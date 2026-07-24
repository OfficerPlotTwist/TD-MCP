"""Local tests for step_tracks() — pure Python, no TD, no numpy required.

Run:  python touchdesigner/blobtrack/test_idtrack_logic.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from idtrack_callbacks import step_tracks

R = 0.08      # Matchradius used throughout
P = 30        # Persistframes used unless a test overrides


def step_empty(tracks, next_id, n):
    """Run n steps with no current blobs (full occlusion)."""
    for _ in range(n):
        blobs, tracks, next_id = step_tracks([], tracks, R, P, next_id)
    return tracks, next_id


def test_stationary_resume():
    # Marker tracked, fully covered 10 frames, returns at same spot -> same ID.
    blobs, tracks, nid = step_tracks([(100, 0.5, 0.5, 20.0)], [], R, P, 1)
    assert blobs[0][1] == 1
    tracks, nid = step_empty(tracks, nid, 10)
    assert len(tracks) == 1 and tracks[0][6] == 10          # ghost, miss=10
    blobs, tracks, nid = step_tracks([(100, 0.5, 0.5, 20.0)], tracks, R, P, nid)
    assert blobs[0][1] == 1, "stationary marker must resume its ID"
    assert tracks[0][6] == 0


def test_timeout_drop():
    # Ghost past Persistframes is dropped; return mints a fresh ID.
    blobs, tracks, nid = step_tracks([(100, 0.5, 0.5, 20.0)], [], R, 5, 1)
    for _ in range(6):                                      # persist=5, 6th miss drops
        blobs, tracks, nid = step_tracks([], tracks, R, 5, nid)
    assert tracks == [], "ghost must drop after persist frames"
    blobs, tracks, nid = step_tracks([(100, 0.5, 0.5, 20.0)], tracks, R, 5, nid)
    assert blobs[0][1] == 2, "expired track must NOT resume"


def test_fragment_cannot_steal():
    # 1 px fragment near a marker-sized ghost must not inherit its ID,
    # and the real marker must still resume afterwards.
    blobs, tracks, nid = step_tracks([(100, 0.5, 0.5, 51.0)], [], R, P, 1)
    tracks, nid = step_empty(tracks, nid, 2)                # ghost, miss=2
    blobs, tracks, nid = step_tracks([(200, 0.52, 0.5, 1.0)], tracks, R, P, nid)
    frag_ids = [b[1] for b in blobs]
    assert frag_ids == [2], "fragment must mint a new ID, not steal (got %s)" % frag_ids
    # fragment vanishes, marker returns
    blobs, tracks, nid = step_tracks([], tracks, R, P, nid)
    blobs, tracks, nid = step_tracks([(100, 0.5, 0.5, 50.0)], tracks, R, P, nid)
    ids = sorted(b[1] for b in blobs)
    assert 1 in ids, "marker must resume ID 1 (got %s)" % ids
    # symmetric gate: marker must not have taken the fragment's ghost either
    assert ids == [1]


def test_live_track_beats_ghost():
    # A blob near both its own live track and a big-radius ghost matches the live track.
    tracks = [
        (1, 0.50, 0.5, 0.0, 0.0, 20.0, 0),   # live
        (2, 0.52, 0.5, 0.0, 0.0, 20.0, 6),   # ghost with grown radius
    ]
    blobs, tracks2, nid = step_tracks([(100, 0.51, 0.5, 20.0)], tracks, R, P, 10)
    assert blobs[0][1] == 1, "live track must win over ghost"
    ghost = [t for t in tracks2 if t[0] == 2]
    assert ghost and ghost[0][6] == 7


def test_moving_marker_predicted_resume():
    # Track with velocity ghosts; blob re-appears along its path -> resumes.
    tracks = [(1, 0.5, 0.5, 0.01, 0.0, 20.0, 0)]
    tracks, nid = step_empty(tracks, 2, 8)
    ghost = tracks[0]
    assert ghost[1] > 0.54, "ghost must coast along +x (at %.4f)" % ghost[1]
    blobs, tracks, nid = step_tracks([(100, 0.55, 0.5, 20.0)], tracks, R, P, nid)
    assert blobs[0][1] == 1, "moving marker must resume via predicted position"


def test_velocity_cap():
    # A big correction on ghost resumption cannot produce runaway velocity.
    # Ghost at miss=2 -> radius 0.08*1.5 = 0.12; blob 0.11 away -> raw v = 0.055.
    tracks = [(1, 0.1, 0.1, 0.0, 0.0, 20.0, 2)]
    blobs, tracks, nid = step_tracks([(100, 0.21, 0.1, 20.0)], tracks, R, P, 2)
    assert blobs[0][1] == 1
    vx, vy = tracks[0][3], tracks[0][4]
    assert (vx * vx + vy * vy) ** 0.5 <= 0.05 + 1e-9, "velocity must be capped"


def test_legacy_tuple_tolerated():
    # Old (id, cx, cy, miss) storage tuples must still work; area gate disabled for them.
    tracks = [(9, 0.3, 0.3, 2)]
    blobs, tracks2, nid = step_tracks([(100, 0.31, 0.3, 1.0)], tracks, R, P, 10)
    assert blobs[0][1] == 9, "legacy ghost (area 0) must resume without area gate"
    assert len(tracks2[0]) == 7


def test_id_wrap():
    blobs, tracks, nid = step_tracks([(100, 0.5, 0.5, 20.0)], [], R, P, 1 << 23)
    assert blobs[0][1] == 1 << 23 and nid == 1


if __name__ == '__main__':
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print('PASS  %s' % name)
            except AssertionError as e:
                print('FAIL  %s: %s' % (name, e))
                fails += 1
    sys.exit(1 if fails else 0)
