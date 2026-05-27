"""Resolve a shader review grid from a terse approval command.

Schema (order enforced):   looksgood.py <numbers> <id>
  <numbers>  approval digits 1-9 (contiguous "13357" or spaced "1 3 3 5 7").
             A digit present once  -> that tile is approved.
             A digit present twice -> approved + favorite + pushed to front of queue.
             The token "00"        -> disapprove ALL (grid rejected); takes precedence.
  <id>       grid id, last token. Accepts "sgr_0007", "0007", or "7"
             (the 4-digit counter that increments per grid).

Effect: approved shaders are added to human_selected_good_shaders.json (favorite
flag set on doubles) and appended to implementation_queue.json (favorites at the
front). The grid is marked resolved/rejected and its PNG is deleted. TD-side
sync (Table DAT + gold flag on already-built favorites) is done by the command
wrapper via td_queue_sync.py over the MCP bridge.

Prints a JSON summary on the last line (consumed by the /looksgood command).
"""
from __future__ import annotations
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shader_pipeline"))
from _db import (CANDIDATES_DB, GOOD_SHADERS_DB, QUEUE_DB, REJECTED_DB,  # noqa: E402
                 REVIEW_GRIDS_DB, load_db, now_iso, pipeline_lock, save_db)


def log_rejection(rejected_db, seen, tile, grid_id, reason):
    """Append a rejected-shader audit record (dedup by sid)."""
    sid = tile["sid"]
    if sid in seen:
        return
    rejected_db["rejected"].append({
        "sid": sid, "src_id": tile["src_id"], "src_name": tile["src_name"],
        "composite_score": tile.get("composite_score"),
        "source_grid_id": grid_id, "reason": reason, "rejected_at": now_iso(),
    })
    seen.add(sid)


def _trailing_int(s: str):
    m = re.search(r"(\d+)$", s or "")
    return int(m.group(1)) if m else None


def find_grid(grids: list, id_arg: str) -> dict | None:
    """Resolve a grid by exact id ('sgr05', legacy 'sgr_0005') or by its
    trailing number ('05' or '5'). Prefers a pending grid on a number tie."""
    for g in grids:
        if g["id"] == id_arg:
            return g
    n = _trailing_int(id_arg)
    if n is not None:
        matches = [g for g in grids if _trailing_int(g["id"]) == n]
        for g in matches:
            if g.get("status") == "pending":
                return g
        if matches:
            return matches[0]
    return None


def reindex_queue(queue: list) -> None:
    for i, e in enumerate(queue, start=1):
        e["rank"] = i


def _resolve(args: list) -> int:
    id_arg = args[-1]
    number_tokens = args[:-1]
    reject_all = "00" in number_tokens or "".join(number_tokens) == "00"

    digits = [ch for tok in number_tokens for ch in tok if ch in "123456789"]
    counts = Counter(digits)

    grids_db = load_db(REVIEW_GRIDS_DB, "grids")
    grid = find_grid(grids_db["grids"], id_arg)
    if grid is None:
        print(json.dumps({"ok": False, "error": f"grid '{id_arg}' not found"}))
        return 1
    if grid["status"] != "pending":
        print(json.dumps({"ok": False, "error": f"grid {grid['id']} already {grid['status']}"}))
        return 1

    good_db = load_db(GOOD_SHADERS_DB, "shaders")
    queue_db = load_db(QUEUE_DB, "queue")
    cand_db = load_db(CANDIDATES_DB, "candidates")
    cand_by_sid = {c["sid"]: c for c in cand_db["candidates"]}
    rejected_db = load_db(REJECTED_DB, "rejected")
    rej_seen = {r["sid"] for r in rejected_db["rejected"]}

    summary = {"ok": True, "grid": grid["id"], "approved": [], "favorited": [],
               "rejected_all": reject_all, "rejected": [], "png_deleted": False,
               "ignored_digits": []}

    if reject_all:
        grid["status"] = "rejected"
        for label, tile in grid["tiles"].items():
            log_rejection(rejected_db, rej_seen, tile, grid["id"], "grid_rejected_00")
            summary["rejected"].append(tile["sid"])
    else:
        good_by_sid = {s["sid"]: s for s in good_db["shaders"]}
        q_by_sid = {q["sid"]: q for q in queue_db["queue"]}
        front = []  # favorites to prepend (tile order)

        for label in sorted(counts):           # "1".."9"
            tile = grid["tiles"].get(label)
            if tile is None:
                summary["ignored_digits"].append(label)
                continue
            sid = tile["sid"]
            fav = counts[label] >= 2
            cand = cand_by_sid.get(sid, {})

            # human_selected_good_shaders
            if sid in good_by_sid:
                if fav:
                    good_by_sid[sid]["favorite"] = True
            else:
                good_by_sid[sid] = {
                    "sid": sid, "src_id": tile["src_id"], "src_name": tile["src_name"],
                    "frag_path": cand.get("frag_path"), "description": cand.get("description", ""),
                    "composite_score": tile.get("composite_score"),
                    "favorite": fav, "approved_at": now_iso(),
                    "source_grid_id": grid["id"], "td_status": "queued", "td_path": None,
                }
                good_db["shaders"].append(good_by_sid[sid])

            # implementation_queue
            if sid in q_by_sid:
                qe = q_by_sid[sid]
                if fav and qe in queue_db["queue"]:
                    queue_db["queue"].remove(qe)
                    qe["favorite"] = True
                    front.append(qe)
            else:
                qe = {"sid": sid, "src_id": tile["src_id"], "src_name": tile["src_name"],
                      "frag_path": cand.get("frag_path"), "favorite": fav, "status": "queued"}
                q_by_sid[sid] = qe
                if fav:
                    front.append(qe)
                else:
                    queue_db["queue"].append(qe)

            summary["approved"].append(sid)
            if fav:
                summary["favorited"].append(sid)

        if front:
            queue_db["queue"] = front + queue_db["queue"]
        reindex_queue(queue_db["queue"])
        grid["status"] = "resolved"

        # Audit trail: tiles the human did not approve are rejected ("not_selected").
        approved_set = set(summary["approved"])
        for label, tile in grid["tiles"].items():
            if tile["sid"] not in approved_set:
                log_rejection(rejected_db, rej_seen, tile, grid["id"], "not_selected")
                summary["rejected"].append(tile["sid"])

    # Delete the grid PNG either way.
    png = Path(grid["png_path"])
    if png.exists():
        png.unlink()
        summary["png_deleted"] = True

    save_db(GOOD_SHADERS_DB, good_db)
    save_db(QUEUE_DB, queue_db)
    save_db(REVIEW_GRIDS_DB, grids_db)
    save_db(REJECTED_DB, rejected_db)

    # Auto-replenish: when no grids remain pending, build the next batch (<=10,
    # capped by the remaining pool) so there's always more to review.
    AUTO_BATCH = 10
    auto_built = []
    if not any(g["status"] == "pending" for g in grids_db["grids"]):
        from build_shader_grid import build_one
        for _ in range(AUTO_BATCH):
            rec = build_one(grids_db, cand_db)
            if rec is None:
                break
            auto_built.append(rec["id"])
        if auto_built:
            save_db(REVIEW_GRIDS_DB, grids_db)
            save_db(CANDIDATES_DB, cand_db)
    summary["auto_built_grids"] = auto_built

    summary["queue_len"] = len(queue_db["queue"])
    print(f"grid {grid['id']} -> {grid['status']}")
    if not reject_all:
        print(f"  approved: {summary['approved']}")
        print(f"  favorited (front of queue): {summary['favorited']}")
        if summary["ignored_digits"]:
            print(f"  ignored (no such tile): {summary['ignored_digits']}")
    reason = "grid_rejected_00" if reject_all else "not_selected"
    print(f"  rejected -> audit ({reason}): {summary['rejected']}")
    print(f"  queue length: {summary['queue_len']}  | grid PNG deleted: {summary['png_deleted']}")
    if auto_built:
        print(f"  auto-built {len(auto_built)} new grid(s) (pool empty of pending): {auto_built}")
    print(json.dumps(summary))
    return 0


def main() -> int:
    args = sys.argv[1:]
    if len(args) < 2:
        print("usage: looksgood.py <numbers> <id>", file=sys.stderr)
        print(json.dumps({"ok": False, "error": "need <numbers> <id>"}))
        return 2
    try:
        with pipeline_lock():
            return _resolve(args)
    except TimeoutError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
