"""Voice-reply setting for the speech service.

The setting starts off. A voice message still asks for speech. This gate
refuses that request until the setting is on. One typed request can allow
the next speech request only.
"""

from __future__ import annotations

import fcntl
import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_STATE_PATH = Path(
    os.environ.get(
        "AUDIO_REPLIES_PATH",
        str(Path.home() / ".local" / "share" / "home-agent" / "audio-replies.json"),
    )
)


@dataclass
class AudioReplies:
    enabled: bool = False
    speak_next: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {"enabled": self.enabled, "speak_next": self.speak_next}


def _read(path: Path) -> AudioReplies:
    if not path.is_file():
        return AudioReplies()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AudioReplies()
    if not isinstance(payload, dict):
        return AudioReplies()
    return AudioReplies(
        enabled=payload.get("enabled") is True,
        speak_next=payload.get("speak_next") is True,
    )


def _write(path: Path, state: AudioReplies) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(state.as_dict(), separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


def _locked(path: Path, change):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with lock_path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            return change()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_state(path: Path | None = None) -> AudioReplies:
    state_path = path or DEFAULT_STATE_PATH
    return _locked(state_path, lambda: _read(state_path))


def update_state(
    *,
    enabled: bool | None = None,
    speak_next: bool | None = None,
    path: Path | None = None,
) -> AudioReplies:
    if enabled is None and speak_next is None:
        raise ValueError("enabled or speak_next is required")
    state_path = path or DEFAULT_STATE_PATH

    def change() -> AudioReplies:
        state = _read(state_path)
        if enabled is not None:
            state.enabled = enabled
        if speak_next is not None:
            state.speak_next = speak_next
        if state.enabled:
            state.speak_next = False
        _write(state_path, state)
        return state

    return _locked(state_path, change)


def claim_speech(path: Path | None = None) -> bool:
    """Return true when this speech request may proceed."""
    state_path = path or DEFAULT_STATE_PATH

    def change() -> bool:
        state = _read(state_path)
        if state.enabled:
            return True
        if not state.speak_next:
            return False
        state.speak_next = False
        _write(state_path, state)
        return True

    return _locked(state_path, change)
