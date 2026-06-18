"""uiborder_blur (`uib`) /looksgood resolver.

Invocation (id LAST, matching the sgr arg order so /looksgood passes the user
string through unchanged):

    python resolver.py <numbers> [r<series>] <id>

Approval semantics for a blur-size sweep:
  - digit once   -> that tile's size approved (a candidate pick for the blur)
  - digit twice  -> FAVORITE: the definitive locked pick for the blur
  - r<series>    -> those sizes go to the refine pool (next TD render sweeps finer around them)
  - 00           -> reject the whole grid (no size chosen)

Pick rule: favorite if any, else the single approved size, else the first approved.
Writes selections.json / refine.json, marks the grid resolved, deletes the grid
PNG, and prints a one-line JSON summary (consumed by /looksgood). The chosen
sizes are applied to the live TD blurs by the TD-sync step (td_uiborder_apply.py).
"""
import sys, os, json, re
import engine


def parse_args(argv):
    if not argv:
        raise SystemExit("usage: resolver.py <numbers> [r<series>] <id>")
    grid_id = argv[-1]
    rest = argv[:-1]
    nums, refine, reject = [], [], False
    for tok in rest:
        t = tok.strip().lower()
        if t == "00":
            reject = True
        elif t.startswith("r"):
            refine += [int(c) for c in re.sub(r"\D", "", t)]
        else:
            nums += [int(c) for c in re.sub(r"\D", "", t)]
    return grid_id, nums, refine, reject


def main(argv):
    grid_id, nums, refine_digits, reject = parse_args(argv)
    db = engine.ensure_db()
    grid = engine.find_grid(db, grid_id)
    if grid is None:
        print(json.dumps({"ok": False, "pipeline": "uib", "error": f"grid '{grid_id}' not found"}))
        return 1
    if grid["status"] != "pending":
        print(json.dumps({"ok": False, "pipeline": "uib", "error": f"grid {grid['id']} already {grid['status']}"}))
        return 1

    blur = grid["blur"]
    tiles = grid["tiles"]

    def size_of(d):
        return tiles[str(d)]["size"] if str(d) in tiles else None

    summary = {"ok": True, "pipeline": "uib", "grid": grid["id"], "blur": blur}

    if reject:
        grid["status"] = "rejected"
        summary.update({"rejected": True, "pick": None})
    else:
        approved = sorted({d for d in nums if size_of(d)})
        favorites = sorted({d for d in approved if nums.count(d) >= 2})
        approved_sizes = [size_of(d) for d in approved]
        fav_sizes = [size_of(d) for d in favorites]
        pick = fav_sizes[0] if fav_sizes else (approved_sizes[0] if approved_sizes else None)
        refine_sizes = sorted({size_of(d) for d in refine_digits if size_of(d)})

        if pick is not None:
            sel = engine._read(engine.SELECTIONS, {})
            sel[blur] = {"size": pick, "grid": grid["id"],
                         "favorite": bool(fav_sizes), "approved": approved_sizes}
            engine._write(engine.SELECTIONS, sel)
        if refine_sizes:
            ref = engine._read(engine.REFINE, {})
            ref[blur] = sorted(set(ref.get(blur, [])) | set(refine_sizes))
            engine._write(engine.REFINE, ref)
        grid["status"] = "resolved"
        summary.update({"approved": approved_sizes, "favorite": (fav_sizes[0] if fav_sizes else None),
                        "refined": refine_sizes, "pick": pick})

    engine._write(engine.DB, db)
    try:
        os.remove(grid["png_path"])
        summary["grid_deleted"] = True
    except FileNotFoundError:
        summary["grid_deleted"] = False
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    raise SystemExit(main(sys.argv[1:]))
