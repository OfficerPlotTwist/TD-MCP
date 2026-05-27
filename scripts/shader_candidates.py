"""Build candidates.json: the ranked, texture-free shader pool for review.

Joins the OpenGLSL corpus manifest (sid -> origin/src_id/src_name) with
findings.json (composite_score + baseline render thumbnail, keyed by ShaderToy
shader_id == manifest src_id for origin 'shadertoy'), scans each .frag for
iChannel texture dependence, and emits a pool sorted by composite_score desc.

Pool membership (v1, per approved plan):
  has a composite_score  AND  not texture-dependent.

Usage:  python shader_candidates.py
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shader_pipeline"))
from _db import CANDIDATES_DB, fwd, now_iso, save_db  # noqa: E402

CORPUS = Path(r"C:\Users\nik\Documents\AI\OpenGLSL_Code_Reference")
MANIFEST = CORPUS / "dailies" / "shaders" / "manifest_in.json"
FINDINGS = CORPUS / "findings.json"
FRAG_DIR = CORPUS / "dailies" / "shaders"

# Definitive external-texture signal -> skip in v1.
TEXTURE_RE = re.compile(r"iChannel\d?|texelFetch\s*\(")


def resolve_thumb(origin: str, src_id, findings_screenshot: str | None) -> str | None:
    """Prefer the findings baseline render; fall back to source-keyed thumbs."""
    candidates = []
    if findings_screenshot:
        candidates.append(CORPUS / findings_screenshot)
    sid_s = str(src_id)
    if origin == "shadertoy":
        candidates.append(CORPUS / "shadertoy_thumbs" / f"{sid_s}.jpg")
    else:
        candidates.append(CORPUS / "glslsandbox_thumbs" / f"{sid_s}.png")
        candidates.append(CORPUS / "thumbs" / f"{sid_s}.png")
    for c in candidates:
        if c.exists():
            return fwd(c)
    return None


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    findings = json.loads(FINDINGS.read_text(encoding="utf-8"))

    # findings keyed by shader_id (== shadertoy src_id)
    fmap = {}
    for f in findings:
        sid_key = str(f.get("shader_id"))
        br = f.get("baseline_render") or {}
        score = ((br.get("metrics") or {}).get("methods") or {}).get("composite_score")
        fmap[sid_key] = {
            "score": score,
            "screenshot": br.get("screenshot"),
            "name": f.get("shader_name") or "",
            "description": f.get("description") or "",
        }

    candidates = []
    n_scored = n_texture = n_pool = n_missing_thumb = 0
    for m in manifest:
        sid = m["sid"]
        origin = m["origin"]
        src_id = m["src_id"]
        frag = FRAG_DIR / f"{sid}.frag"
        src = frag.read_text(encoding="utf-8", errors="ignore") if frag.exists() else ""
        uses_texture = bool(TEXTURE_RE.search(src))

        f = fmap.get(str(src_id), {})
        score = f.get("score")
        if score is not None:
            n_scored += 1
        if uses_texture:
            n_texture += 1

        thumb = resolve_thumb(origin, src_id, f.get("screenshot"))
        entry = {
            "sid": sid,
            "origin": origin,
            "src_id": src_id,
            "src_name": f.get("name") or m.get("src_name") or "",
            "description": (f.get("description") or "")[:500],
            "frag_path": fwd(frag),
            "thumb_path": thumb,
            "composite_score": score,
            "uses_texture": uses_texture,
            "reviewed": False,
        }
        # Pool = scored AND texture-free AND has a thumbnail on disk.
        in_pool = score is not None and not uses_texture and thumb is not None
        entry["in_pool"] = in_pool
        if score is not None and not uses_texture and thumb is None:
            n_missing_thumb += 1
        if in_pool:
            n_pool += 1
        candidates.append(entry)

    # Sort: pool members first by score desc, then the rest.
    candidates.sort(
        key=lambda e: (e["in_pool"], e["composite_score"] or -1.0),
        reverse=True,
    )

    save_db(CANDIDATES_DB, {
        "generated_at": now_iso(),
        "corpus": fwd(CORPUS),
        "total": len(candidates),
        "scored": n_scored,
        "texture_dependent": n_texture,
        "pool_size": n_pool,
        "candidates": candidates,
    })

    print(f"total={len(candidates)} scored={n_scored} texture_dep={n_texture} "
          f"pool={n_pool} scored_but_no_thumb={n_missing_thumb}")
    print(f"wrote {CANDIDATES_DB}")
    print("top of pool:")
    for e in [c for c in candidates if c["in_pool"]][:5]:
        print(f"  {e['sid']} {e['src_id']:<8} score={e['composite_score']:.4f} "
              f"{e['src_name'][:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
