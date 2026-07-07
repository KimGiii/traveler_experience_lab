"""Plan the MCP search calls a scenario brief implies — pure, offline.

Turns a resolved :class:`ScenarioInputs` into the concrete ``(tool, arguments)``
calls the orchestrator will run through the canonical adapter path, plus an
honest list of calls it *could not* plan (missing required inputs). Keeping this
a pure function makes the "which tools, with what args" decision testable without
touching the network, and mirrors the argument names the tools actually require
(``searchTnas`` → ``query``; ``searchStays`` → ``keyword``+``checkIn``/``checkOut``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..mcp.endpoints import (
    TOOL_SEARCH_INTERNATIONAL_FLIGHTS,
    TOOL_SEARCH_STAYS,
    TOOL_SEARCH_TNAS,
)
from .inputs import ScenarioInputs


@dataclass(frozen=True)
class PlannedCall:
    """A concrete MCP search call the orchestrator should execute."""

    domain: str
    tool: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class SkippedCall:
    """A call we intentionally did not plan, with the missing inputs named.

    Surfaced so the command can ask the user for exactly what's missing instead
    of silently returning a thinner scenario.
    """

    domain: str
    tool: str
    missing: tuple[str, ...]


@dataclass(frozen=True)
class Plan:
    calls: tuple[PlannedCall, ...]
    skipped: tuple[SkippedCall, ...]


def plan_calls(inputs: ScenarioInputs) -> Plan:
    """Decide which search tools to call for this brief.

    ``destination`` anchors everything; without it every call is skipped. Each
    domain is planned only when its required inputs are present, otherwise it is
    recorded as skipped with the exact missing field names.
    """
    calls: list[PlannedCall] = []
    skipped: list[SkippedCall] = []

    _plan_tnas(inputs, calls, skipped)
    _plan_stays(inputs, calls, skipped)
    _plan_flights(inputs, calls, skipped)

    return Plan(calls=tuple(calls), skipped=tuple(skipped))


def _plan_tnas(
    inputs: ScenarioInputs, calls: list[PlannedCall], skipped: list[SkippedCall]
) -> None:
    if inputs.destination:
        calls.append(
            PlannedCall("tnas", TOOL_SEARCH_TNAS, {"query": inputs.destination})
        )
    else:
        skipped.append(SkippedCall("tnas", TOOL_SEARCH_TNAS, ("destination",)))


def _plan_stays(
    inputs: ScenarioInputs, calls: list[PlannedCall], skipped: list[SkippedCall]
) -> None:
    missing = _missing(
        destination=inputs.destination,
        checkIn=inputs.check_in,
        checkOut=inputs.check_out,
    )
    if missing:
        skipped.append(SkippedCall("stays", TOOL_SEARCH_STAYS, missing))
        return
    calls.append(
        PlannedCall(
            "stays",
            TOOL_SEARCH_STAYS,
            {
                "keyword": inputs.destination,
                "checkIn": inputs.check_in,
                "checkOut": inputs.check_out,
                "adultCount": inputs.adults,
                "order": "recommended",
            },
        )
    )


def _plan_flights(
    inputs: ScenarioInputs, calls: list[PlannedCall], skipped: list[SkippedCall]
) -> None:
    # searchInternationalFlights takes IATA codes, not place names — skip rather
    # than guess a code from the destination string.
    missing = _missing(
        destination_iata=inputs.destination_iata,
        departDate=inputs.depart_date,
    )
    if missing:
        skipped.append(SkippedCall("flights", TOOL_SEARCH_INTERNATIONAL_FLIGHTS, missing))
        return
    arguments: dict[str, Any] = {
        "origin": inputs.origin,
        "destination": inputs.destination_iata,
        "departDate": inputs.depart_date,
        "passengers": {"adults": inputs.adults},
    }
    if inputs.return_date:
        arguments["tripType"] = "ROUND_TRIP"
        arguments["returnDate"] = inputs.return_date
    else:
        arguments["tripType"] = "ONE_WAY"
    calls.append(PlannedCall("flights", TOOL_SEARCH_INTERNATIONAL_FLIGHTS, arguments))


def _missing(**fields: Any) -> tuple[str, ...]:
    """Return the names of the fields that are falsy (missing), in order."""
    return tuple(name for name, value in fields.items() if not value)
