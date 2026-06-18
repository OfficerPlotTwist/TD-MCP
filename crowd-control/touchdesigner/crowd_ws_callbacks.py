# crowd-control/touchdesigner/crowd_ws_callbacks.py
"""
Crowd-Control WebSocket DAT callbacks (TouchDesigner side).

Setup (SEPARATE from the 9980 MCP WebServer DAT — do not reuse it):
  1. Create a WebSocket DAT (e.g. /project1/crowd_ws).
  2. Network Address = the Khadas localhost or tunnel host; Port = 8080;
     Path/Request = /engine?secret=<ENGINE_SECRET>; Active = On.
  3. Point its Callbacks DAT at a Text DAT holding this script.
  4. Create three Table DATs as siblings: 'crowd_slots', 'crowd_signals', and a Text DAT 'crowd_code'.
  5. Feed crowd_slots into a DAT-to-CHOP (+ Lag CHOP) for your channel logic;
     composite crowd_code into a Text TOP on the projection.
"""

import json

BASE_COLS = ['slot', 'role', 'active', 'x', 'y']


def onConnect(webSocketDAT):
    code_dat = op('crowd_code')
    if code_dat is not None:
        code_dat.clear()
        code_dat.text = '...'
    return


def onDisconnect(webSocketDAT):
    return


def onReceiveText(webSocketDAT, contents):
    try:
        msg = json.loads(contents)
    except Exception:
        return

    mtype = msg.get('type')
    if mtype == 'snapshot':
        _apply_snapshot(msg)
    elif mtype == 'signal':
        _apply_signal(msg)
    return


def _apply_snapshot(msg):
    # code → Text DAT
    code_dat = op('crowd_code')
    if code_dat is not None:
        code_dat.clear()
        code_dat.text = str(msg.get('code') or '')

    slots = msg.get('slots', [])

    # discover the union of control-value columns present this frame
    val_cols = []
    for s in slots:
        for k in (s.get('vals') or {}).keys():
            if k not in val_cols:
                val_cols.append(k)

    table = op('crowd_slots')
    if table is None:
        return
    table.clear()
    table.appendRow(BASE_COLS + val_cols)
    for s in slots:
        vals = s.get('vals') or {}
        row = [
            s.get('slot'), s.get('role'), 1 if s.get('active') else 0,
            s.get('x', 0), s.get('y', 0),
        ]
        for c in val_cols:
            v = vals.get(c, '')
            # booleans → 0/1 so downstream CHOP conversion is numeric
            if isinstance(v, bool):
                v = 1 if v else 0
            row.append(v)
        table.appendRow(row)


def _apply_signal(msg):
    sig = op('crowd_signals')
    if sig is None:
        return
    if sig.numRows == 0:
        sig.appendRow(['slot', 'id', 'frame'])
    sig.appendRow([msg.get('slot'), msg.get('id'), absTime.frame])
    # keep the table bounded
    while sig.numRows > 200:
        sig.deleteRow(1)
