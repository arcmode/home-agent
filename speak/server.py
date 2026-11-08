#!/usr/bin/env python3
"""Speech service for Telegram voice replies.

ZeroClaw posts JSON ``{"input": "..."}`` to the Piper provider.
This service returns WAV audio. ZeroClaw converts that WAV to the Opus
voice note. The laptop speakers stay quiet.
"""

from __future__ import annotations

import io
import json
import os
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from piper import PiperVoice
from piper.download_voices import download_voice

from gate import claim_speech

HOST = os.environ.get("SPEAK_HOST", "127.0.0.1")
PORT = int(os.environ.get("SPEAK_PORT", "8179"))
VOICE = os.environ.get("SPEAK_VOICE", "en_US-libritts-high")
VOICE_DIR = Path(
    os.environ.get(
        "SPEAK_VOICE_DIR",
        str(Path.home() / ".cache" / "home-agent" / "piper"),
    )
)
MAX_CHARS = int(os.environ.get("SPEAK_MAX_CHARS", "4096"))

_voice: PiperVoice | None = None
_lock = threading.Lock()


def load_voice() -> PiperVoice:
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    model_path = VOICE_DIR / f"{VOICE}.onnx"
    if not model_path.is_file() or not Path(f"{model_path}.json").is_file():
        print(f"downloading voice {VOICE}", flush=True)
        download_voice(VOICE, VOICE_DIR)
    print(f"loading voice {VOICE}", flush=True)
    return PiperVoice.load(model_path)


def synthesize(text: str) -> bytes:
    if _voice is None:
        raise RuntimeError("voice is not loaded")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        with _lock:
            _voice.synthesize_wav(text, wav_file)
    return buffer.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "home-agent-speak/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} {fmt % args}", flush=True)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/health":
            self._send_json(404, {"error": "not found"})
            return
        self._send_json(200, {"status": "ok", "voice": VOICE})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/v1/audio/speech":
            self._send_json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1024 * 1024:
            self._send_json(413, {"error": "request is empty or too large"})
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._send_json(400, {"error": "request is not json"})
            return
        text = str(payload.get("input", "")).strip()
        if not text or len(text) > MAX_CHARS:
            self._send_json(400, {"error": "input is empty or too long"})
            return
        if not claim_speech():
            print("speech refused because voice replies are off", flush=True)
            self._send_json(409, {"error": {"message": "voice replies are off"}})
            return
        try:
            audio = synthesize(text)
        except Exception as error:  # noqa: BLE001
            print(f"speech failed: {type(error).__name__}: {error}", flush=True)
            self._send_json(500, {"error": "speech failed"})
            return
        if len(audio) < 44:
            self._send_json(500, {"error": "speech returned empty audio"})
            return
        print(f"spoke {len(text)} characters as {len(audio)} bytes", flush=True)
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)

    def _send_json(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    global _voice
    _voice = load_voice()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"listening on http://{HOST}:{PORT}/v1/audio/speech", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
