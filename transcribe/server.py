#!/usr/bin/env python3
"""Speech-to-text service for Telegram voice messages.

ZeroClaw posts one audio file as multipart field ``file``.
This service returns JSON ``{"text": "..."}``.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from faster_whisper import WhisperModel

HOST = os.environ.get("TRANSCRIBE_HOST", "127.0.0.1")
PORT = int(os.environ.get("TRANSCRIBE_PORT", "8178"))
MODEL_NAME = os.environ.get("TRANSCRIBE_MODEL", "small")
DEVICE = os.environ.get("TRANSCRIBE_DEVICE", "cpu")
COMPUTE_TYPE = os.environ.get("TRANSCRIBE_COMPUTE", "int8")
CPU_THREADS = int(os.environ.get("TRANSCRIBE_CPU_THREADS", "4"))
MAX_AUDIO_BYTES = int(os.environ.get("TRANSCRIBE_MAX_AUDIO_BYTES", str(25 * 1024 * 1024)))
DOWNLOAD_ROOT = Path(
    os.environ.get(
        "TRANSCRIBE_DOWNLOAD_ROOT",
        str(Path.home() / ".cache" / "home-agent" / "whisper"),
    )
)

AUDIO_EXTENSIONS = {
    "flac",
    "mp3",
    "mpeg",
    "mpga",
    "mp4",
    "m4a",
    "ogg",
    "oga",
    "opus",
    "wav",
    "webm",
}

_model: WhisperModel | None = None
_lock = threading.Lock()


def load_model() -> WhisperModel:
    DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    print(
        f"loading model {MODEL_NAME} on {DEVICE} ({COMPUTE_TYPE})",
        flush=True,
    )
    return WhisperModel(
        MODEL_NAME,
        device=DEVICE,
        compute_type=COMPUTE_TYPE,
        cpu_threads=CPU_THREADS,
        download_root=str(DOWNLOAD_ROOT),
    )


def extension_from_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix in AUDIO_EXTENSIONS:
        return suffix
    return "ogg"


def parse_file_part(content_type: str, body: bytes) -> tuple[str, bytes]:
    """Return ``(filename, data)`` for the multipart field named ``file``."""
    marker = "boundary="
    lower = content_type.lower()
    index = lower.find(marker)
    if index < 0:
        raise ValueError("content type has no multipart boundary")
    boundary = content_type[index + len(marker) :].split(";", 1)[0].strip()
    if boundary.startswith('"') and boundary.endswith('"') and len(boundary) >= 2:
        boundary = boundary[1:-1]
    if not boundary:
        raise ValueError("multipart boundary is empty")

    delimiter = b"--" + boundary.encode("utf-8")
    for part in body.split(delimiter):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        header_blob, separator, data = part.partition(b"\r\n\r\n")
        if not separator:
            continue
        header_text = header_blob.decode("utf-8", errors="replace")
        disposition = ""
        for line in header_text.split("\r\n"):
            if line.lower().startswith("content-disposition:"):
                disposition = line.split(":", 1)[1].strip()
                break
        if 'name="file"' not in disposition and "name=file" not in disposition:
            continue
        filename = "voice.ogg"
        for item in disposition.split(";"):
            item = item.strip()
            if item.lower().startswith("filename="):
                filename = item.split("=", 1)[1].strip().strip('"')
                break
        if data.endswith(b"\r\n"):
            data = data[:-2]
        return filename, data
    raise ValueError("multipart body has no file field")


def transcribe_bytes(filename: str, audio: bytes) -> str:
    if _model is None:
        raise RuntimeError("model is not loaded")
    suffix = "." + extension_from_filename(filename)
    with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
        handle.write(audio)
        handle.flush()
        with _lock:
            segments, _info = _model.transcribe(
                handle.name,
                beam_size=1,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            return "".join(segment.text for segment in segments).strip()


class Handler(BaseHTTPRequestHandler):
    server_version = "home-agent-transcribe/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} {fmt % args}", flush=True)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/health":
            self._send(404, {"error": "not found"})
            return
        self._send(200, {"status": "ok", "model": MODEL_NAME})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/v1/transcribe":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_AUDIO_BYTES + (1024 * 1024):
            self._send(413, {"error": "audio is empty or too large"})
            return
        body = self.rfile.read(length)
        try:
            filename, audio = parse_file_part(self.headers.get("Content-Type", ""), body)
        except ValueError as error:
            self._send(400, {"error": str(error)})
            return
        if not audio or len(audio) > MAX_AUDIO_BYTES:
            self._send(413, {"error": "audio is empty or too large"})
            return
        try:
            text = transcribe_bytes(filename, audio)
        except Exception as error:  # noqa: BLE001
            print(f"transcription failed: {type(error).__name__}: {error}", flush=True)
            self._send(200, {"text": ""})
            return
        print(
            f"transcribed {len(audio)} bytes to {len(text)} characters",
            flush=True,
        )
        self._send(200, {"text": text})

    def _send(self, status: int, payload: dict[str, str]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    global _model
    _model = load_model()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"listening on http://{HOST}:{PORT}/v1/transcribe", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
