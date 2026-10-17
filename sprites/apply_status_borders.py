#!/usr/bin/env python3
"""Bake status borders into running/error sprite frames (and loop GIFs).

running: pink gradient comet trail around the edge
error:   flashing red ring
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Tuple

from PIL import Image

ROOT = Path(__file__).resolve().parent
SIZE = 128
BORDER = 2

PINK_HEAD = (255, 210, 240)
PINK_MID = (255, 120, 190)
PINK_TAIL = (200, 55, 130)
PINK_BASE = (88, 22, 58)
RED_ON = (255, 40, 56)
RED_OFF = (55, 10, 14)

GIF_MS = {
    "running": 480,
    "error": 480,
}

Painter = Callable[[Image.Image, int], None]
Cell = List[Tuple[int, int]]


def edge_cells(size: int = SIZE, width: int = BORDER) -> list[Cell]:
    """Clockwise border cells; each cell is `width` pixels thick at one edge step."""
    cells: list[Cell] = []
    # top L→R
    for x in range(size):
        cells.append([(x, y) for y in range(width)])
    # right T→B (skip corners already covered)
    for y in range(width, size - width):
        cells.append([(size - 1 - w, y) for w in range(width)])
    # bottom R→L
    for x in range(size - 1, -1, -1):
        cells.append([(x, size - 1 - y) for y in range(width)])
    # left B→T
    for y in range(size - 1 - width, width - 1, -1):
        cells.append([(w, y) for w in range(width)])
    return cells


CELLS = edge_cells()


def _set(px, x: int, y: int, rgb: tuple[int, int, int], mode: str) -> None:
    px[x, y] = rgb + ((255,) if mode == "RGBA" else ())


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(int(a[c] * (1.0 - t) + b[c] * t) for c in range(3))


def draw_marquee(img: Image.Image, frame_index: int, frame_count: int = 4) -> None:
    """Pink comet trail: bright head + smooth gradient fade, advancing each frame."""
    px = img.load()
    n = len(CELLS)
    trail_len = max(48, n // 3)
    head = (frame_index * (n // frame_count)) % n
    for i, cell in enumerate(CELLS):
        # Distance behind the head along the ring (0 = head).
        dist = (head - i) % n
        if dist < trail_len:
            # Head → mid → soft tail → base (smooth comet).
            t = dist / max(1, trail_len - 1)
            if t < 0.15:
                color = _lerp(PINK_HEAD, PINK_MID, t / 0.15)
            elif t < 0.55:
                color = _lerp(PINK_MID, PINK_TAIL, (t - 0.15) / 0.4)
            else:
                color = _lerp(PINK_TAIL, PINK_BASE, (t - 0.55) / 0.45)
        else:
            color = PINK_BASE
        for x, y in cell:
            _set(px, x, y, color, img.mode)


def draw_flash_red(img: Image.Image, frame_index: int) -> None:
    px = img.load()
    color = RED_ON if frame_index % 2 == 0 else RED_OFF
    for cell in CELLS:
        for x, y in cell:
            _set(px, x, y, color, img.mode)


def process_status(status: str, painter: Painter) -> None:
    folder = ROOT / status
    frames_rgb: list[Image.Image] = []
    for i in range(1, 5):
        black = folder / f"f{i}-black.png"
        img = Image.open(black).convert("RGB")
        painter(img, i - 1)
        img.save(black)
        frames_rgb.append(img.copy())

        transparent = folder / f"f{i}-transparent.png"
        if transparent.is_file():
            t = Image.open(transparent).convert("RGBA")
            painter(t, i - 1)
            t.save(transparent)

    sheet = Image.new("RGB", (SIZE * 2, SIZE * 2))
    for idx, fr in enumerate(frames_rgb):
        sheet.paste(fr, ((idx % 2) * SIZE, (idx // 2) * SIZE))
    sheet.save(folder / "sheet-2x2-bg.png")

    frames_rgb[0].save(
        folder / "loop.gif",
        save_all=True,
        append_images=frames_rgb[1:],
        duration=GIF_MS[status],
        loop=0,
        disposal=2,
    )
    print(f"{status}: updated 4 frames + loop.gif")


def main() -> int:
    # Re-apply over current frames (border pixels are overwritten each run).
    process_status("running", draw_marquee)
    process_status("error", draw_flash_red)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
