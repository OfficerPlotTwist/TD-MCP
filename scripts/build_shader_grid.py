"""Compose 3x3 shader-thumbnail review contact-sheets.

Picks the next <=9 unreviewed pool candidates (ranked by composite_score desc),
lays them out 3x3 with a "1".."9" badge in each cell's upper-right corner, and a
caption bar across the bottom showing the grid id, the approval destinations, and
the /looksgood legend. Writes the PNG, records the grid (with its verbose full
path + tile->shader map) in review_grids.json, and marks those candidates
reviewed in candidates.json.

Usage:  python build_shader_grid.py [count]      # count grids, default 1
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shader_pipeline"))
from _db import (CANDIDATES_DB, GRID_IMG_DIR, REVIEW_GRIDS_DB, fwd, load_db,  # noqa: E402
                 now_iso, pipeline_lock, save_db)

# Layout constants.
CELL = 360            # thumbnail cell size (px)
GAP = 10              # gap between cells
MARGIN = 16           # outer margin
CAPTION_H = 132       # bottom caption bar height
BG = (18, 18, 22)
CELL_BG = (30, 30, 36)
CAPTION_BG = (12, 12, 15)
FG = (235, 235, 240)
DIM = (150, 150, 160)
BADGE_BG = (250, 196, 40)     # gold
BADGE_FG = (20, 20, 20)

DESTINATIONS = [
    "Approved → Human-Selected-Good-Shaders DB",
    "Approved → TouchDesigner queue  /project1/shader_queue",
]
LEGEND = "/looksgood <numbers> <id>   •   dup digit = favorite + front of queue   •   00 = reject all"


def _font(size: int, bold: bool = False):
    for name in (("arialbd.ttf" if bold else "arial.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit(img: Image.Image, box: int) -> Image.Image:
    """Resize preserving aspect to fit within box x box."""
    img = img.convert("RGB")
    w, h = img.size
    scale = min(box / w, box / h)
    return img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)


def _next_counter(grids_db: dict) -> int:
    """Next counter = 1 + the highest trailing number across existing grid ids.
    Reads any id ending in digits (legacy 'sgr_0004' or short 'sgr04')."""
    nums = []
    for g in grids_db["grids"]:
        m = re.search(r"(\d+)$", g.get("id", ""))
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def _draw_badge(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, font) -> None:
    """Number badge in a cell's upper-right corner."""
    pad = 8
    tw = draw.textlength(label, font=font)
    th = font.size
    bw, bh = int(tw) + pad * 2, th + pad
    bx, by = x + CELL - bw - 8, y + 8
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=8, fill=BADGE_BG)
    draw.text((bx + pad, by + pad // 2 - 1), label, font=font, fill=BADGE_FG)


def build_one(grids_db: dict, candidates_db: dict) -> dict | None:
    pool = [c for c in candidates_db["candidates"] if c.get("in_pool") and not c.get("reviewed")]
    if not pool:
        return None
    pool.sort(key=lambda c: c["composite_score"] or -1.0, reverse=True)
    tiles = pool[:9]

    n = _next_counter(grids_db)
    grid_id = f"sgr{n:02d}"

    grid_w = MARGIN * 2 + CELL * 3 + GAP * 2
    grid_h = MARGIN * 2 + CELL * 3 + GAP * 2 + CAPTION_H
    canvas = Image.new("RGB", (grid_w, grid_h), BG)
    draw = ImageDraw.Draw(canvas)
    badge_font = _font(34, bold=True)
    cap_title = _font(30, bold=True)
    cap_line = _font(22)
    cap_small = _font(19)

    tile_map = {}
    for i in range(9):
        r, col = divmod(i, 3)
        x = MARGIN + col * (CELL + GAP)
        y = MARGIN + r * (CELL + GAP)
        draw.rectangle([x, y, x + CELL, y + CELL], fill=CELL_BG)
        label = str(i + 1)
        if i < len(tiles):
            t = tiles[i]
            try:
                thumb = _fit(Image.open(t["thumb_path"]), CELL - 8)
                ox = x + (CELL - thumb.width) // 2
                oy = y + (CELL - thumb.height) // 2
                canvas.paste(thumb, (ox, oy))
            except (OSError, ValueError):
                draw.text((x + 12, y + 12), "(thumb error)", font=cap_small, fill=DIM)
            _draw_badge(draw, x, y, label, badge_font)
            tile_map[label] = {
                "sid": t["sid"], "src_id": t["src_id"], "src_name": t["src_name"],
                "thumb_path": t["thumb_path"], "composite_score": t["composite_score"],
            }
        else:
            draw.text((x + CELL // 2 - 8, y + CELL // 2 - 12), "—", font=badge_font, fill=DIM)

    # Caption bar.
    cy0 = grid_h - CAPTION_H
    draw.rectangle([0, cy0, grid_w, grid_h], fill=CAPTION_BG)
    tx = MARGIN
    draw.text((tx, cy0 + 10), f"GRID  {grid_id}", font=cap_title, fill=BADGE_BG)
    draw.text((tx + 280, cy0 + 17), now_iso(), font=cap_small, fill=DIM)
    draw.text((tx, cy0 + 48), DESTINATIONS[0], font=cap_line, fill=FG)
    draw.text((tx, cy0 + 74), DESTINATIONS[1], font=cap_line, fill=FG)
    draw.text((tx, cy0 + 102), LEGEND, font=cap_small, fill=DIM)

    GRID_IMG_DIR.mkdir(parents=True, exist_ok=True)
    png_path = GRID_IMG_DIR / f"{grid_id}.png"
    canvas.save(png_path)

    record = {
        "id": grid_id,
        "png_path": fwd(png_path),
        "created_at": now_iso(),
        "status": "pending",
        "destinations": DESTINATIONS,
        "tiles": tile_map,
    }
    grids_db["grids"].append(record)
    for t in tiles:
        t["reviewed"] = True
    return record


def main() -> int:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    with pipeline_lock():
        grids_db = load_db(REVIEW_GRIDS_DB, "grids")
        candidates_db = load_db(CANDIDATES_DB, "candidates")

        made = []
        for _ in range(count):
            rec = build_one(grids_db, candidates_db)
            if rec is None:
                break
            made.append(rec)

        save_db(REVIEW_GRIDS_DB, grids_db)
        save_db(CANDIDATES_DB, candidates_db)

    if not made:
        print("No unreviewed pool candidates remain — nothing to build.")
        return 0
    for rec in made:
        print(f"{rec['id']}  ({len(rec['tiles'])} tiles)  {rec['png_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
