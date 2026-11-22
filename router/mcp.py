#!/usr/bin/env python3
"""MCP tools for the home Wi-Fi radios on the Xfinity gateway.

ROUTER_PASSWORD comes from the MCP server env in the ZeroClaw config.
ROUTER_URL and ROUTER_USER are optional.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from client import RouterError, set_wifi, status  # noqa: E402

PROTOCOL = "2024-11-05"
_framing = "ndjson"

TOOLS = [
    {
        "name": "wifi_status",
        "description": "Read whether the 2.4GHz and 5GHz Wi-Fi networks are on or off.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "wifi_set",
        "description": (
            "Turn a home Wi-Fi band on or off on the router. "
            "band is 2.4GHz, 5GHz, or both. enabled true turns it on. "
            "enabled false turns it off. The router refuses to turn off every band."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "band": {"type": "string", "enum": ["2.4GHz", "5GHz", "both"]},
                "enabled": {"type": "boolean"},
            },
            "required": ["band", "enabled"],
            "additionalProperties": False,
        },
    },
]


def _send(message: dict) -> None:
    body = json.dumps(message, separators=(",", ":")).encode()
    if _framing == "lsp":
        sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
    else:
        sys.stdout.buffer.write(body + b"\n")
    sys.stdout.buffer.flush()


def _read_content_length(first_line: bytes) -> dict | None:
    headers = {
        first_line.decode().split(":", 1)[0].strip().lower(): first_line.decode().split(":", 1)[1].strip()
    }
    while True:
        line = sys.stdin.buffer.readline()
        if line == b"":
            return None
        if line in (b"\r\n", b"\n"):
            break
        key, value = line.decode().split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    payload = sys.stdin.buffer.read(length)
    if len(payload) != length:
        return None
    return json.loads(payload)


def _read_message() -> dict | None:
    global _framing
    while True:
        line = sys.stdin.buffer.readline()
        if line == b"":
            return None
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith(b"content-length:"):
            _framing = "lsp"
            return _read_content_length(line)
        _framing = "ndjson"
        return json.loads(stripped)


def _result(request_id, result: dict) -> None:
    _send({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error(request_id, code: int, message: str) -> None:
    _send(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
    )


def _call(name: str, arguments: dict) -> dict:
    if name == "wifi_status":
        return status()
    band = arguments.get("band")
    enabled = arguments.get("enabled")
    if band not in ("2.4GHz", "5GHz", "both"):
        return {"confirmed": False, "error": "band must be 2.4GHz, 5GHz, or both"}
    if not isinstance(enabled, bool):
        return {"confirmed": False, "error": "enabled must be true or false"}
    return set_wifi(band, enabled)


def _handle(message: dict) -> None:
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return
    if method == "initialize":
        _result(
            request_id,
            {
                "protocolVersion": PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "router", "version": "1.0.0"},
            },
        )
        return
    if method == "ping":
        _result(request_id, {})
        return
    if method == "tools/list":
        _result(request_id, {"tools": TOOLS})
        return
    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in ("wifi_status", "wifi_set") or not isinstance(arguments, dict):
            outcome = {"confirmed": False, "error": "unknown tool"}
        else:
            try:
                outcome = _call(name, arguments)
            except (RouterError, OSError) as exc:
                outcome = {"confirmed": False, "error": str(exc)}
            except Exception as exc:  # noqa: BLE001
                outcome = {"confirmed": False, "error": f"unexpected error: {exc}"}
        _result(
            request_id,
            {
                "content": [{"type": "text", "text": json.dumps(outcome)}],
                "isError": not outcome.get("confirmed", False),
            },
        )
        return
    _error(request_id, -32601, f"Method not found: {method}")


def main() -> None:
    while True:
        message = _read_message()
        if message is None:
            return
        try:
            _handle(message)
        except Exception as exc:  # noqa: BLE001
            request_id = message.get("id")
            if request_id is not None:
                _error(request_id, -32603, str(exc))


if __name__ == "__main__":
    main()
