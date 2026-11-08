#!/usr/bin/env python3
"""MCP tool for the voice-reply setting.

The speech service reads the same setting file. This tool changes that file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "speak"))

from gate import update_state  # noqa: E402

PROTOCOL = "2024-11-05"
_framing = "ndjson"

TOOLS = [
    {
        "name": "audio_replies",
        "description": (
            "Set voice replies for later voice messages. "
            "enabled true turns them on. enabled false turns them off. "
            "speak_next true allows one voice reply for a typed message that "
            "says answer via voice. Call this tool once for that request. "
            "Do not call it for an ordinary voice message."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "enabled": {
                    "type": "boolean",
                    "description": "Voice replies for later voice messages.",
                },
                "speak_next": {
                    "type": "boolean",
                    "description": "Allow the next speech request only.",
                },
            },
            "additionalProperties": False,
        },
    }
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


def _call(arguments: dict) -> dict:
    enabled = arguments.get("enabled")
    speak_next = arguments.get("speak_next")
    if enabled is not None and not isinstance(enabled, bool):
        return {"confirmed": False, "error": "enabled must be true or false"}
    if speak_next is not None and not isinstance(speak_next, bool):
        return {"confirmed": False, "error": "speak_next must be true or false"}
    if enabled is None and speak_next is None:
        return {"confirmed": False, "error": "enabled or speak_next is required"}
    state = update_state(enabled=enabled, speak_next=speak_next)
    return {"confirmed": True, **state.as_dict()}


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
                "serverInfo": {"name": "audio", "version": "1.0.0"},
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
        if name != "audio_replies" or not isinstance(arguments, dict):
            outcome = {"confirmed": False, "error": "unknown tool"}
        else:
            try:
                outcome = _call(arguments)
            except Exception as exc:  # noqa: BLE001
                outcome = {"confirmed": False, "error": str(exc)}
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
