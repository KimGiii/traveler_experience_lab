"""MCP response -> ScenarioFixture normalization (v1, validated 2026-07-01).

Maps the raw ``tools/call`` result of each search tool into ProductCandidate
rows, grounded in the shapes recorded in ``docs/schema/field_notes.md``. The
common envelope (content/structuredContent/isError, plus the two failure modes)
is handled here so callers get either candidates or a structured McpToolError.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ..schema.scenario_fixture import (
    Price,
    ProductCandidate,
    SourceRef,
    dedupe_candidates,
)

# Bump whenever the mapping logic below changes in a way that could alter output
# for the same upstream payload. Stamped into fixture metadata for drift/regress
# tracking (see docs/schema/contract.md §drift).
NORMALIZER_VERSION = "1"

# Product links appear in two shapes inside the widget tree: the experiences
# path and a legacy offers path (F-4: an offers-only leading card broke the
# old index-based title↔url pairing). Group 0 is the verbatim url, group 1 the
# trailing numeric id (the gid used by getTnaDetail/getTnaOptions chaining).
_TNA_PRODUCT_URL = re.compile(
    r"https://(?:experiences\.myrealtrip\.com/products|www\.myrealtrip\.com/offers)/(\d+)"
)
# copy_text lines like: "1. **[1일권] ... 입장권** ⭐4.8" then "   84,000원~"
_TNA_TITLE = re.compile(r"^\s*\d+\.\s*\*\*(.+?)\*\*(?:\s*⭐\s*([\d.]+))?", re.MULTILINE)
_TNA_PRICE = re.compile(r"([\d,]+)\s*원")


class McpToolError(RuntimeError):
    """A tool returned an error envelope (business or MCP validation error)."""

    def __init__(self, message: str, *, kind: str, raw: Any = None):
        super().__init__(message)
        self.kind = kind  # "business" | "validation"
        self.raw = raw


def source_ref(tool: str, arguments: dict[str, Any]) -> SourceRef:
    return SourceRef(tool=tool, arguments=dict(arguments))


# -- provenance / drift detection -----------------------------------------

def raw_sha256(result: Any) -> str:
    """Stable SHA-256 of a tools/call ``result`` (canonical JSON, sorted keys).

    Deterministic regardless of key order, so a re-probe or an offline backfill
    produces the same digest — the anchor for detecting silent upstream drift.
    """
    canonical = json.dumps(result, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def source_type(result: Any) -> str:
    """Classify how a result carries its data (for fixture metadata).

    One of: "structured" (has structuredContent), "error" (isError envelope),
    "widget" (content json is a UI widget tree), "content-json" (plain JSON in
    content), or "unknown".
    """
    if not isinstance(result, dict):
        return "unknown"
    if result.get("isError"):  # checked first: a business error can also carry structuredContent
        return "error"
    if result.get("structuredContent") is not None:
        return "structured"
    text = _first_text(result)
    parsed = _try_json(text)
    if isinstance(parsed, dict):
        return "widget" if "widget" in parsed else "content-json"
    return "unknown"


def fingerprint(result: Any) -> dict[str, str]:
    """Fixture metadata block: normalizer version, source type, raw digest."""
    return {
        "normalizer_version": NORMALIZER_VERSION,
        "source_type": source_type(result),
        "raw_sha256": raw_sha256(result),
    }


# -- envelope handling -----------------------------------------------------

def unwrap(result: Any) -> tuple[dict[str, Any] | None, Any]:
    """Return ``(structured, content_json)`` from a tools/call result.

    ``structured`` is ``result.structuredContent`` when present. ``content_json``
    is ``result.content[0].text`` parsed as JSON (or the raw string on failure).
    Raises McpToolError on either failure mode described in field_notes §1.
    """
    if not isinstance(result, dict):
        raise McpToolError("unexpected result (not an object)", kind="validation", raw=result)

    structured = result.get("structuredContent")
    text = _first_text(result)
    content_json = _try_json(text)

    if result.get("isError"):
        # Mode 2: MCP validation error — no structuredContent, text carries it.
        if structured is None:
            raise McpToolError(str(text)[:500], kind="validation", raw=text)
        # Mode 1: business error — structuredContent.success == false.
        message = ""
        if isinstance(structured, dict):
            message = structured.get("error") or structured.get("presentation", {}).get("note") or ""
        raise McpToolError(str(message)[:500] or "tool error", kind="business", raw=structured)

    return structured, content_json


def _first_text(result: dict[str, Any]) -> str | None:
    content = result.get("content")
    if isinstance(content, list) and content:
        block = content[0]
        if isinstance(block, dict) and block.get("type") == "text":
            return block.get("text")
    return None


def _try_json(text: Any) -> Any:
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


# -- per-domain normalization ---------------------------------------------

def normalize(tool: str, arguments: dict[str, Any], result: Any) -> list[ProductCandidate]:
    """Dispatch to the right per-tool mapper; returns [] for unmodeled tools."""
    structured, content_json = unwrap(result)
    src = source_ref(tool, arguments)
    if tool in ("searchInternationalFlights", "searchDomesticFlights"):
        cands = _flights(structured, src)
    elif tool == "searchStays":
        cands = _stays(structured, src)
    elif tool == "searchTnas":
        cands = _tnas(content_json, src)
    elif tool == "getStayDetail":
        cands = _stay_detail(content_json, src)
    elif tool == "getTnaOptions":
        cands = _tna_options(content_json, src)
    elif tool == "getTnaDetail":
        cands = _tna_detail(content_json, src)
    else:
        return []
    # Contract: preserve upstream order, dedupe (first occurrence wins).
    return dedupe_candidates(cands)


def _flights(structured: Any, src: SourceRef) -> list[ProductCandidate]:
    items = (((structured or {}).get("result") or {}).get("items")) or []
    out: list[ProductCandidate] = []
    for it in items:
        price = it.get("price") or {}
        route = it.get("route") or {}
        airline = it.get("airline")
        airline_name = airline.get("name") if isinstance(airline, dict) else (airline or "")
        title = f"{route.get('origin', '?')}→{route.get('destination', '?')} {airline_name}".strip()
        out.append(
            ProductCandidate(
                domain="flights",
                title=title,
                price=Price(amount=price.get("total"), currency=price.get("currency", "KRW")),
                booking_url=it.get("reservationUrl"),
                identifier=str(it.get("id")) if it.get("id") is not None else None,
                edge_flags=["price_change", "mobile"],
                source=src,
                raw=it,
            )
        )
    return out


def _stays(structured: Any, src: SourceRef) -> list[ProductCandidate]:
    stays = (structured or {}).get("stays") or []
    out: list[ProductCandidate] = []
    for s in stays:
        out.append(
            ProductCandidate(
                domain="stays",
                title=s.get("name"),
                price=Price(text=s.get("price")),
                rating=_as_float(s.get("rating")),
                review_count=_as_int(s.get("reviewCount")),
                # searchStays list carries no reservation URL and no cancellation /
                # availability fields (field_notes §3): booking_url + those edges
                # only surface via getStayDetail (shareWebLink / isFreeCancellation).
                # So nothing is grounded at search depth — keep url None, flags empty.
                booking_url=None,
                identifier=str(s.get("gid")) if s.get("gid") is not None else None,
                edge_flags=[],
                source=src,
                raw=s,
            )
        )
    return out


def _tnas(content_json: Any, src: SourceRef) -> list[ProductCandidate]:
    """TNA search has no structuredContent — parse copy_text + widget urls."""
    if not isinstance(content_json, dict):
        return []
    copy_text = content_json.get("copy_text") or ""
    # finditer (not findall) so we can slice each product's verbatim copy_text
    # block — the closest thing to a per-item upstream object, since TNA search
    # returns no structuredContent and no discrete per-product JSON.
    matches = list(_TNA_TITLE.finditer(copy_text))
    # Pair titles to urls by *position inside the widget tree*, not by index:
    # each card renders its title followed by its own url group, and cards
    # without a product/offers url (F-4) would shift an index-based mapping.
    # A title we cannot locate in the widget gets gid None — no pairing beats
    # a wrong one (chaining with a wrong gid returns a different product).
    widget_str = json.dumps(content_json.get("widget") or {}, ensure_ascii=False)
    title_pos = [widget_str.find(m.group(1).strip()) for m in matches]

    def _url_after(i: int) -> tuple[str | None, str | None]:
        start = title_pos[i]
        if start < 0:
            return None, None
        following = [p for p in title_pos[i + 1:] if p >= 0]
        end = min(following) if following else len(widget_str)
        u = _TNA_PRODUCT_URL.search(widget_str, start, end)
        return (u.group(0), u.group(1)) if u else (None, None)

    out: list[ProductCandidate] = []
    for i, m in enumerate(matches):
        title, rating = m.group(1), m.group(2)
        product_url, gid = _url_after(i)
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(copy_text)
        block = copy_text[m.start():block_end].strip()  # verbatim source slice
        price_m = _TNA_PRICE.search(block)  # price from THIS block, not a global index
        out.append(
            ProductCandidate(
                domain="tnas",
                title=title.strip(),
                price=Price(text=f"{price_m.group(1)}원~") if price_m else None,
                rating=_as_float(rating) if rating else None,
                booking_url=product_url,
                identifier=gid,
                # Only "mobile" is grounded at search depth (product_url is a
                # mobile-web booking link). date_unavailable / cancellation need
                # getTnaOptions / getTnaDetail evidence (field_notes §5) and are set
                # by those normalizers — do NOT assert them from search alone.
                edge_flags=["mobile"],
                source=src,
                # Source fragment (not a re-synthesized dict): the untouched
                # copy_text block + resolved product url. See contract.md §raw.
                raw={"copy_text_block": block, "product_url": product_url},
            )
        )
    return out


def _stay_detail(content_json: Any, src: SourceRef) -> list[ProductCandidate]:
    """getStayDetail -> one enriched candidate (availability, cancellation, url)."""
    if not isinstance(content_json, dict):
        return []
    prop = content_json.get("property") or {}
    pricing = content_json.get("pricing") or {}
    rooms = content_json.get("rooms") or []
    is_sold_out = bool(pricing.get("isSoldOut")) or bool(content_json.get("noRoomsAvailable"))
    free_cancel = any(r.get("isFreeCancellation") for r in rooms) if rooms else None
    # Evidence-gated flags (field_notes §5): shareWebLink → mobile; rooms carrying
    # isFreeCancellation → cancellation; an originalPrice → possible price move;
    # sold_out only when confirmed. No blanket assertions.
    flags = ["mobile"]
    if free_cancel is not None:
        flags.append("cancellation")
    if pricing.get("originalPrice") is not None:
        flags.append("price_change")
    if is_sold_out:
        flags.insert(0, "sold_out")
    return [
        ProductCandidate(
            domain="stays",
            title=prop.get("name"),
            price=Price(
                amount=pricing.get("averagePrice"),
                text=pricing.get("priceText"),
                original_amount=pricing.get("originalPrice"),
            ),
            rating=_as_float(prop.get("reviewScore")),
            review_count=_as_int(prop.get("reviewCount")),
            booking_url=prop.get("shareWebLink"),
            identifier=str(prop.get("gid")) if prop.get("gid") is not None else None,
            available=not is_sold_out,
            free_cancellation=free_cancel,
            edge_flags=flags,
            source=src,
            raw=content_json,
        )
    ]


def _tna_options(content_json: Any, src: SourceRef) -> list[ProductCandidate]:
    """getTnaOptions -> one candidate carrying date availability."""
    if not isinstance(content_json, dict):
        return []
    has_options = bool(content_json.get("hasAvailableOptions"))
    date_ok = content_json.get("isRequestedDateAvailable")
    available = has_options and bool(date_ok) if date_ok is not None else has_options
    params = content_json.get("searchParams") or {}
    flags = ["date_unavailable", "mobile"] if not available else ["mobile"]
    return [
        ProductCandidate(
            domain="tnas",
            identifier=str(params.get("gid")) if params.get("gid") is not None else None,
            booking_url=params.get("url"),
            available=available,
            availability_note=content_json.get("availabilityMessage"),
            edge_flags=flags,
            source=src,
            raw=content_json,
        )
    ]


def _tna_detail(content_json: Any, src: SourceRef) -> list[ProductCandidate]:
    """getTnaDetail -> one candidate; title/rating/cancellation from copy_text."""
    if not isinstance(content_json, dict):
        return []
    copy_text = content_json.get("copy_text") or ""
    title_m = re.search(r"\*\*(.+?)\*\*", copy_text)
    rating_m = re.search(r"⭐\s*([\d.]+)\s*\(리뷰\s*([\d,]+)개\)", copy_text)
    cancellation = _extract_cancellation(copy_text)  # may be absent (field_notes §4)
    meeting_place, meeting_time = _extract_meeting(content_json.get("widget"))
    return [
        ProductCandidate(
            domain="tnas",
            title=title_m.group(1).strip() if title_m else content_json.get("name"),
            rating=_as_float(rating_m.group(1)) if rating_m else None,
            review_count=_as_int(rating_m.group(2)) if rating_m else None,
            cancellation_note=cancellation,
            meeting_place=meeting_place,
            meeting_time=meeting_time,
            # "cancellation" only when the copy_text actually carries a policy line.
            edge_flags=["cancellation", "mobile"] if cancellation else ["mobile"],
            source=src,
            raw=content_json,  # single-product detail: full upstream object (lossless)
        )
    ]


# Meeting info lives in the widget's "이용 안내" section as Text nodes prefixed
# "장소:" / "시간:" — NOT in copy_text (field_notes §4). The guide's contact
# number is deliberately not extracted: it is absent pre-booking ("예약 확정 후
# 조율"), so there is no source field to normalize (F-5).
_MEETING_PREFIX = re.compile(r"^\s*(장소|시간)\s*:\s*(.+)$", re.DOTALL)


def _extract_meeting(widget: Any) -> tuple[str | None, str | None]:
    place: str | None = None
    time: str | None = None

    def walk(node: Any) -> None:
        nonlocal place, time
        if isinstance(node, dict):
            if node.get("type") == "Text" and isinstance(node.get("value"), str):
                m = _MEETING_PREFIX.match(node["value"].strip())
                if m:
                    label, value = m.group(1), m.group(2).strip()
                    if label == "장소" and place is None:
                        place = value
                    elif label == "시간" and time is None:
                        time = value
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(widget)
    return place, time


def _extract_cancellation(copy_text: str) -> str | None:
    """Pull the first line mentioning 취소/환불 from a TNA copy_text, if any."""
    for line in copy_text.splitlines():
        if "취소" in line or "환불" in line:
            return line.strip().lstrip("•*# ").strip()
    return None


def _dedupe(seq: list[str]) -> list[str]:
    """Order-preserving de-duplication."""
    seen: set[str] = set()
    out: list[str] = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _as_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_int(v: Any) -> int | None:
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        digits = re.sub(r"[^\d]", "", v)
        return int(digits) if digits else None
    return None
