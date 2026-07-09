"""Minimal, dependency-free MCP client for the MyRealTrip public endpoint.

Talks JSON-RPC 2.0 over HTTP POST against the Streamable-HTTP MCP transport at
``https://mcp-servers.myrealtrip.com/mcp`` (no auth). Uses only the Python
standard library (``urllib``) so the adapter runs anywhere the log hooks already
run ``python3`` — no virtualenv, no build step.

Public surface is intentionally small:

    client = McpClient()
    client.initialize()                 # handshake (captures session id if any)
    tools = client.list_tools()         # tools/list
    result = client.call_tool(name, arguments)  # tools/call

This module knows nothing about flights/stays/tnas field shapes. Response
normalization into a ScenarioFixture lives in ``core.mcp.adapters`` and is
filled in only after the sample-call validation step.
"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from .endpoints import DEFAULT_ENDPOINT, PROTOCOL_VERSION

# The MCP Streamable-HTTP transport can answer either application/json or a
# text/event-stream SSE frame. We accept both and parse accordingly.
_ACCEPT = "application/json, text/event-stream"
_DEFAULT_TIMEOUT = 30.0

# The endpoint rate-limits bursts (measured 2026-07-09: ~5-7 back-to-back
# requests → HTTP 429 {"code":"RATE_LIMITED","retryAfter":60}). One 429 must
# not kill a whole orchestration run, so we honor retryAfter a bounded number
# of times. Indirection over time.sleep keeps the wait testable.
_RATE_LIMIT_MAX_RETRIES = 2
_RATE_LIMIT_MAX_WAIT_S = 60.0
_sleep = time.sleep


def _retry_after_seconds(detail: str, headers: Any) -> float:
    """Extract the server-requested wait from a 429 response, capped."""
    wait: float | None = None
    try:
        wait = float(json.loads(detail).get("retryAfter"))
    except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
        pass
    if wait is None and headers is not None:
        try:
            wait = float(headers.get("Retry-After"))
        except (ValueError, TypeError):
            pass
    if wait is None or wait <= 0:
        wait = _RATE_LIMIT_MAX_WAIT_S
    return min(wait, _RATE_LIMIT_MAX_WAIT_S)

# Common CA-bundle locations to fall back to when the interpreter's default
# trust store is empty (e.g. python.org macOS builds that never ran
# "Install Certificates.command"). We NEVER disable verification — we only help
# a correctly-signed endpoint find a valid bundle.
_CA_BUNDLE_FALLBACKS = (
    "/etc/ssl/cert.pem",                     # macOS / BSD
    "/etc/ssl/certs/ca-certificates.crt",    # Debian/Ubuntu
    "/etc/pki/tls/certs/ca-bundle.crt",      # RHEL/Fedora
)


def _build_ssl_context() -> ssl.SSLContext:
    """Return a verifying SSL context, resolving a CA bundle if the default is empty.

    Order: honor SSL_CERT_FILE (default context already does) → certifi if
    installed → known system bundles. Verification stays ON in every branch.
    """
    context = ssl.create_default_context()
    paths = ssl.get_default_verify_paths()
    if os.environ.get("SSL_CERT_FILE") or paths.cafile or paths.capath:
        return context  # default trust store is usable
    try:
        import certifi  # optional; not a hard dependency

        context.load_verify_locations(cafile=certifi.where())
        return context
    except Exception:  # noqa: BLE001 - certifi absent or unreadable
        pass
    for bundle in _CA_BUNDLE_FALLBACKS:
        if os.path.isfile(bundle):
            context.load_verify_locations(cafile=bundle)
            return context
    return context  # last resort: default (may still fail, surfaced as McpError)


class McpError(RuntimeError):
    """Raised when the endpoint returns a JSON-RPC error or an HTTP failure.

    Carries the structured error payload (when present) so callers can record
    failure cases during validation instead of only seeing a string.
    """

    def __init__(self, message: str, *, payload: Any = None, http_status: int | None = None):
        super().__init__(message)
        self.payload = payload
        self.http_status = http_status


@dataclass
class McpClient:
    """Stateful JSON-RPC client. One instance == one logical MCP session."""

    endpoint: str = DEFAULT_ENDPOINT
    timeout: float = _DEFAULT_TIMEOUT
    session_id: str | None = None
    _next_id: int = field(default=1, repr=False)
    _ssl_context: ssl.SSLContext = field(default_factory=_build_ssl_context, repr=False)

    # -- low-level ---------------------------------------------------------

    def _post(self, method: str, params: dict[str, Any] | None, *, is_notification: bool = False) -> Any:
        """Send one JSON-RPC message; return its ``result`` (None for notifications)."""
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        if not is_notification:
            body["id"] = self._next_id
            self._next_id += 1

        raw = json.dumps(body).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": _ACCEPT,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        request = urllib.request.Request(self.endpoint, data=raw, headers=headers, method="POST")
        for attempt in range(_RATE_LIMIT_MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout, context=self._ssl_context) as response:
                    # Capture a session id handed back on initialize.
                    sid = response.headers.get("Mcp-Session-Id")
                    if sid:
                        self.session_id = sid
                    payload_text = response.read().decode("utf-8", errors="replace")
                break
            except urllib.error.HTTPError as exc:  # 4xx/5xx
                detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
                if exc.code == 429 and attempt < _RATE_LIMIT_MAX_RETRIES:
                    _sleep(_retry_after_seconds(detail, exc.headers))
                    continue
                raise McpError(
                    f"HTTP {exc.code} calling {method}: {detail[:500]}",
                    http_status=exc.code,
                ) from exc
            except urllib.error.URLError as exc:  # DNS / connection / timeout
                raise McpError(f"transport error calling {method}: {exc.reason}") from exc

        if is_notification and not payload_text.strip():
            return None
        return _extract_result(payload_text, method)

    # -- MCP handshake -----------------------------------------------------

    def initialize(self, *, client_name: str = "traveler-experience-lab", client_version: str = "0.1.0") -> Any:
        """Run the ``initialize`` handshake, then send ``notifications/initialized``."""
        result = self._post(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": client_name, "version": client_version},
            },
        )
        # Best-effort per the MCP spec; endpoint tolerates its absence.
        try:
            self._post("notifications/initialized", None, is_notification=True)
        except McpError:
            pass
        return result

    # -- tools -------------------------------------------------------------

    def list_tools(self) -> list[dict[str, Any]]:
        """Return the ``tools`` array from ``tools/list``."""
        result = self._post("tools/list", {})
        tools = result.get("tools") if isinstance(result, dict) else None
        return tools or []

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Invoke ``tools/call`` and return the raw JSON-RPC ``result``.

        The result is left unnormalized on purpose — the validation step inspects
        the real shape before ``core.mcp.adapters`` commits to a schema.
        """
        return self._post("tools/call", {"name": name, "arguments": arguments or {}})


def _extract_result(payload_text: str, method: str) -> Any:
    """Parse a JSON or SSE JSON-RPC envelope and return its ``result``.

    Raises McpError on a JSON-RPC ``error`` member or an unparseable body.
    """
    envelope = _parse_envelope(payload_text)
    if envelope is None:
        raise McpError(f"empty/unparseable response for {method}", payload=payload_text[:500])
    if "error" in envelope:
        err = envelope["error"]
        message = err.get("message") if isinstance(err, dict) else str(err)
        raise McpError(f"JSON-RPC error for {method}: {message}", payload=err)
    return envelope.get("result")


def _parse_envelope(payload_text: str) -> dict[str, Any] | None:
    """Return the JSON-RPC object from either a raw JSON body or an SSE stream."""
    text = payload_text.strip()
    if not text:
        return None
    # Plain JSON.
    if text[0] == "{":
        try:
            return json.loads(text)
        except ValueError:
            pass
    # SSE framing: lines like ``data: {...}``. Take the last data payload.
    last: dict[str, Any] | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        chunk = line[len("data:"):].strip()
        if not chunk:
            continue
        try:
            parsed = json.loads(chunk)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            last = parsed
    return last
