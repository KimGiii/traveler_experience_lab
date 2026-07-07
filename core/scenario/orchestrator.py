"""Orchestrate a scenario: plan → fetch (canonical path) → assemble.

The one stateful step is the fetch, and it is injected as a :class:`Fetcher` so
the wiring stays testable offline against fixtures. The live implementation
(``core.cli``) wraps ``McpClient`` + ``adapters.normalize`` — i.e. the same
canonical adapter path ADR 0001 mandates — and raises :class:`FetchError` on any
transport or tool-level failure. A failed call is recorded, not fatal: one dead
domain must not sink the whole scenario.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..schema.scenario_fixture import ProductCandidate, ScenarioFixture, SourceRef
from .assembly import assemble
from .inputs import ScenarioInputs
from .planning import PlannedCall, SkippedCall, plan_calls


class FetchError(RuntimeError):
    """A single tool call failed. ``stage`` is 'transport' or 'tool'."""

    def __init__(self, message: str, *, stage: str):
        super().__init__(message)
        self.stage = stage


class Fetcher(Protocol):
    """Runs one MCP tool through the canonical adapter path.

    Returns normalized candidates, or raises :class:`FetchError`. Implementations
    MUST NOT return raw payloads — normalization is the contract (ADR 0001).
    """

    def __call__(self, tool: str, arguments: dict) -> list[ProductCandidate]: ...


@dataclass(frozen=True)
class CallError:
    domain: str
    tool: str
    stage: str
    error: str


@dataclass
class ScenarioResult:
    """Everything the command needs: the grounded fixture + an execution trace."""

    fixture: ScenarioFixture
    executed: list[PlannedCall] = field(default_factory=list)
    skipped: list[SkippedCall] = field(default_factory=list)
    errors: list[CallError] = field(default_factory=list)


def orchestrate(inputs: ScenarioInputs, fetcher: Fetcher) -> ScenarioResult:
    """Plan the brief, fetch each planned call, assemble the fixture.

    ``inputs`` is resolved first so date fields are derived from ``period`` before
    planning. Skipped calls (missing inputs) and per-call errors are collected and
    returned alongside the fixture rather than raised.
    """
    resolved = inputs.resolved()
    plan = plan_calls(resolved)

    candidates: list[ProductCandidate] = []
    sources: list[SourceRef] = []
    executed: list[PlannedCall] = []
    errors: list[CallError] = []

    for call in plan.calls:
        try:
            fetched = fetcher(call.tool, call.arguments)
        except FetchError as exc:
            errors.append(CallError(call.domain, call.tool, exc.stage, str(exc)))
            continue
        executed.append(call)
        candidates.extend(fetched)
        sources.append(SourceRef(tool=call.tool, arguments=dict(call.arguments)))

    fixture = assemble(resolved, candidates, sources)
    return ScenarioResult(
        fixture=fixture,
        executed=executed,
        skipped=list(plan.skipped),
        errors=errors,
    )
