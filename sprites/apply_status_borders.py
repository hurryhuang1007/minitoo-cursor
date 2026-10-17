#!/usr/bin/env python3
"""Bake status borders into running/error sprite frames (and loop GIFs).

running: pink/white dashed marquee around the edge
error:   flashing red ring
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Tuple

from PIL import Image

ROOT = Path(__file__).resolve().parent
SIZE = 128
BORDER = 2

PINK = (255, 120, 190)
WHITE = (255, 255, 255)
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
    for x in range(size):
        cells.append([(x, y) for y in range(width)])
    for y in range(width, size - width):
        cells.append([(size - 1 - w, y) for w in range(width)])
    for x in range(size - 1, -1, -1):
        cells.append([(x, size - 1 - y) for y in range(width)])
    for y in range(size - 1 - width, width - 1, -1):
        cells.append([(w, y) for w in range(width)])
    return cells


CELLS = edge_cells()


def _set(px, x: int, y: int, rgb: tuple[int, int, int], mode: str) -> None:
    px[x, y] = rgb + ((255,) if mode == "RGBA" else ())


def draw_marquee(img: Image.Image, frame_index: int, frame_count: int = 4) -> None:
    """Pink/white dashed chase that advances each frame."""
    px = img.load()
    n = len(CELLS)
    period = 16  # 8 pink + 8 white
    on_len = 8
    shift = (frame_index * (period // frame_count)) % period
    for i, cell in enumerate(CELLS):
        on = ((i - shift) % period) < on_len
        color = PINK if on else WHITE
        for x, y in cell:
            _set(px, x, y, color, img.mode)


def draw_flash_red(img: Image.Image, frame_index: int) -> None:
    px = img.load()
    color = RED_ON if frame_index % 2 == 0 else RED_OFF
    for cell in CELLS:
        for x, y in cell:
            _set(px, x, y, color, img.mode)


def _save_gif(frames: list[Image.Image], path: Path, duration: int) -> None:
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
        disposal=2,
        optimize=False,
    )


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

    _save_gif(frames_rgb, folder / "loop.gif", GIF_MS[status])
    print(f"{status}: updated 4 frames + loop.gif")


def main() -> int:
    process_status("running", draw_marquee)
    process_status("error", draw_flash_red)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
