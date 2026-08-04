"""Turn approved.json into an ordered rebuild plan for the agent.

Prints plan JSON: container name, master_controls channels, op creates
(with left-to-right layout), channel-referenced params, direct-set params
(non-numeric - CHOP channels carry numbers only), and wires.

This script never touches TD. The agent executes the plan over the MCP
bridge; --dry-run is accepted and identical to the default (print only).

Usage: python rebuild_plan.py <session_dir> [--dry-run]
"""
import json
import math
import os
import re
import sys

CHAN_MAX = 60
BUS = "/project1/master_controls"


def sanitize(text):
    return re.sub(r"[^a-z0-9_]", "_", str(text).lower()).strip("_")


def is_numeric(value):
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    try:
        return math.isfinite(float(str(value).strip()))
    except ValueError:
        return False


def channel_name(video_id, op_name, par_name, taken):
    base = "tut_%s_%s_%s" % (sanitize(video_id), sanitize(op_name),
                             sanitize(par_name))
    name = base[:CHAN_MAX]
    n = 2
    while name in taken:
        suffix = "_%d" % n
        name = base[:CHAN_MAX - len(suffix)] + suffix
        n += 1
    taken.add(name)
    return name


def compute_depths(ops, wires):
    depth = {o["id"]: 0 for o in ops}
    incoming = {o["id"]: [] for o in ops}
    for w in wires:
        if w["to"] in incoming and w["from"] in depth:
            incoming[w["to"]].append(w["from"])
    for _ in range(len(ops)):
        changed = False
        for o in ops:
            for src in incoming[o["id"]]:
                if depth[src] + 1 > depth[o["id"]]:
                    depth[o["id"]] = depth[src] + 1
                    changed = True
        if not changed:
            break
    return depth


def build_plan(graph, video_id):
    ops, wires = graph["ops"], graph["wires"]
    depth = compute_depths(ops, wires)
    rows = {}
    creates = []
    for o in sorted(ops, key=lambda o: (depth[o["id"]], o["id"])):
        col = depth[o["id"]]
        row = rows.get(col, 0)
        rows[col] = row + 1
        creates.append({"name": o["id"], "opType": o["opType"],
                        "nodeX": col * 200, "nodeY": -row * 160})
    taken = set()
    channels, chan_params, direct_params = [], [], []
    for o in ops:
        for pname, slot in (o.get("params") or {}).items():
            value = slot["value"]
            if is_numeric(value):
                chan = channel_name(video_id, o["id"], pname, taken)
                channels.append({"name": chan,
                                 "value": float(str(value).strip())
                                 if not isinstance(value, bool)
                                 else float(value)})
                chan_params.append({"op": o["id"], "par": pname,
                                    "expr": "op('%s')['%s']" % (BUS, chan)})
            else:
                direct_params.append({
                    "op": o["id"], "par": pname, "value": value,
                    "note": "non-numeric; set directly "
                            "(CHOP channels are numbers)"})
    blockers = [{"kind": "empty-optype", "op": o["id"]}
                for o in ops if not o.get("opType")]
    blockers.extend({"kind": "unresolved-conflict", "detail": c.get("detail")}
                     for c in (graph.get("conflicts") or []))
    return {"container": "tutorial_%s" % sanitize(video_id),
            "bus": BUS,
            "opTypes": sorted({o["opType"] for o in ops if o["opType"]}),
            "blockers": blockers,
            "channels": channels,
            "creates": creates,
            "channelParams": chan_params,
            "directParams": direct_params,
            "wires": [{"from": w["from"], "to": w["to"],
                       "toInlet": w.get("toInlet", 0)} for w in wires]}


def main():
    session_dir = sys.argv[1]
    with open(os.path.join(session_dir, "approved.json"), "r",
              encoding="utf-8") as f:
        graph = json.load(f)
    video_id = os.path.basename(os.path.normpath(session_dir))
    print(json.dumps(build_plan(graph, video_id), indent=2))


if __name__ == "__main__":
    main()
