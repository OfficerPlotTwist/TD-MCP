"""uiborder_blur (`uib`) review pipeline — engine.

Owns the paths, the grid DB, and grid (re)generation. The Busdriver
`regenerate.py` shim and `resolver.py` both import this. Grids are 3x3 contact
sheets, one per blur, sweeping that blur's size (others held at project
default). Each tile = one swept size; tile digits 1..9 map row-major.

Frames are link2 snapshots captured live from TouchDesigner (the image
`out_uiborder` would record). Regeneration rebuilds sheets from cached frames in
GRID_DIR/_frames — it cannot render NEW sizes headless (that needs the live TD
bridge), so refine requests are fulfilled by a TD-side render step, not here.
"""
import os, json, glob, re

GRID_DIR = r"C:/Users/nik/Documents/AI/Busdriver/review_grids/uiborder_blur"
FRAMES = os.path.join(GRID_DIR, "_frames")
PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(PIPELINE_DIR, "db.json")
SELECTIONS = os.path.join(PIPELINE_DIR, "selections.json")
REFINE = os.path.join(PIPELINE_DIR, "refine.json")

CODE = "uib"
# swept sizes per blur (idx 0..8) and the project-default size held while sweeping others
SIZES = {"blur1": [2, 3, 4, 6, 7, 10, 14, 21, 28],
         "blur2": [4, 7, 10, 14, 17, 24, 34, 51, 68],
         "blur3": [3, 4, 7, 9, 11, 15, 22, 33, 44]}
ORIG = {"blur1": 7, "blur2": 17, "blur3": 11}
GRID_FOR = {"blur1": "uib01", "blur2": "uib02", "blur3": "uib03"}
BLUR_FOR = {v: k for k, v in GRID_FOR.items()}


def _read(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def _write(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def _frame_for(blur, size):
    idx = SIZES[blur].index(size)
    return f"{blur}__{idx}__{size}.png"


def ensure_db():
    """Create db.json from SIZES if absent. Returns the db dict."""
    db = _read(DB, None)
    if db is not None:
        return db
    grids = []
    for blur, sizes in SIZES.items():
        gid = GRID_FOR[blur]
        tiles = {}
        for i, s in enumerate(sizes):
            tiles[str(i + 1)] = {"size": s, "frame": _frame_for(blur, s),
                                 "is_default": (s == ORIG[blur])}
        grids.append({"id": gid, "blur": blur,
                      "png_path": os.path.join(GRID_DIR, gid + ".png").replace("\\", "/"),
                      "status": "pending", "tiles": tiles})
    db = {"grids": grids}
    _write(DB, db)
    return db


def find_grid(db, grid_id):
    key = str(grid_id).lower()
    m = re.match(r"^([a-z]{3})[_]?0*?(\d+)$", key)
    norm = None
    if m:
        norm = m.group(1) + str(int(m.group(2))).zfill(2)
    elif key.isdigit():
        norm = CODE + str(int(key)).zfill(2)
    for g in db["grids"]:
        if g["id"] == norm or g["id"] == key:
            return g
    return None


def build_sheet(grid):
    """Render one grid's 3x3 contact sheet from cached frames. Returns png path."""
    from PIL import Image, ImageDraw, ImageFont
    TILE_W, TILE_H, PAD, LABEL_H, HEAD_H, COLS = 384, 216, 14, 24, 46, 3
    BG, CUR = (24, 24, 28), (0, 220, 255)

    def font(sz):
        try:
            return ImageFont.truetype("arial.ttf", sz)
        except Exception:
            return ImageFont.load_default()

    blur = grid["blur"]
    items = sorted(((int(k), v) for k, v in grid["tiles"].items()))
    rows = (len(items) + COLS - 1) // COLS
    W = COLS * TILE_W + (COLS + 1) * PAD
    H = HEAD_H + rows * (TILE_H + LABEL_H + PAD) + PAD
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)
    others = ", ".join(f"{k}={v}" for k, v in ORIG.items() if k != blur)
    d.text((PAD, 12), f"{grid['id']}  {blur} size sweep   (held: {others})", fill=(235, 235, 240), font=font(22))
    for n, t in items:
        i = n - 1
        r, c = divmod(i, COLS)
        x = PAD + c * (TILE_W + PAD)
        y = HEAD_H + r * (TILE_H + LABEL_H + PAD)
        fp = os.path.join(FRAMES, t["frame"])
        try:
            im = Image.open(fp).convert("RGB").resize((TILE_W, TILE_H))
        except Exception:
            im = Image.new("RGB", (TILE_W, TILE_H), (40, 0, 0))
        sheet.paste(im, (x, y))
        if t.get("is_default"):
            d.rectangle([x - 3, y - 3, x + TILE_W + 2, y + TILE_H + 2], outline=CUR, width=4)
        lbl = f"{n}: size {t['size']}" + ("  (current)" if t.get("is_default") else "")
        d.text((x + 4, y + TILE_H + 4), lbl, fill=(CUR if t.get("is_default") else (200, 200, 205)), font=font(18))
    out = grid["png_path"]
    sheet.save(out)
    return out


def regenerate():
    """Watcher entrypoint: rebuild any PENDING grid whose PNG is missing.
    Never resurrects resolved/rejected grids."""
    db = ensure_db()
    built = []
    for g in db["grids"]:
        if g["status"] == "pending" and not os.path.exists(g["png_path"]):
            built.append(build_sheet(g))
    print(f"[uib] regenerate: rebuilt {len(built)} grid(s): {built}")
    return built


if __name__ == "__main__":
    ensure_db()
    # Force a full rebuild of all pending grids (used for first build / manual refresh).
    db = _read(DB, {"grids": []})
    for g in db["grids"]:
        if g["status"] == "pending":
            print(build_sheet(g))
