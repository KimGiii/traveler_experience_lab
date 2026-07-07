"""ScenarioFixture — schema v1 (validated 2026-07-01).

Normalized shape the ``/mrt scenario`` command consumes: real MRT product
candidates (flights / stays / tnas) plus the domain edge cases they imply.
Field choices are grounded in real MCP payloads — see
``docs/schema/field_notes.md`` and ``fixtures/``. Still a draft: only the fields
observed across the sample sweep are modeled; anything unobserved stays in
``raw``.

Plain dataclasses (stdlib only) to stay dependency-free and runtime-agnostic.

ProductCandidate CONTRACT (enforced by ``validate_candidate``; see
``docs/schema/contract.md``):
  * Required (never None): ``domain`` (∈ DOMAINS), ``source`` (provenance),
    ``raw`` (the preserved source the candidate derived from — the whole
    per-product object when the tool returns one, else the original source
    fragment for widget/copy_text responses like TNA search; never derived or
    re-synthesized. See ``docs/schema/contract.md`` §raw).
  * Nullable: every other field — absence means "not provided by this tool",
    never "known to be empty".
  * ``edge_flags`` ⊆ ``EDGE_CASES``.
  * Ordering: candidates preserve the UPSTREAM order returned by the MCP tool
    (relevance / recommended / isCheapest ranking is meaningful). Normalizers
    MUST NOT re-sort.
  * De-duplication: order-preserving; key = ``identifier`` when present, else
    ``(domain, title, booking_url)``. First occurrence wins.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Domain = Literal["flights", "stays", "tnas"]
DOMAINS: tuple[str, ...] = ("flights", "stays", "tnas")
SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class SourceRef:
    """Provenance: which MCP tool + arguments produced a piece of data."""

    tool: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Price:
    """Money, normalized across the three domains' differing price shapes.

    ``amount`` is the numeric KRW value when available; ``text`` preserves the
    human string (e.g. "86,834원~") since some tools only give text.
    """

    amount: int | None = None
    currency: str = "KRW"
    text: str | None = None
    original_amount: int | None = None  # for discount/price-change edge cases


@dataclass
class ProductCandidate:
    """A single real product surfaced from the MCP.

    Common fields are lifted from each domain's response; ``raw`` preserves the
    source the candidate derived from (whole per-product object, or the source
    fragment when the tool has no per-product object). Whole-response
    losslessness is guaranteed separately by CLI/probe response metadata's
    ``raw_sha256``.
    """

    domain: Domain
    title: str | None = None
    price: Price | None = None
    rating: float | None = None
    review_count: int | None = None
    booking_url: str | None = None       # reservationUrl / product url / shareWebLink
    identifier: str | None = None        # gid (stays/tnas) or fare id (flights)
    # Enrichment from detail tools (getStayDetail / getTnaOptions / getTnaDetail).
    available: bool | None = None            # isSoldOut / noRoomsAvailable / hasAvailableOptions
    availability_note: str | None = None     # e.g. "해당 날짜는 예약이 불가능합니다."
    free_cancellation: bool | None = None    # stay room isFreeCancellation
    cancellation_note: str | None = None     # cancellation policy text (tna copy_text)
    # Meeting info from getTnaDetail's "이용 안내" widget section (field_notes §4).
    # Present for most TNA products; the guide's contact number is NOT — it is
    # disclosed only after booking, so it has no pre-booking source field.
    meeting_place: str | None = None
    meeting_time: str | None = None
    edge_flags: list[str] = field(default_factory=list)  # e.g. "sold_out", "date_unavailable"
    source: SourceRef | None = None
    raw: Any = None

    def __post_init__(self) -> None:
        # Cheap always-on invariant: domain must be one of the known domains.
        if self.domain not in DOMAINS:
            raise ValueError(f"ProductCandidate.domain must be one of {DOMAINS}, got {self.domain!r}")


# Canonical edge-case vocabulary (see field_notes.md §5). Kept as a tuple so the
# scenario command and adapters agree on the same labels.
EDGE_CASES: tuple[str, ...] = (
    "sold_out",          # 재고없음
    "date_unavailable",  # 날짜불일치
    "price_change",      # 가격변동
    "cancellation",      # 취소/환불 정책
    "low_reviews",       # 리뷰부족/신뢰성
    "mobile",            # 모바일 예약 흐름
)


def validate_candidate(c: ProductCandidate) -> ProductCandidate:
    """Enforce the full ProductCandidate contract; returns ``c`` or raises.

    Checks the required-never-None fields, the edge_flags vocabulary, and basic
    type/range sanity. ``__post_init__`` already guarantees ``domain``.
    """
    if c.source is None:
        raise ValueError("ProductCandidate.source is required (provenance)")
    if c.raw is None:
        raise ValueError("ProductCandidate.raw is required (preserved source; see contract.md §raw)")
    bad_flags = [f for f in c.edge_flags if f not in EDGE_CASES]
    if bad_flags:
        raise ValueError(f"edge_flags not in EDGE_CASES: {bad_flags}")
    if c.price is not None and not isinstance(c.price, Price):
        raise ValueError("price must be a Price or None")
    if c.rating is not None and not (0.0 <= c.rating <= 5.0):
        raise ValueError(f"rating out of range [0,5]: {c.rating}")
    return c


def _dedupe_key(c: ProductCandidate) -> tuple:
    """Contract dedupe key: identifier if present, else (domain, title, url)."""
    if c.identifier:
        return (c.domain, "id", c.identifier)
    return (c.domain, "fallback", c.title, c.booking_url)


def dedupe_candidates(cands: list[ProductCandidate]) -> list[ProductCandidate]:
    """Order-preserving de-duplication per the contract (first occurrence wins)."""
    seen: set[tuple] = set()
    out: list[ProductCandidate] = []
    for c in cands:
        key = _dedupe_key(c)
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


@dataclass
class ScenarioFixture:
    """Normalized input bundle for scenario generation (v1)."""

    destination: str | None = None
    period: str | None = None
    budget: Any | None = None
    companions: str | None = None
    persona: str | None = None
    candidates: list[ProductCandidate] = field(default_factory=list)
    edge_cases: list[str] = field(default_factory=list)  # subset of EDGE_CASES
    sources: list[SourceRef] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
