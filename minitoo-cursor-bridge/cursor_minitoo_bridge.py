#!/usr/bin/env python3
"""Display Cursor's local hook state on a Divoom MiniToo.

This program is deliberately outside Cursor's process.  It polls the small
state file written by the Hook, then sends the matching character sprite
animation through the reused Divoom daemon/sender.  It never reads prompts
or conversations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

VALID_STATUSES = frozenset({"idle", "running", "completed", "aborted", "error"})
DEFAULT_STATE_PATH = Path("~/.minitoo/cursor-state.json").expanduser()
DEFAULT_FRAME_DIR = Path("~/.minitoo/cursor-frames").expanduser()
DEFAULT_SPRITES_DIR = Path(__file__).resolve().parent.parent / "sprites"
FRAME_SPEED_MS = {
    "idle": 480,
    "running": 480,
    "completed": 450,
    "aborted": 480,
    "error": 480,
}


@dataclass(frozen=True)
class CursorState:
    status: str
    event: str
    updated_at: datetime


def parse_timestamp(value: object) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def read_state(path: Path) -> Tuple[Optional[CursorState], Optional[str]]:
    """Return a validated minimal state, or a safe error string."""
    try:
        raw = path.read_bytes()
        data = json.loads(raw)
    except FileNotFoundError:
        return None, "state file does not exist yet"
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, "state file is temporarily unreadable: {}".format(type(exc).__name__)

    if not isinstance(data, dict):
        return None, "state root is not an object"
    status = data.get("status")
    event = data.get("event")
    updated_at = parse_timestamp(data.get("updated_at"))
    if status not in VALID_STATUSES:
        return None, "state has an unknown status"
    if not isinstance(event, str) or not event:
        return None, "state has no event"
    if updated_at is None:
        return None, "state has no timezone-aware updated_at"
    return CursorState(status=status, event=event, updated_at=updated_at), None


def effective_status(
    state: CursorState, now: datetime, stale_after: float, terminal_hold: float
) -> Tuple[str, str]:
    """Map one Hook state to a display state without rewriting the state file."""
    age = max(0.0, (now - state.updated_at).total_seconds())
    if state.status == "running" and age >= stale_after:
        return "idle", "STALE"
    if state.status in {"completed", "aborted", "error"} and age >= terminal_hold:
        return "idle", "IDLE"
    return state.status, state.status.upper()


def display_fingerprint(status: str, label: str) -> str:
    return hashlib.sha256((status + "\0" + label).encode("ascii")).hexdigest()


def sprite_frame_paths(sprites_dir: Path, status: str) -> List[Path]:
    folder = sprites_dir / status
    paths = [folder / "f{}-black.png".format(i) for i in range(1, 5)]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        raise RuntimeError("missing sprite frames: {}".format(", ".join(missing)))
    return paths


def load_sender_module(sender: Path):
    tools_dir = str(sender.expanduser().resolve().parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import divoom_send  # type: ignore
    import send_divoom_image  # type: ignore

    return divoom_send, send_divoom_image


def build_animation_packets(
    send_divoom_image,
    frame_paths: List[Path],
    speed_ms: int,
) -> bytes:
    from PIL import Image

    frames = [
        Image.open(path).convert("RGB").tobytes("raw", "RGB") for path in frame_paths
    ]
    payload = send_divoom_image._animation_payload(
        frames, size=128, speed=speed_ms, level=17, window_log=17
    )
    packets = send_divoom_image.build_packets(payload)
    buf = bytearray()
    for packet in packets:
        buf += len(packet).to_bytes(2, "little") + packet
    return bytes(buf)


def send_status_animation(
    sender: Path,
    sprites_dir: Path,
    status: str,
    packet_dir: Path,
    dry_run: bool,
    host: str = "127.0.0.1",
    port: int = 40583,
) -> Dict[str, object]:
    divoom_send, send_divoom_image = load_sender_module(sender)
    frame_paths = sprite_frame_paths(sprites_dir, status)
    packet_bytes = build_animation_packets(
        send_divoom_image, frame_paths, FRAME_SPEED_MS.get(status, 480)
    )
    packet_dir.mkdir(parents=True, exist_ok=True)
    packet_path = packet_dir / "{}-packets-lenpref.bin".format(status)
    packet_path.write_bytes(packet_bytes)
    # Keep a still preview of frame 1 for debugging without storing prompts.
    preview = packet_dir.parent / "cursor-status.png"
    from PIL import Image

    Image.open(frame_paths[0]).convert("RGB").save(preview, format="PNG")

    if dry_run:
        return {"ok": True, "dry_run": True, "packets": str(packet_path)}
    return divoom_send.submit(host, port, packet_path, 0.012, False)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read Cursor Hook state and update MiniToo through sprite animations."
    )
    parser.add_argument("--sender", type=Path, required=True, help="path to reused divoom_send.py")
    parser.add_argument("--sprites-dir", type=Path, default=DEFAULT_SPRITES_DIR)
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--frame-dir", type=Path, default=DEFAULT_FRAME_DIR)
    parser.add_argument("--interval", type=float, default=0.75, help="poll interval in seconds")
    parser.add_argument("--stale-after", type=float, default=300.0, help="running age treated as stale")
    parser.add_argument("--terminal-hold", type=float, default=12.0, help="seconds to show terminal status")
    parser.add_argument("--once", action="store_true", help="send exactly one state, then exit")
    parser.add_argument("--dry-run", action="store_true", help="build packets only; never contact the daemon")
    args = parser.parse_args()

    if args.interval <= 0 or args.stale_after <= 0 or args.terminal_hold < 0:
        parser.error("interval and stale-after must be positive; terminal-hold cannot be negative")

    state_path = args.state_path.expanduser()
    frame_dir = args.frame_dir.expanduser()
    sprites_dir = args.sprites_dir.expanduser()
    sender = args.sender.expanduser()
    last_fingerprint: Optional[str] = None
    last_problem: Optional[str] = None

    while True:
        try:
            state, error = read_state(state_path)
            if error:
                if error != last_problem:
                    print("bridge: {}".format(error), file=sys.stderr)
                    last_problem = error
            else:
                assert state is not None
                status, label = effective_status(
                    state, datetime.now().astimezone(), args.stale_after, args.terminal_hold
                )
                fingerprint = display_fingerprint(status, label)
                if fingerprint != last_fingerprint:
                    resp = send_status_animation(
                        sender=sender,
                        sprites_dir=sprites_dir,
                        status=status,
                        packet_dir=frame_dir / "packets",
                        dry_run=args.dry_run,
                    )
                    if not resp.get("ok"):
                        raise RuntimeError("daemon rejected send: {}".format(resp))
                    print(
                        "bridge: displayed {}{}".format(
                            label, " (dry run)" if args.dry_run else ""
                        )
                    )
                    last_fingerprint = fingerprint
                last_problem = None
        except (OSError, RuntimeError, socket.error) as exc:
            message = "bridge: {}".format(exc)
            if message != last_problem:
                print(message, file=sys.stderr)
                last_problem = message

        if args.once:
            return 0 if last_problem is None else 1
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
