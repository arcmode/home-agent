"""Tests for the voice-reply gate."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gate import claim_speech, load_state, update_state


class GateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "audio-replies.json"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_missing_file_starts_off(self) -> None:
        state = load_state(self.path)
        self.assertFalse(state.enabled)
        self.assertFalse(claim_speech(self.path))

    def test_enabled_allows_every_request(self) -> None:
        update_state(enabled=True, path=self.path)
        self.assertTrue(claim_speech(self.path))
        self.assertTrue(claim_speech(self.path))

    def test_speak_next_allows_one_request_while_off(self) -> None:
        update_state(speak_next=True, path=self.path)
        self.assertTrue(claim_speech(self.path))
        self.assertFalse(claim_speech(self.path))
        self.assertFalse(load_state(self.path).speak_next)

    def test_enabled_clears_speak_next(self) -> None:
        update_state(enabled=False, speak_next=True, path=self.path)
        state = update_state(enabled=True, path=self.path)
        self.assertTrue(state.enabled)
        self.assertFalse(state.speak_next)

    def test_update_requires_a_field(self) -> None:
        with self.assertRaises(ValueError):
            update_state(path=self.path)


if __name__ == "__main__":
    unittest.main()
