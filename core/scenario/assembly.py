"""Assemble fetched candidates into a validated :class:`ScenarioFixture`.

Two jobs, both pure:
  * fold the per-call candidate lists into one deduped, contract-valid bundle;
  * derive the scenario-level ``edge_cases`` — the union of what the normalizer
    flagged per candidate, plus data-driven signals the normalizer cannot know
    at single-tool granularity (low reviews, an actual price delta, a confirmed
    sold-out). Grounded in field_notes §5's edge-case → field mapping.
"""
from __future__ import annotations

import json
from typing import Iterable

from ..schema.scenario_fixture import (
    EDGE_CASES,
    ProductCandidate,
    ScenarioFixture,
    SourceRef,
    dedupe_candidates,
    validate_candidate,
)
from .inputs import ScenarioInputs

# Below this review count a stay/tna is "리뷰부족/신뢰성" (field_notes §5). Named
# so the threshold is a single tunable, not a magic number sprinkled in logic.
LOW_REVIEW_THRESHOLD = 10


def derive_edge_cases(candidates: Iterable[ProductCandidate]) -> list[str]:
    """Union the candidates' edge signals, returned in canonical EDGE_CASES order.

    Starts from each candidate's ``edge_flags`` (set by the normalizer) and adds
    signals that only become visible once real values are in hand:
      * ``low_reviews`` — a known review_count under the threshold;
      * ``price_change`` — an original price that actually differs from current;
      * ``sold_out`` — availability confirmed False.
    Ordering by ``EDGE_CASES`` keeps output stable regardless of candidate order.
    """
    present: set[str] = set()
    for c in candidates:
        present.update(c.edge_flags)
        if c.review_count is not None and c.review_count < LOW_REVIEW_THRESHOLD:
            present.add("low_reviews")
        if _has_price_delta(c):
            present.add("price_change")
        if c.available is False:
            present.add("sold_out")
    return [edge for edge in EDGE_CASES if edge in present]


def assemble(
    inputs: ScenarioInputs,
    candidates: Iterable[ProductCandidate],
    sources: Iterable[SourceRef],
) -> ScenarioFixture:
    """Build the fixture: dedupe + validate candidates, derive edges, keep sources.

    Raises (via ``validate_candidate``) if any candidate breaches the contract —
    the fixture is the hand-off surface, so a bad candidate must fail loudly here
    rather than reach the scenario prose.
    """
    deduped = dedupe_candidates(list(candidates))
    for c in deduped:
        validate_candidate(c)
    return ScenarioFixture(
        destination=inputs.destination,
        period=inputs.period,
        budget=inputs.budget,
        companions=inputs.companions,
        persona=inputs.persona,
        candidates=deduped,
        edge_cases=derive_edge_cases(deduped),
        sources=_unique_sources(sources),
    )


def _has_price_delta(c: ProductCandidate) -> bool:
    p = c.price
    return bool(
        p is not None
        and p.original_amount is not None
        and p.amount is not None
        and p.original_amount != p.amount
    )


def _unique_sources(sources: Iterable[SourceRef]) -> list[SourceRef]:
    """Order-preserving de-dup of provenance (SourceRef holds an unhashable dict)."""
    seen: set[str] = set()
    out: list[SourceRef] = []
    for s in sources:
        # Canonical JSON so nested-dict args (e.g. flights passengers) hash safely.
        key = s.tool + "|" + json.dumps(s.arguments, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out
