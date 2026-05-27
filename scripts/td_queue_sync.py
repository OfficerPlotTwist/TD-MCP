# TouchDesigner-side sync: materialize implementation_queue.json into a Table DAT
# and gold-flag any already-implemented favorites. This script is meant to be
# EXEC'd inside TouchDesigner (via the MCP execute_script tool), not run by the
# system Python — it uses the TD op() API. It is self-contained (only stdlib
# json) and reads the pipeline DBs from their canonical absolute paths.
import json
import os

PIPELINE = r"C:\Users\nik\Documents\AI\MCP\TD MCP\shader_pipeline"
QUEUE_PATH = os.path.join(PIPELINE, "implementation_queue.json")
GOOD_PATH = os.path.join(PIPELINE, "human_selected_good_shaders.json")
PARENT = "/project1"
DAT_NAME = "shader_queue"
GOLD = (0.98, 0.77, 0.16)

queue = json.load(open(QUEUE_PATH, encoding="utf-8")).get("queue", []) if os.path.exists(QUEUE_PATH) else []
good = json.load(open(GOOD_PATH, encoding="utf-8")).get("shaders", []) if os.path.exists(GOOD_PATH) else []
good_by_sid = {g["sid"]: g for g in good}

parent = op(PARENT)
dat = parent.op(DAT_NAME)
if dat is None:
    dat = parent.create(tableDAT, DAT_NAME)
    # drop it clear of the existing node cluster
    dat.nodeX, dat.nodeY = -1200, 600

dat.clear()
dat.appendRow(["rank", "sid", "src_id", "name", "favorite", "status"])
for e in queue:
    dat.appendRow([
        e.get("rank", ""), e.get("sid", ""), e.get("src_id", ""),
        e.get("src_name", ""), "fav" if e.get("favorite") else "",
        e.get("status", "queued"),
    ])

# Gold-flag already-implemented favorites on their live networks.
flagged = []
for g in good:
    if not g.get("favorite") or g.get("td_status") != "implemented":
        continue
    tp = g.get("td_path")
    target = op(tp) if tp else None
    if target is None:
        continue
    target.color = GOLD
    if target.isCOMP:
        if not hasattr(target.par, "Favorite"):
            pg = target.appendCustomPage("Shader")
            pg.appendToggle("Favorite")
        target.par.Favorite = True
    flagged.append(g["sid"])

print(f"shader_queue rows: {len(queue)} | gold-flagged implemented favorites: {flagged}")
