"""ScenarioInputs — the user-facing brief the orchestrator plans from.

Deliberately dumb: it holds what ``/mrt scenario`` collected (destination,
period, budget, companions, persona) plus the concrete fields the MCP search
tools need (dates, IATA, origin). ``resolved()`` fills the date fields from a
free-text ``period`` when they were not passed explicitly, so the planner only
ever sees normalized dates. No network, no MCP knowledge — pure data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

# Departure airport assumed when the brief does not name one. MRT's audience is
# domestic (KR), so ICN is the sensible default; override via --origin.
DEFAULT_ORIGIN = "ICN"
DEFAULT_ADULTS = 2

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class ScenarioInputs:
    """Immutable brief. Optional fields are ``None`` when the user omitted them.

    ``destination`` is the anchor: without it the planner can plan nothing.
    ``destination_iata`` is required only for the flights call (search tools
    take an IATA code, not a place name), so flights are skipped when it is
    absent rather than guessed.
    """

    destination: str | None = None
    period: str | None = None
    budget: Any | None = None
    companions: str | None = None
    persona: str | None = None
    origin: str = DEFAULT_ORIGIN
    destination_iata: str | None = None
    check_in: str | None = None
    check_out: str | None = None
    depart_date: str | None = None
    return_date: str | None = None
    adults: int = DEFAULT_ADULTS

    def resolved(self) -> "ScenarioInputs":
        """Return a copy with date fields derived from ``period`` when missing.

        Only fills gaps — an explicitly provided ``check_in``/``depart_date`` is
        never overwritten. Extracts ISO dates (``YYYY-MM-DD``) from the free-text
        period: the first becomes check-in/depart, the second check-out/return.
        A period without two ISO dates leaves the unresolved fields ``None`` (the
        planner then skips the calls that need them).
        """
        check_in, check_out = self.check_in, self.check_out
        if (check_in is None or check_out is None) and self.period:
            found = _ISO_DATE.findall(self.period)
            if found:
                check_in = check_in or found[0]
            if len(found) >= 2:
                check_out = check_out or found[1]
        depart_date = self.depart_date or check_in
        return_date = self.return_date or check_out
        return replace(
            self,
            check_in=check_in,
            check_out=check_out,
            depart_date=depart_date,
            return_date=return_date,
        )
