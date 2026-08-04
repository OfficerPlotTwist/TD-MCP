"""Merge human captures and agent vision readings into graph.json.

Inputs (session dir):
  captures.json  - written by the capture app:
      [{"id","t","type":"param|network|pair","bbox","file","pairId","role"}]
  readings.json  - written by the agent after vision-reading each crop:
      {"<captureId>": reading}
    reading kinds:
      {"kind":"param","opName":"noise1","opType":"noiseTOP",
       "params":{"period":"4"}}
      {"kind":"network","nodes":[{"label":"noi","opType":"noiseTOP"}],
       "wires":[{"from":"noi","to":"lev","toInlet":0}]}
      {"kind":"opnode","label":"noise1"}      (pair op-node crops)
      {"kind":"network-whole","opCount":14,"wireCount":13}
          (zoomed-out grabs: names unreadable, counts cross-checked
           against the built graph -> opcount/wirecount-mismatch conflicts)
      {"kind":"unreadable"}
  optypes.json   - optional list of valid TD op types (from live TD)

Output: graph.json (see design spec 2026-08-04-attention-handoff-design.md).
Pure logic in normalize/resolve_label/build_graph; __main__ does file I/O.
"""
import json
import os
import sys


def normalize(name):
    return str(name).strip().lower()


def resolve_label(label, known_names):
    """Resolve a possibly-truncated node label against known op names.

    Returns (resolved_name, conflict). A unique exact or prefix match wins;
    multiple prefix matches yield an ambiguous-name conflict; no match
    returns the label itself as a new op name.
    """
    lab = normalize(label)
    for n in known_names:
        if normalize(n) == lab:
            return n, None
    prefixed = [n for n in known_names if normalize(n).startswith(lab)]
    if len(prefixed) == 1:
        return prefixed[0], None
    if len(prefixed) > 1:
        return None, {"kind": "ambiguous-name",
                      "detail": "label '%s' matches %s" % (label, sorted(prefixed)),
                      "captureIds": []}
    return label, None


def build_graph(captures, readings):
    conflicts = []

    # 1. Pair overrides: normalized node label -> full op name
    pair_label_to_name = {}
    successful_pairs = set()  # track pairIds that produced an override
    by_pair = {}
    for c in captures:
        if c.get("pairId"):
            by_pair.setdefault(c["pairId"], []).append(c)
    for pair_id, group in by_pair.items():
        label, name = None, None
        for c in group:
            r = readings.get(c["id"]) or {}
            if r.get("kind") == "opnode":
                label = r.get("label")
            elif r.get("kind") == "param":
                name = r.get("opName")
        if label and name:
            pair_label_to_name[normalize(label)] = name
            successful_pairs.add(pair_id)

    # 2. Ops from param readings, ordered by video time (latest wins)
    ops = {}  # normalized name -> op dict

    def ensure_op(name, op_type=None, cap_id=None):
        key = normalize(name)
        if key not in ops:
            ops[key] = {"id": name, "opType": op_type or "",
                        "confidence": 1.0, "params": {}, "sources": []}
        op = ops[key]
        if op_type and not op["opType"]:
            op["opType"] = op_type
        if cap_id and cap_id not in op["sources"]:
            op["sources"].append(cap_id)
        return op

    param_reads = []
    for c in captures:
        r = readings.get(c["id"]) or {}
        if r.get("kind") == "param":
            param_reads.append((c, r))
        elif r.get("kind") == "unreadable":
            conflicts.append({"kind": "unreadable",
                              "detail": "capture %s could not be read" % c["id"],
                              "captureIds": [c["id"]]})
    param_reads.sort(key=lambda cr: cr[0]["t"])
    for c, r in param_reads:
        op = ensure_op(r["opName"], r.get("opType"), c["id"])
        for pname, value in (r.get("params") or {}).items():
            slot = op["params"].get(pname)
            if slot is None:
                op["params"][pname] = {"value": value, "t": c["t"],
                                       "history": []}
            elif slot["value"] != value:
                slot["history"].append({"value": slot["value"], "t": slot["t"]})
                slot["value"], slot["t"] = value, c["t"]
                conflicts.append({
                    "kind": "param-changed",
                    "detail": "%s.%s changed to %r at t=%.1f"
                              % (op["id"], pname, value, c["t"]),
                    "captureIds": [c["id"]]})

    # 3. Network readings: resolve labels, add unmatched ops, union wires
    known = [o["id"] for o in ops.values()]

    def resolve(label, cap_id):
        key = normalize(label)
        if key in pair_label_to_name:
            return pair_label_to_name[key]
        name, conflict = resolve_label(label, known)
        if conflict:
            conflict["captureIds"] = [cap_id]
            conflicts.append(conflict)
            return None
        return name

    wires = {}
    for c in captures:
        r = readings.get(c["id"]) or {}
        if r.get("kind") != "network":
            continue
        for node in r.get("nodes") or []:
            name = resolve(node["label"], c["id"])
            if name:
                ensure_op(name, node.get("opType"), c["id"])
                if name not in known:
                    known.append(name)
        for w in r.get("wires") or []:
            src = resolve(w["from"], c["id"])
            dst = resolve(w["to"], c["id"])
            if not src or not dst:
                continue
            for endpoint in (src, dst):
                ensure_op(endpoint, None, c["id"])
                if endpoint not in known:
                    known.append(endpoint)
            key = (normalize(src), normalize(dst), w.get("toInlet", 0))
            if key not in wires:
                wires[key] = {"from": src, "to": dst,
                              "toInlet": w.get("toInlet", 0), "sources": []}
            if c["id"] not in wires[key]["sources"]:
                wires[key]["sources"].append(c["id"])

    for op in ops.values():
        if not op["opType"]:
            conflicts.append({"kind": "unknown-optype",
                              "detail": "op '%s' has no op type" % op["id"],
                              "captureIds": list(op["sources"])})

    # 3b. Whole-network readings: structure/count evidence only (names
    # unreadable at that zoom) — cross-check counts against the built graph.
    for c in captures:
        r = readings.get(c["id"]) or {}
        if r.get("kind") != "network-whole":
            continue
        expected_ops = r.get("opCount")
        if isinstance(expected_ops, int) and expected_ops != len(ops):
            conflicts.append({
                "kind": "opcount-mismatch",
                "detail": "whole-network capture %s shows ~%d ops; graph has %d"
                          % (c["id"], expected_ops, len(ops)),
                "captureIds": [c["id"]]})
        expected_wires = r.get("wireCount")
        if isinstance(expected_wires, int) and expected_wires != len(wires):
            conflicts.append({
                "kind": "wirecount-mismatch",
                "detail": "whole-network capture %s shows ~%d wires; graph has %d"
                          % (c["id"], expected_wires, len(wires)),
                "captureIds": [c["id"]]})

    # 4. Final pass: validate all captures have recognized readings
    valid_kinds = {"param", "network", "network-whole", "unreadable", "opnode"}
    for c in captures:
        cap_id = c["id"]
        r = readings.get(cap_id)
        if r is None:
            conflicts.append({"kind": "missing-reading",
                              "detail": "capture %s has no reading" % cap_id,
                              "captureIds": [cap_id]})
        else:
            kind = r.get("kind")
            if kind not in valid_kinds:
                conflicts.append({"kind": "missing-reading",
                                  "detail": "capture %s has unrecognized reading kind '%s'" % (cap_id, kind),
                                  "captureIds": [cap_id]})
            elif kind == "opnode":
                pid = c.get("pairId")
                if not pid:
                    conflicts.append({"kind": "missing-reading",
                                      "detail": "capture %s is an opnode with no pairId" % cap_id,
                                      "captureIds": [cap_id]})
                elif pid not in successful_pairs:
                    conflicts.append({"kind": "missing-reading",
                                      "detail": "capture %s: pair %s incomplete" % (cap_id, pid),
                                      "captureIds": [cap_id]})

    op_list = list(ops.values())
    wire_list = list(wires.values())
    return {"ops": op_list, "wires": wire_list, "conflicts": conflicts,
            "stats": {"opCount": len(op_list), "wireCount": len(wire_list)}}


def main(session_dir):
    def load(name, default):
        path = os.path.join(session_dir, name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return default

    captures = load("captures.json", [])
    readings = load("readings.json", {})
    graph = build_graph(captures, readings)
    graph["opTypes"] = load("optypes.json", [])
    out = os.path.join(session_dir, "graph.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2)
    print("wrote %s: %d ops, %d wires, %d conflicts" % (
        out, graph["stats"]["opCount"], graph["stats"]["wireCount"],
        len(graph["conflicts"])))


if __name__ == "__main__":
    main(sys.argv[1])
