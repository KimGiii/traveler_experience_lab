"""Traveler Experience Lab — scenario orchestration.

Assembles a grounded :class:`ScenarioFixture` from a user brief by planning MCP
search calls, running them through the canonical adapter path, and folding the
results (with derived edge cases) into one validated bundle. Network access is
injected as a :class:`Fetcher`, so plan/assemble/orchestrate stay pure.
"""
from __future__ import annotations

from .assembly import LOW_REVIEW_THRESHOLD, assemble, derive_edge_cases
from .inputs import DEFAULT_ADULTS, DEFAULT_ORIGIN, ScenarioInputs
from .orchestrator import (
    CallError,
    Fetcher,
    FetchError,
    ScenarioResult,
    orchestrate,
)
from .planning import Plan, PlannedCall, SkippedCall, plan_calls

__all__ = [
    "ScenarioInputs",
    "DEFAULT_ADULTS",
    "DEFAULT_ORIGIN",
    "plan_calls",
    "Plan",
    "PlannedCall",
    "SkippedCall",
    "assemble",
    "derive_edge_cases",
    "LOW_REVIEW_THRESHOLD",
    "orchestrate",
    "ScenarioResult",
    "Fetcher",
    "FetchError",
    "CallError",
]
