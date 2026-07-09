"""Rate-limit (HTTP 429) retry behavior of McpClient._post.

Runs with stdlib only (no pytest required):

    python3 -m unittest discover -s tests

Guards, motivated by the 2026-07-09 live probe (~5-7 back-to-back requests →
429 {"code":"RATE_LIMITED","retryAfter":60}):
  * A transient 429 mid-orchestration is retried after the server-requested
    wait instead of killing the whole run.
  * A persistent 429 still surfaces as McpError(http_status=429) after the
    bounded retries — no infinite loop.
  * retryAfter comes from the JSON body first, the Retry-After header second,
    and is always capped at _RATE_LIMIT_MAX_WAIT_S.
"""
from __future__ import annotations

import contextlib
import io
import json
import unittest
import urllib.error
from email.message import Message
from unittest.mock import patch

from core.mcp import client as client_mod
from core.mcp.client import McpClient, McpError, _retry_after_seconds

_RPC_OK = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})


def _http_429(body: dict | None, headers: dict[str, str] | None = None) -> urllib.error.HTTPError:
    hdrs = Message()
    for k, v in (headers or {}).items():
        hdrs[k] = v
    raw = json.dumps(body).encode() if body is not None else b""
    return urllib.error.HTTPError("https://x", 429, "Too Many Requests", hdrs, io.BytesIO(raw))


class _FakeResponse:
    headers = Message()

    def read(self) -> bytes:
        return _RPC_OK.encode()

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class RetryAfterParsing(unittest.TestCase):
    def test_body_json_wins(self) -> None:
        self.assertEqual(_retry_after_seconds('{"retryAfter": 7}', None), 7.0)

    def test_header_fallback(self) -> None:
        hdrs = Message()
        hdrs["Retry-After"] = "12"
        self.assertEqual(_retry_after_seconds("not json", hdrs), 12.0)

    def test_default_and_cap(self) -> None:
        self.assertEqual(_retry_after_seconds("", None), client_mod._RATE_LIMIT_MAX_WAIT_S)
        self.assertEqual(
            _retry_after_seconds('{"retryAfter": 999}', None),
            client_mod._RATE_LIMIT_MAX_WAIT_S,
        )


class RateLimitRetry(unittest.TestCase):
    def test_transient_429_recovers(self) -> None:
        """First call 429 with retryAfter=3 → sleep(3) → second call succeeds."""
        outcomes = [_http_429({"retryAfter": 3}), _FakeResponse()]

        def fake_urlopen(*args: object, **kwargs: object) -> _FakeResponse:
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        sleeps: list[float] = []
        with patch.object(client_mod.urllib.request, "urlopen", side_effect=fake_urlopen), \
                patch.object(client_mod, "_sleep", sleeps.append):
            result = McpClient().call_tool("getCurrentTime", {})
        self.assertEqual(result, {"ok": True})
        self.assertEqual(sleeps, [3.0])

    def test_persistent_429_raises_after_bounded_retries(self) -> None:
        calls = {"n": 0}

        def always_429(*args: object, **kwargs: object) -> None:
            calls["n"] += 1
            raise _http_429({"retryAfter": 1})

        sleeps: list[float] = []
        with patch.object(client_mod.urllib.request, "urlopen", side_effect=always_429), \
                patch.object(client_mod, "_sleep", sleeps.append):
            with self.assertRaises(McpError) as ctx:
                McpClient().call_tool("getCurrentTime", {})
        self.assertEqual(ctx.exception.http_status, 429)
        self.assertEqual(calls["n"], client_mod._RATE_LIMIT_MAX_RETRIES + 1)
        self.assertEqual(len(sleeps), client_mod._RATE_LIMIT_MAX_RETRIES)

    def test_non_429_is_not_retried(self) -> None:
        calls = {"n": 0}

        def raise_500(*args: object, **kwargs: object) -> None:
            calls["n"] += 1
            hdrs = Message()
            raise urllib.error.HTTPError("https://x", 500, "boom", hdrs, io.BytesIO(b"{}"))

        with patch.object(client_mod.urllib.request, "urlopen", side_effect=raise_500):
            with self.assertRaises(McpError) as ctx:
                McpClient().call_tool("getCurrentTime", {})
        self.assertEqual(ctx.exception.http_status, 500)
        self.assertEqual(calls["n"], 1)


if __name__ == "__main__":  # pragma: no cover
    with contextlib.suppress(SystemExit):
        unittest.main()
