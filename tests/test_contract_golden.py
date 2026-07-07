"""Golden tests locking the ProductCandidate contract + failure handling.

Runs with stdlib only (no pytest required):

    python3 -m unittest discover -s tests

Guards, in order of the review that motivated them:
  * Error envelopes (isError / business / -32602) MUST surface as McpToolError —
    prevents the P2-2 regression where a failure was reported green.
  * Successful fixtures MUST normalize into contract-valid candidates.
  * De-dup + domain invariants hold.
  * Stored drift hash MUST match a recompute — catches silent upstream change
    or fixture tampering.
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
from core.mcp.adapters import McpToolError, normalize, raw_sha256
from core.mcp.client import McpError
from core.schema.scenario_fixture import (
    DOMAINS,
    Price,
    ProductCandidate,
    SourceRef,
    dedupe_candidates,
    validate_candidate,
)

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The known error fixtures and the failure mode each must exercise.
_ERROR_FIXTURES = {
    "searchInternationalFlights.sample3.json": "business",
    "searchStays.sample2.json": "validation",
}


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _is_mcp_call_fixture(path: str) -> bool:
    # fixtures/ also holds non-MCP datasets (e.g. voc/); the contract goldens
    # only apply to recorded tools/call envelopes.
    rec = _load(path)
    return isinstance(rec, dict) and "tool" in rec and "result" in rec


_FIXTURES = sorted(
    p
    for p in glob.glob(os.path.join(_REPO, "fixtures", "*", "*.json"))
    if _is_mcp_call_fixture(p)
)


def _is_error_fixture(path: str) -> bool:
    return os.path.basename(path) in _ERROR_FIXTURES


class ErrorEnvelopeGolden(unittest.TestCase):
    def test_error_fixtures_raise_with_expected_kind(self):
        for name, kind in _ERROR_FIXTURES.items():
            matches = [p for p in _FIXTURES if os.path.basename(p) == name]
            self.assertTrue(matches, f"missing error fixture {name}")
            rec = _load(matches[0])
            with self.assertRaises(McpToolError, msg=f"{name} should raise") as ctx:
                normalize(rec["tool"], rec.get("arguments", {}), rec["result"])
            self.assertEqual(ctx.exception.kind, kind, f"{name} wrong failure kind")

    def test_error_fixtures_flagged_not_ok(self):
        for name in _ERROR_FIXTURES:
            rec = _load([p for p in _FIXTURES if os.path.basename(p) == name][0])
            self.assertFalse(rec.get("ok"), f"{name} must be recorded ok=False")
            self.assertEqual(rec["_meta"]["source_type"], "error")


class SuccessNormalizationGolden(unittest.TestCase):
    def test_success_fixtures_yield_valid_candidates(self):
        for path in _FIXTURES:
            if _is_error_fixture(path):
                continue
            rec = _load(path)
            cands = normalize(rec["tool"], rec.get("arguments", {}), rec["result"])
            for c in cands:
                validate_candidate(c)  # raises on any contract breach
                self.assertIn(c.domain, DOMAINS)

    def test_raw_preserves_source_not_derived(self):
        # Contract §raw: raw holds the upstream object / source slice, never a
        # re-synthesized dict of already-parsed fields.
        for path in _FIXTURES:
            if _is_error_fixture(path):
                continue
            rec = _load(path)
            for c in normalize(rec["tool"], rec.get("arguments", {}), rec["result"]):
                self.assertIsNotNone(c.raw, f"{path}: raw is None")
                if c.domain == "tnas" and rec["tool"] == "searchTnas":
                    # Source slice: verbatim copy_text block containing the title.
                    self.assertIn("copy_text_block", c.raw)
                    stem = c.title.split("]")[-1].strip()[:6]
                    self.assertIn(stem, c.raw["copy_text_block"], f"{path}: raw not source slice")

    def test_candidates_are_deduped(self):
        for path in _FIXTURES:
            if _is_error_fixture(path):
                continue
            rec = _load(path)
            cands = normalize(rec["tool"], rec.get("arguments", {}), rec["result"])
            self.assertEqual(cands, dedupe_candidates(cands), f"{path} not deduped")


class ContractInvariants(unittest.TestCase):
    def test_bad_domain_rejected(self):
        with self.assertRaises(ValueError):
            ProductCandidate(domain="hotels")  # type: ignore[arg-type]

    def test_source_required_by_validate(self):
        with self.assertRaises(ValueError):
            validate_candidate(ProductCandidate(domain="stays", raw={}))


class DriftDetectionGolden(unittest.TestCase):
    def test_stored_hash_matches_recompute(self):
        for path in _FIXTURES:
            rec = _load(path)
            meta = rec.get("_meta")
            self.assertIsNotNone(meta, f"{path} missing _meta")
            self.assertEqual(
                raw_sha256(rec["result"]),
                meta["raw_sha256"],
                f"{path}: raw payload drift — hash mismatch",
            )


class CliSurfaceContract(unittest.TestCase):
    """Lock the ADR-0001 CLI split so a refactor cannot quietly erode it."""

    def test_canonical_and_debug_subcommands_exist(self):
        parser = cli.build_parser()
        actions = [a for a in parser._actions if a.dest == "command"]
        self.assertTrue(actions, "no subcommand group")
        choices = set(actions[0].choices)
        # Canonical data path + debugging surfaces must all remain present.
        for name in ("fetch", "probe", "call", "list-tools", "list-tools-raw"):
            self.assertIn(name, choices, f"CLI lost subcommand {name}")

    def test_candidate_dict_drops_raw_by_default(self):
        c = ProductCandidate(
            domain="stays",
            title="X",
            source=SourceRef(tool="searchStays", arguments={}),
            raw={"big": "payload"},
        )
        self.assertNotIn("raw", cli._candidate_dict(c, include_raw=False))
        self.assertIn("raw", cli._candidate_dict(c, include_raw=True))

    def test_candidate_dict_keeps_normalized_fields(self):
        c = ProductCandidate(
            domain="tnas",
            title="USJ",
            price=Price(text="84,000원~"),
            source=SourceRef(tool="searchTnas", arguments={"query": "오사카"}),
            raw={},
        )
        row = cli._candidate_dict(c, include_raw=False)
        self.assertEqual(row["title"], "USJ")
        self.assertEqual(row["price"]["text"], "84,000원~")
        self.assertEqual(row["source"]["tool"], "searchTnas")

    def test_fetch_session_failure_is_structured_json(self):
        args = argparse.Namespace(tool="searchTnas", args='{"query":"오사카"}', with_raw=False)
        buf = io.StringIO()
        with patch.object(
            cli,
            "_new_session",
            side_effect=McpError("transport error calling initialize: DNS failed"),
        ):
            with contextlib.redirect_stdout(buf):
                code = cli.cmd_fetch(args)

        self.assertEqual(code, 1)
        payload = json.loads(buf.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["stage"], "transport")
        self.assertEqual(payload["command"], "fetch")
        self.assertEqual(payload["tool"], "searchTnas")


if __name__ == "__main__":
    unittest.main()
