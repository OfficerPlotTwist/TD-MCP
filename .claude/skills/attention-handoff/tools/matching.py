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
