"""Scenario orchestration tests — pure/offline (stdlib unittest).

Exercises plan → assemble → orchestrate against real success fixtures with an
injected fetcher, so no network is touched:

    python3 -m unittest discover -s tests

Covers: date resolution from free-text period, the plan/skip decision per
domain, edge-case derivation (union + data-driven signals, canonical order),
end-to-end assembly, and the "one dead call is recorded, not fatal" guarantee.
"""
from __future__ import annotations

import argparse
import contextlib
import glob
import io
import json
import os
import unittest
from unittest.mock import patch

from core import cli
from core.mcp.adapters import normalize
from core.mcp.client import McpError
from core.scenario import (
    FetchError,
    ScenarioInputs,
    ScenarioResult,
    assemble,
    derive_edge_cases,
    orchestrate,
    plan_calls,
)
from core.schema.scenario_fixture import (
    EDGE_CASES,
    Price,
    ProductCandidate,
    ScenarioFixture,
    SourceRef,
)

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIXTURES = {
    os.path.basename(p): p
    for p in glob.glob(os.path.join(_REPO, "fixtures", "*", "*.json"))
}

# Success fixtures, one per domain, that normalize into candidates.
_TOOL_FIXTURE = {
    "searchTnas": "searchTnas.sample1.json",
    "searchStays": "searchStays.sample1.json",
    "searchInternationalFlights": "searchInternationalFlights.sample1.json",
}


def _load(name: str) -> dict:
    with open(_FIXTURES[name], encoding="utf-8") as fh:
        return json.load(fh)


def _fixture_fetcher(tool: str, arguments: dict) -> list[ProductCandidate]:
    """A Fetcher backed by recorded fixtures instead of the network."""
    rec = _load(_TOOL_FIXTURE[tool])
    return normalize(rec["tool"], rec.get("arguments", {}), rec["result"])


def _cand(**kw) -> ProductCandidate:
    kw.setdefault("domain", "stays")
    kw.setdefault("source", SourceRef(tool="t", arguments={}))
    kw.setdefault("raw", {})
    return ProductCandidate(**kw)


class InputResolution(unittest.TestCase):
    def test_period_range_fills_dates(self):
        got = ScenarioInputs(destination="오사카", period="2026-09-10 ~ 2026-09-13").resolved()
        self.assertEqual(got.check_in, "2026-09-10")
        self.assertEqual(got.check_out, "2026-09-13")
        self.assertEqual(got.depart_date, "2026-09-10")
        self.assertEqual(got.return_date, "2026-09-13")

    def test_explicit_dates_not_overwritten(self):
        got = ScenarioInputs(
            destination="오사카", period="2026-09-10~2026-09-13", check_in="2026-10-01"
        ).resolved()
        self.assertEqual(got.check_in, "2026-10-01")  # explicit wins
        self.assertEqual(got.check_out, "2026-09-13")  # gap filled from period

    def test_period_without_dates_leaves_none(self):
        got = ScenarioInputs(destination="오사카", period="3박4일").resolved()
        self.assertIsNone(got.check_in)
        self.assertIsNone(got.check_out)


class Planning(unittest.TestCase):
    def test_full_brief_plans_three_domains(self):
        inputs = ScenarioInputs(
            destination="오사카",
            check_in="2026-09-10",
            check_out="2026-09-13",
            destination_iata="KIX",
            depart_date="2026-09-10",
        )
        plan = plan_calls(inputs)
        domains = {c.domain for c in plan.calls}
        self.assertEqual(domains, {"tnas", "stays", "flights"})
        self.assertEqual(plan.skipped, ())

    def test_missing_dates_skip_stays_and_flights(self):
        plan = plan_calls(ScenarioInputs(destination="오사카"))
        self.assertEqual([c.domain for c in plan.calls], ["tnas"])
        skipped = {s.domain: s.missing for s in plan.skipped}
        self.assertIn("checkIn", skipped["stays"])
        self.assertIn("destination_iata", skipped["flights"])

    def test_no_destination_skips_everything(self):
        plan = plan_calls(ScenarioInputs())
        self.assertEqual(plan.calls, ())
        self.assertEqual({s.domain for s in plan.skipped}, {"tnas", "stays", "flights"})

    def test_tnas_uses_query_stays_uses_keyword(self):
        inputs = ScenarioInputs(destination="오사카", check_in="2026-09-10", check_out="2026-09-13")
        by_tool = {c.tool: c.arguments for c in plan_calls(inputs).calls}
        self.assertEqual(by_tool["searchTnas"]["query"], "오사카")
        self.assertEqual(by_tool["searchStays"]["keyword"], "오사카")
        self.assertEqual(by_tool["searchStays"]["checkIn"], "2026-09-10")


class EdgeCaseDerivation(unittest.TestCase):
    def test_returned_in_canonical_order(self):
        cands = [
            _cand(edge_flags=["mobile", "cancellation"]),
            _cand(edge_flags=["sold_out"]),
        ]
        got = derive_edge_cases(cands)
        self.assertEqual(got, [e for e in EDGE_CASES if e in set(got)])
        self.assertLess(got.index("sold_out"), got.index("cancellation"))

    def test_low_reviews_derived_from_count(self):
        self.assertIn("low_reviews", derive_edge_cases([_cand(review_count=3)]))
        self.assertNotIn("low_reviews", derive_edge_cases([_cand(review_count=500)]))

    def test_price_change_from_original_delta(self):
        changed = _cand(price=Price(amount=80000, original_amount=100000))
        same = _cand(price=Price(amount=80000, original_amount=80000))
        self.assertIn("price_change", derive_edge_cases([changed]))
        self.assertNotIn("price_change", derive_edge_cases([same]))

    def test_sold_out_from_available_false(self):
        self.assertIn("sold_out", derive_edge_cases([_cand(available=False)]))
        self.assertNotIn("sold_out", derive_edge_cases([_cand(available=True)]))


class Assembly(unittest.TestCase):
    def test_dedupes_across_sources(self):
        dup = dict(domain="tnas", identifier="123", title="USJ")
        fixture = assemble(
            ScenarioInputs(destination="오사카"),
            [_cand(**dup), _cand(**dup)],
            [SourceRef(tool="searchTnas", arguments={"query": "오사카"})],
        )
        self.assertEqual(len(fixture.candidates), 1)

    def test_carries_brief_and_sources(self):
        fixture = assemble(
            ScenarioInputs(destination="오사카", persona="가족"),
            [_cand(domain="tnas", identifier="1")],
            [
                SourceRef(tool="searchTnas", arguments={"query": "오사카"}),
                SourceRef(tool="searchTnas", arguments={"query": "오사카"}),  # dup
            ],
        )
        self.assertEqual(fixture.destination, "오사카")
        self.assertEqual(fixture.persona, "가족")
        self.assertEqual(len(fixture.sources), 1)  # provenance deduped


class OrchestrateEndToEnd(unittest.TestCase):
    def _full_inputs(self) -> ScenarioInputs:
        return ScenarioInputs(
            destination="오사카",
            period="2026-09-10~2026-09-13",
            persona="가족",
            destination_iata="KIX",
        )

    def test_assembles_from_fixture_fetcher(self):
        result = orchestrate(self._full_inputs(), _fixture_fetcher)
        self.assertEqual({c.domain for c in result.executed}, {"tnas", "stays", "flights"})
        self.assertEqual(result.errors, [])
        self.assertTrue(result.fixture.candidates)
        self.assertTrue(result.fixture.edge_cases)
        # every derived edge case is in the canonical vocabulary
        self.assertTrue(set(result.fixture.edge_cases) <= set(EDGE_CASES))

    def test_one_failing_call_is_recorded_not_fatal(self):
        def flaky(tool: str, arguments: dict):
            if tool == "searchStays":
                raise FetchError("boom", stage="tool")
            return _fixture_fetcher(tool, arguments)

        result = orchestrate(self._full_inputs(), flaky)
        failed = {e.tool for e in result.errors}
        self.assertEqual(failed, {"searchStays"})
        # tnas + flights still assembled despite the stays failure
        self.assertEqual({c.domain for c in result.executed}, {"tnas", "flights"})
        self.assertTrue(result.fixture.candidates)

    def test_missing_inputs_surface_as_skipped(self):
        result = orchestrate(ScenarioInputs(destination="오사카"), _fixture_fetcher)
        self.assertEqual({s.domain for s in result.skipped}, {"stays", "flights"})
        self.assertEqual([c.tool for c in result.executed], ["searchTnas"])


class CliScenarioSurface(unittest.TestCase):
    def _args(self, **overrides) -> argparse.Namespace:
        defaults = {
            "destination": None,
            "period": None,
            "budget": None,
            "companions": None,
            "persona": None,
            "origin": "ICN",
            "destination_iata": None,
            "check_in": None,
            "check_out": None,
            "depart_date": None,
            "return_date": None,
            "adults": 2,
            "with_raw": False,
        }
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_scenario_subcommand_registered(self):
        parser = cli.build_parser()
        choices = set([a for a in parser._actions if a.dest == "command"][0].choices)
        self.assertIn("scenario", choices)

    def test_result_dict_can_include_response_fingerprints(self):
        result = ScenarioResult(fixture=ScenarioFixture(destination="오사카"))
        meta = [
            {
                "tool": "searchTnas",
                "arguments": {"query": "오사카"},
                "normalizer_version": "1",
                "source_type": "widget",
                "raw_sha256": "abc123",
            }
        ]

        row = cli._result_dict(result, include_raw=False, response_meta=meta)

        self.assertEqual(row["_meta"]["responses"][0]["raw_sha256"], "abc123")
        self.assertEqual(row["_meta"]["responses"][0]["source_type"], "widget")

    def test_scenario_with_no_planned_calls_does_not_open_session(self):
        buf = io.StringIO()
        with patch.object(cli, "_new_session", side_effect=AssertionError("network not needed")):
            with contextlib.redirect_stdout(buf):
                code = cli.cmd_scenario(self._args())

        payload = json.loads(buf.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["executed"], [])
        self.assertEqual({s["domain"] for s in payload["skipped"]}, {"tnas", "stays", "flights"})

    def test_scenario_session_failure_is_recorded_in_trace(self):
        buf = io.StringIO()
        with patch.object(
            cli,
            "_new_session",
            side_effect=McpError("transport error calling initialize: DNS failed"),
        ):
            with contextlib.redirect_stdout(buf):
                code = cli.cmd_scenario(
                    self._args(
                        destination="오사카",
                        period="2026-09-10~2026-09-13",
                        destination_iata="KIX",
                    )
                )

        payload = json.loads(buf.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["executed"], [])
        self.assertEqual({e["domain"] for e in payload["errors"]}, {"tnas", "stays", "flights"})
        self.assertEqual({e["stage"] for e in payload["errors"]}, {"transport"})


if __name__ == "__main__":
    unittest.main()
