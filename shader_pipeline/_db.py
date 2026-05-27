"""Tiny JSON-as-DB helpers for the shader curation pipeline.

Mirrors the house pattern from td-mcp-server/checkpoints.js: each DB file is a
single JSON object with one top-level collection key holding a list, pretty
printed with 2-space indent so it stays hand-editable. Paths are stored with
forward slashes (even on Windows) to match the checkpoints index convention.
"""
from __future__ import annotations
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
# Review-grid PNGs live outside the repo, under AI/Busdriver. Each curation
# pipeline gets its own subdirectory under review_grids/ (the watcher scans these
# and regenerates any that go empty). This is the GLSL shader pipeline's folder.
GRID_REVIEW_ROOT = Path(r"C:\Users\nik\Documents\AI\Busdriver\review_grids")
GRID_IMG_DIR = GRID_REVIEW_ROOT / "GLSL implement with agents"

# Canonical DB file paths (verbose, absolute).
CANDIDATES_DB = PIPELINE_DIR / "candidates.json"
REVIEW_GRIDS_DB = PIPELINE_DIR / "review_grids.json"
GOOD_SHADERS_DB = PIPELINE_DIR / "human_selected_good_shaders.json"
QUEUE_DB = PIPELINE_DIR / "implementation_queue.json"
REJECTED_DB = PIPELINE_DIR / "rejected_shaders.json"


def now_iso() -> str:
    """UTC ISO-8601 with milliseconds + Z, matching checkpoints/index.json."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
        f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"


def fwd(p) -> str:
    """Absolute path with forward slashes for storage in DB records."""
    return str(Path(p).resolve()).replace("\\", "/")


def load_db(path, collection_key: str) -> dict:
    """Load a DB file, returning {collection_key: [...]} (empty if absent/corrupt)."""
    path = Path(path)
    if not path.exists():
        return {collection_key: []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {collection_key: []}
    if collection_key not in data or not isinstance(data.get(collection_key), list):
        data[collection_key] = []
    return data


def save_db(path, data: dict) -> None:
    """Atomically write a DB file (temp file + os.replace) so a concurrent
    reader never sees a partial file. Ensures the parent dir exists."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)  # atomic on the same filesystem (incl. Windows)


LOCK_PATH = PIPELINE_DIR / ".pipeline.lock"


class _PipelineLock:
    """Coarse cross-process mutex for the whole pipeline so parallel agents
    serialize their read-modify-write of the shared JSON DBs. Uses exclusive
    file creation (works on Windows); a lock left by a crashed process is
    reclaimed after `stale` seconds."""

    def __init__(self, timeout: float = 30.0, stale: float = 120.0):
        self.timeout = timeout
        self.stale = stale
        self.fd = None

    def __enter__(self):
        start = time.time()
        while True:
            try:
                self.fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.write(self.fd, f"{os.getpid()} {time.time():.0f}".encode())
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(LOCK_PATH) > self.stale:
                        os.remove(LOCK_PATH)
                        continue
                except OSError:
                    pass
                if time.time() - start > self.timeout:
                    raise TimeoutError(
                        f"could not acquire pipeline lock ({LOCK_PATH}) within {self.timeout}s")
                time.sleep(0.05)

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
            try:
                os.remove(LOCK_PATH)
            except OSError:
                pass
        return False


def pipeline_lock(timeout: float = 30.0) -> "_PipelineLock":
    """Context manager: `with pipeline_lock(): <read-modify-write DBs>`."""
    return _PipelineLock(timeout=timeout)
