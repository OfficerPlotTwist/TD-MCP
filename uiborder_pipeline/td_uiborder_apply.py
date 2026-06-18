"""TD-sync step for the `uib` pipeline. Exec'd inside TouchDesigner by
/looksgood via mcp__touchdesigner__execute_script:
    exec(open(r'.../uiborder_pipeline/td_uiborder_apply.py', encoding='utf-8').read())

Reads selections.json and applies each chosen blur size to the live
/project1/blurN op, then saves. Acquires the TD_MCP file lock first (single
agent at a time). Flat code only — execute_script wrapper can't see nested defs.
"""
import json

SEL = r"C:/Users/nik/Documents/AI/MCP/TD MCP/uiborder_pipeline/selections.json"
_lk = mod('/project1/TD_MCP/text_lockapi')
_lg = mod('/project1/TD_MCP/text_logapi')
_owner = "looksgood-uib"

if _lk.acquire(_owner, ttl=60, note="apply uiborder blur selections"):
    try:
        _data = {}
        try:
            _fh = open(SEL, "r", encoding="utf-8")
            _data = json.load(_fh)
            _fh.close()
        except Exception:
            _data = {}
        _applied = {}
        for _blur in ['blur1', 'blur2', 'blur3']:
            if _blur in _data:
                _o = op('/project1/' + _blur)
                if _o:
                    _o.par.size = _data[_blur]['size']
                    _applied[_blur] = _data[_blur]['size']
        project.save()
        _lg.done("Apply uiborder blur selections to live TD", "completed", str(_applied))
        print(json.dumps({"ok": True, "applied": _applied}))
    finally:
        _lk.release(_owner)
else:
    print(json.dumps({"ok": False, "error": "TD busy (lock held by another agent)"}))
