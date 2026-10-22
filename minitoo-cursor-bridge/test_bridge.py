import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cursor_minitoo_bridge as bridge


class BridgeStateTests(unittest.TestCase):
    def test_valid_state_is_read_without_retaining_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(
                '{"status":"running","event":"beforeSubmitPrompt",'
                '"updated_at":"2026-10-18T00:00:00+08:00",'
                '"conversation_id":"not-used"}',
                encoding="utf-8",
            )
            state, error = bridge.read_state(path)
        self.assertIsNone(error)
        self.assertEqual(state.status, "running")
        self.assertEqual(state.event, "beforeSubmitPrompt")

    def test_stale_running_becomes_idle_without_writing_state(self):
        now = datetime(2026, 10, 18, tzinfo=timezone.utc)
        state = bridge.CursorState("running", "beforeSubmitPrompt", now - timedelta(seconds=301))
        self.assertEqual(bridge.effective_status(state, now, 300, 12), ("idle", "STALE"))

    def test_long_running_stays_running_when_stale_timeout_disabled(self):
        now = datetime(2026, 10, 18, tzinfo=timezone.utc)
        state = bridge.CursorState("running", "beforeSubmitPrompt", now - timedelta(hours=2))
        self.assertEqual(bridge.effective_status(state, now, 0, 12), ("running", "RUNNING"))

    def test_terminal_state_expires_to_idle(self):
        now = datetime(2026, 10, 18, tzinfo=timezone.utc)
        state = bridge.CursorState("completed", "stop", now - timedelta(seconds=13))
        self.assertEqual(bridge.effective_status(state, now, 300, 12), ("idle", "IDLE"))

    def test_sprite_paths_require_four_black_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "idle").mkdir()
            with self.assertRaises(RuntimeError):
                bridge.sprite_frame_paths(root, "idle")

    def test_daemon_available_is_false_for_closed_port(self):
        self.assertFalse(bridge.daemon_available("127.0.0.1", 1, timeout=0.05))


if __name__ == "__main__":
    unittest.main()
