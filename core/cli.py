"""Adapter CLI — the single canonical data path both runtimes shell out to.

Two surfaces, deliberately separated per ADR 0001:

  DATA PATH (canonical — produces normalized ScenarioFixture material):
    python3 -m core.cli fetch searchTnas --args '{"query": "오사카"}'   # -> candidates
    python3 -m core.cli probe --samples <samples.json>                  # sweep -> fixtures/

  DEBUGGING ONLY (raw shapes; MUST NOT be used to build ScenarioFixture):
    python3 -m core.cli list-tools            # tools/list (compact)
    python3 -m core.cli list-tools-raw        # inputSchema
    python3 -m core.cli call <tool> --args '{...}'   # raw JSON-RPC result

Design notes:
  * stdlib only; safe to invoke from the Claude Code / Codex command layer.
  * ``fetch`` runs the adapter normalizer so callers consume ProductCandidate
    rows, never raw payloads — this is what enforces the "single canonical path".
  * ``call`` prints the raw result for humans inspecting shapes; the ``_debug``
    marker in its output signals it is not a ScenarioFixture source.
  * ``probe`` persists each call's request + result (+ drift ``_meta``) as a
    fixture, the evidence base for the schema.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dataclasses import asdict
from datetime import datetime, timezone

from .mcp.adapters import McpToolError, fingerprint, normalize, unwrap
from .mcp.client import McpClient, McpError
from .mcp.endpoints import DOMAIN_TOOLS
from .scenario import DEFAULT_ADULTS, FetchError, ScenarioInputs, ScenarioResult, orchestrate


def _new_session() -> McpClient:
    client = McpClient()
    client.initialize()
    return client


def _open_session(command: str, *, tool: str | None = None) -> McpClient | None:
    """Open an MCP session or print a structured transport failure."""
    try:
        return _new_session()
    except McpError as exc:
        payload: dict[str, Any] = {
            "ok": False,
            "stage": "transport",
            "command": command,
            "error": str(exc),
        }
        if tool:
            payload["tool"] = tool
        if exc.http_status is not None:
            payload["http_status"] = exc.http_status
        if exc.payload is not None:
            payload["payload"] = exc.payload
        _print_json(payload)
        return None


def _print_json(obj: Any) -> None:
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def cmd_list_tools(_: argparse.Namespace) -> int:
    client = _open_session("list-tools")
    if client is None:
        return 1
    tools = client.list_tools()
    # Compact index: name + one-line description; full schema stays in --raw.
    summary = [{"name": t.get("name"), "description": t.get("description")} for t in tools]
    _print_json({"count": len(tools), "tools": summary})
    return 0


def cmd_list_tools_raw(_: argparse.Namespace) -> int:
    client = _open_session("list-tools-raw")
    if client is None:
        return 1
    _print_json(client.list_tools())
    return 0


def cmd_call(args: argparse.Namespace) -> int:
    """DEBUG ONLY: print the raw JSON-RPC result. Not a ScenarioFixture source."""
    arguments = json.loads(args.args) if args.args else {}
    client = _open_session("call", tool=args.tool)
    if client is None:
        return 1
    try:
        result = client.call_tool(args.tool, arguments)
    except McpError as exc:
        _print_json({"ok": False, "tool": args.tool, "error": str(exc), "payload": exc.payload})
        return 1
    # ``_debug`` flags that this raw output must not be normalized by hand — use
    # ``fetch`` for the canonical, adapter-normalized data path (ADR 0001).
    _print_json({
        "_debug": "raw result — do NOT build ScenarioFixture from this; use `fetch`",
        "ok": True,
        "tool": args.tool,
        "arguments": arguments,
        "result": result,
    })
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    """CANONICAL DATA PATH: call a tool and return adapter-normalized candidates.

    This is the only supported way to turn MCP responses into ScenarioFixture
    material. Tool-level error envelopes surface as a structured failure (not a
    green result), matching the probe's behavior.
    """
    arguments = json.loads(args.args) if args.args else {}
    client = _open_session("fetch", tool=args.tool)
    if client is None:
        return 1
    try:
        result = client.call_tool(args.tool, arguments)
    except McpError as exc:
        _print_json({"ok": False, "stage": "transport", "tool": args.tool, "error": str(exc)})
        return 1
    try:
        candidates = normalize(args.tool, arguments, result)
    except McpToolError as exc:
        _print_json({
            "ok": False,
            "stage": "tool",
            "tool": args.tool,
            "kind": exc.kind,
            "error": str(exc),
            "_meta": fingerprint(result),
        })
        return 1
    rows = [_candidate_dict(c, include_raw=args.with_raw) for c in candidates]
    _print_json({
        "ok": True,
        "tool": args.tool,
        "arguments": arguments,
        "count": len(rows),
        "candidates": rows,
        "_meta": fingerprint(result),
    })
    return 0


def _candidate_dict(candidate: Any, *, include_raw: bool) -> dict[str, Any]:
    """Serialize a ProductCandidate; drop the bulky ``raw`` unless requested."""
    data = asdict(candidate)
    if not include_raw:
        data.pop("raw", None)
    return data


def _live_fetcher(
    client: McpClient | None = None,
    response_meta: list[dict[str, Any]] | None = None,
):
    """A Fetcher backed by a lazily opened live session.

    This is the network edge — it wraps the SAME ``call_tool`` + ``normalize``
    canonical path ``fetch`` uses (ADR 0001), translating transport and tool
    errors into the orchestrator's ``FetchError`` so one dead call is recorded,
    not fatal. When ``response_meta`` is provided, it records one fingerprint per
    raw MCP result so scenario output can be drift-checked like ``fetch``/``probe``.
    """
    live_client = client

    def fetch(tool: str, arguments: dict) -> list[Any]:
        nonlocal live_client
        if live_client is None:
            try:
                live_client = _new_session()
            except McpError as exc:
                raise FetchError(str(exc), stage="transport") from exc
        try:
            result = live_client.call_tool(tool, arguments)
        except McpError as exc:
            raise FetchError(str(exc), stage="transport") from exc
        if response_meta is not None:
            response_meta.append({
                "tool": tool,
                "arguments": dict(arguments),
                **fingerprint(result),
            })
        try:
            return normalize(tool, arguments, result)
        except McpToolError as exc:
            raise FetchError(f"{exc.kind}: {exc}", stage="tool") from exc

    return fetch


def cmd_scenario(args: argparse.Namespace) -> int:
    """Orchestrate a full scenario: plan → fetch (canonical) → assemble fixture.

    Wraps the scenario package's ``orchestrate`` with a live fetcher so the
    command layer (Claude Code / Codex) gets one call instead of hand-assembling
    many ``fetch`` outputs. Prints the ScenarioFixture plus an execution trace
    (executed / skipped / errors).
    """
    warnings: list[str] = []
    adults = args.adults
    if adults is None:
        # Silent party-size defaults poisoned a solo-traveler smoke run (F-1,
        # docs/pilot/2026-07-07-plugin-smoke.md): surface the assumption so the
        # command layer maps the companions brief to --adults instead.
        adults = DEFAULT_ADULTS
        warnings.append(
            f"adults not specified; defaulted to {DEFAULT_ADULTS} — "
            "pass --adults matching the companions brief"
        )
    inputs = ScenarioInputs(
        destination=args.destination,
        period=args.period,
        budget=args.budget,
        companions=args.companions,
        persona=args.persona,
        origin=args.origin,
        destination_iata=args.destination_iata,
        check_in=args.check_in,
        check_out=args.check_out,
        depart_date=args.depart_date,
        return_date=args.return_date,
        adults=adults,
    )
    response_meta: list[dict[str, Any]] = []
    result = orchestrate(inputs, _live_fetcher(response_meta=response_meta))
    _print_json(
        _result_dict(
            result,
            include_raw=args.with_raw,
            response_meta=response_meta,
            warnings=warnings,
        )
    )
    # Red when every planned call errored (and at least one was planned) — a
    # scenario with no usable ground truth is a failure, not a thin success.
    planned = len(result.executed) + len(result.errors)
    return 1 if planned and not result.executed else 0


def _result_dict(
    result: ScenarioResult,
    *,
    include_raw: bool,
    response_meta: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    fx = result.fixture
    out = {
        "ok": not (result.errors and not result.executed),
        "fixture": {
            "destination": fx.destination,
            "period": fx.period,
            "budget": fx.budget,
            "companions": fx.companions,
            "persona": fx.persona,
            "edge_cases": fx.edge_cases,
            "candidates": [_candidate_dict(c, include_raw=include_raw) for c in fx.candidates],
            "sources": [asdict(s) for s in fx.sources],
            "schema_version": fx.schema_version,
        },
        "executed": [{"domain": c.domain, "tool": c.tool, "arguments": c.arguments} for c in result.executed],
        "skipped": [{"domain": s.domain, "tool": s.tool, "missing": list(s.missing)} for s in result.skipped],
        "errors": [{"domain": e.domain, "tool": e.tool, "stage": e.stage, "error": e.error} for e in result.errors],
    }
    if response_meta is not None:
        out["_meta"] = {"responses": response_meta}
    if warnings:
        out.setdefault("_meta", {})["warnings"] = warnings
    return out


def cmd_probe(args: argparse.Namespace) -> int:
    """Run the sample sweep and write one fixture per (tool, sample) call.

    Sample arguments come from ``--samples`` (a JSON file), so the harness stays
    data-driven and no field values are hardcoded in code. Missing samples are
    skipped with a note rather than guessed.
    """
    out_root = Path(args.out)
    samples = _load_samples(args.samples)
    client = _open_session("probe")
    if client is None:
        return 1
    report: list[dict[str, Any]] = []

    for domain, tools in DOMAIN_TOOLS.items():
        for tool in tools:
            for i, arguments in enumerate(samples.get(tool, []), start=1):
                entry = _run_and_save(client, out_root, domain, tool, i, arguments)
                report.append(entry)

    _print_json({"probed": len(report), "results": report})
    return 0 if all(r["ok"] for r in report) else 1


def _run_and_save(
    client: McpClient, out_root: Path, domain: str, tool: str, index: int, arguments: dict[str, Any]
) -> dict[str, Any]:
    dest_dir = out_root / domain
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{tool}.sample{index}.json"
    record: dict[str, Any] = {"domain": domain, "tool": tool, "arguments": arguments}
    try:
        result = client.call_tool(tool, arguments)
        tool_error = _tool_error(result)
        if tool_error is None:
            record.update(ok=True, result=result)
        else:
            # Transport succeeded but the tool returned an error envelope
            # (result.isError). Report it as a failure so automation sees red.
            record.update(ok=False, tool_error=tool_error, result=result)
        # Drift metadata: hash + source type + normalizer version. Error
        # envelopes are fingerprinted too (they are valid golden cases).
        record["_meta"] = {**fingerprint(result), "probed_at": _now_iso()}
    except McpError as exc:
        record.update(ok=False, error=str(exc), http_status=exc.http_status, payload=exc.payload)
    dest.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": record["ok"],
        "tool": tool,
        "file": str(dest),
        "error": record.get("error") or record.get("tool_error"),
    }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tool_error(result: Any) -> str | None:
    """Return a short message when ``result`` is a tool-level error envelope.

    Reuses the two-failure-mode logic in ``adapters.unwrap`` (business error /
    MCP validation error) so the probe and the normalizer agree on what counts
    as a failure. Returns None when the tool succeeded.
    """
    try:
        unwrap(result)
        return None
    except McpToolError as exc:
        return f"{exc.kind}: {exc}"


def _load_samples(path: str | None) -> dict[str, list[dict[str, Any]]]:
    if not path:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="core.cli", description="MRT MCP adapter CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-tools", help="tools/list (compact)").set_defaults(func=cmd_list_tools)
    sub.add_parser("list-tools-raw", help="tools/list (full schemas)").set_defaults(func=cmd_list_tools_raw)

    p_call = sub.add_parser("call", help="DEBUG: raw tools/call result (not a fixture source)")
    p_call.add_argument("tool")
    p_call.add_argument("--args", help="JSON object of tool arguments", default=None)
    p_call.set_defaults(func=cmd_call)

    p_fetch = sub.add_parser("fetch", help="CANONICAL: tools/call -> normalized candidates")
    p_fetch.add_argument("tool")
    p_fetch.add_argument("--args", help="JSON object of tool arguments", default=None)
    p_fetch.add_argument("--with-raw", action="store_true", help="include each candidate's raw payload")
    p_fetch.set_defaults(func=cmd_fetch)

    p_probe = sub.add_parser("probe", help="domain sample sweep -> fixtures")
    p_probe.add_argument("--out", default="fixtures", help="fixtures output root")
    p_probe.add_argument("--samples", default=None, help="JSON file: {tool: [args, ...]}")
    p_probe.set_defaults(func=cmd_probe)

    p_scenario = sub.add_parser(
        "scenario", help="CANONICAL: plan+fetch+assemble a grounded ScenarioFixture"
    )
    p_scenario.add_argument("--destination", default=None, help="anchor place name (e.g. 오사카)")
    p_scenario.add_argument("--period", default=None, help="free text; ISO dates parsed for stays/flights")
    p_scenario.add_argument("--budget", default=None)
    p_scenario.add_argument("--companions", default=None)
    p_scenario.add_argument("--persona", default=None)
    p_scenario.add_argument("--origin", default="ICN", help="departure IATA (flights)")
    p_scenario.add_argument("--destination-iata", default=None, help="destination IATA (flights)")
    p_scenario.add_argument("--check-in", default=None, help="YYYY-MM-DD")
    p_scenario.add_argument("--check-out", default=None, help="YYYY-MM-DD")
    p_scenario.add_argument("--depart-date", default=None, help="YYYY-MM-DD (flights)")
    p_scenario.add_argument("--return-date", default=None, help="YYYY-MM-DD (flights)")
    p_scenario.add_argument(
        "--adults",
        type=int,
        default=None,
        help=f"성인 인원 — 동행자 브리프에서 파악해 반드시 지정 (미지정 시 {DEFAULT_ADULTS} + _meta.warnings)",
    )
    p_scenario.add_argument("--with-raw", action="store_true", help="include each candidate's raw payload")
    p_scenario.set_defaults(func=cmd_scenario)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
