#!/usr/bin/env python3
"""Cursor Agent Hooks → ~/.minitoo/cursor-state.json (local status only).

Lightweight observer: parse stdin JSON, map lifecycle events to a status,
atomically write a minimal state file. No network, AI, Bluetooth, or scans.
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
import tempfile
from datetime import datetime
from typing import Any, Dict, Optional

STATE_DIR = os.path.expanduser("~/.minitoo")
STATE_FILE = os.path.join(STATE_DIR, "cursor-state.json")
LOCK_FILE = os.path.join(STATE_DIR, "cursor-state.lock")

# Events that mean "agent is actively working on a generation".
RUNNING_EVENTS = frozenset({"beforeSubmitPrompt"})

# Session boundaries → idle (no active agent task).
IDLE_EVENTS = frozenset({"sessionStart", "sessionEnd"})

# Terminal agent-loop statuses from the official `stop` hook.
STOP_STATUSES = frozenset({"completed", "aborted", "error"})


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_payload() -> Dict[str, Any]:
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def pick_str(payload: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def resolve_status(event: str, payload: Dict[str, Any]) -> Optional[str]:
    if event in RUNNING_EVENTS:
        return "running"
    if event in IDLE_EVENTS:
        return "idle"
    if event == "stop":
        status = payload.get("status")
        if isinstance(status, str) and status in STOP_STATUSES:
            return status
        return None
    return None


def build_state(event: str, status: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "status": status,
        "updated_at": now_iso(),
        "event": event,
    }
    conversation_id = pick_str(payload, "conversation_id", "session_id")
    if conversation_id is not None:
        state["conversation_id"] = conversation_id
    generation_id = pick_str(payload, "generation_id")
    if generation_id is not None:
        state["generation_id"] = generation_id
    return state


def atomic_write(state: Dict[str, Any]) -> None:
    os.makedirs(STATE_DIR, mode=0o755, exist_ok=True)
    # Exclusive lock across concurrent hook invocations.
    with open(LOCK_FILE, "a+", encoding="utf-8") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        try:
            fd, tmp_path = tempfile.mkstemp(
                prefix=".cursor-state.",
                suffix=".tmp",
                dir=STATE_DIR,
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as out:
                    json.dump(state, out, ensure_ascii=False, separators=(",", ":"))
                    out.write("\n")
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(tmp_path, STATE_FILE)
                os.chmod(STATE_FILE, 0o644)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


def emit_response(event: str) -> None:
    # beforeSubmitPrompt can block submission; always allow and stay silent otherwise.
    if event == "beforeSubmitPrompt":
        sys.stdout.write('{"continue":true}\n')
    else:
        # stop / session* expect JSON or empty object; never emit followup_message.
        sys.stdout.write("{}\n")


def main() -> int:
    payload = read_payload()
    event = pick_str(payload, "hook_event_name") or ""
    status = resolve_status(event, payload) if event else None

    if status is not None:
        try:
            atomic_write(build_state(event, status, payload))
        except OSError:
            # Fail open: never break the agent loop on filesystem errors.
            pass

    emit_response(event)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # Absolute fail-open for any unexpected error.
        try:
            sys.stdout.write("{}\n")
        except Exception:
            pass
        raise SystemExit(0)
