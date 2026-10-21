"""Tests for the rep-counting logic and the web API (no camera or model needed).

Run:  python -m pytest tests      or      python tests/test_counter.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import storage  # noqa: E402
from exercises import EXERCISES, RepCounter, joint_angle  # noqa: E402


def feed(counter, angles, t0=0.0, dt=0.1):
    t = t0
    for a in angles:
        counter.update_angle(a, t)
        t += dt
    return t


def ramp(a, b, steps=12):
    return [a + (b - a) * i / (steps - 1) for i in range(steps)]


def full_rep(rest, peak, hold=4):
    return ramp(rest, peak) + [peak] * hold + ramp(peak, rest) + [rest] * hold


def test_joint_angle():
    assert round(joint_angle((0, 1), (0, 0), (1, 0))) == 90
    assert round(joint_angle((-1, 0), (0, 0), (1, 0))) == 180
    assert round(joint_angle((1, 0), (0, 0), (1, 0))) == 0


def test_counts_full_reps_for_every_exercise():
    for ex in EXERCISES.values():
        rest = ex.rest_angle + (10 if ex.peak_angle < ex.rest_angle else -10)
        peak = ex.peak_angle + (-10 if ex.peak_angle < ex.rest_angle else 10)
        c = RepCounter(ex, side="left", target=3, smoothing=1.0)
        seq = [rest] * 3
        for _ in range(3):
            seq += full_rep(rest, peak)
        feed(c, seq)
        assert c.reps == 3, (ex.key, c.reps)
        assert c.partial == 0
        assert c.to_dict()["completed"]


def test_partial_rep_is_not_counted():
    ex = EXERCISES["bicep_curl"]
    c = RepCounter(ex, side="right", smoothing=1.0)
    feed(c, [165] * 3 + ramp(165, 100) + ramp(100, 165) + [165] * 3)
    assert c.reps == 0 and c.partial == 1
    assert "Partial" in c.feedback


def test_too_fast_rep_is_rejected():
    ex = EXERCISES["squat"]
    c = RepCounter(ex, side="left", smoothing=1.0, min_rep_seconds=0.6)
    feed(c, [170, 170, 90, 170], dt=0.1)   # 0.2 s from start to finish
    assert c.reps == 0
    assert "Too fast" in c.feedback


def test_waits_for_start_position():
    ex = EXERCISES["bicep_curl"]
    c = RepCounter(ex, side="left", smoothing=1.0)
    feed(c, [50, 50, 50])                   # starts already curled
    assert c.reps == 0 and c.stage == "rest"
    assert c.feedback == ex.cue_start


def test_jitter_near_threshold_does_not_double_count():
    ex = EXERCISES["bicep_curl"]
    c = RepCounter(ex, side="left", smoothing=1.0)
    seq = [165] * 3 + ramp(165, 45) + [52, 48, 53, 47, 52] + ramp(45, 165) + [165] * 3
    feed(c, seq)
    assert c.reps == 1


def test_landmark_visibility_and_auto_side():
    ex = EXERCISES["bicep_curl"]
    c = RepCounter(ex, side="auto")
    lms = [(0.5, 0.5, 0.0)] * 33
    lms = list(lms)
    # right arm visible and straight, left arm hidden
    lms[12], lms[14], lms[16] = (0.5, 0.3, 0.9), (0.5, 0.5, 0.9), (0.5, 0.7, 0.9)
    c.update(lms, 0.0)
    assert c.active_side == "right" and c.visible
    assert round(c.angle) == 180
    c.update(None, 0.1)
    assert not c.visible and "No one" in c.feedback


def test_api_with_fake_engine():
    from app import create_app

    class FakeEngine:
        def __init__(self):
            self.session = None
        def latest_jpeg(self):
            return 0, b""
        def state(self):
            return {"camera_ok": True, "person": True, "fps": 30.0, "source": "webcam",
                    "session": self.session}
        def start_session(self, key, side, target, profile):
            self.session = {"exercise": key, "reps": 0, "target": target}
            return self.state()
        def pause(self, paused):
            pass
        def end_session(self):
            s, self.session = self.session, None
            if s is None:
                return None
            return {"profile": "Amma", "exercise": "squat", "exercise_name": "Squat",
                    "side": "left", "reps": 8, "target": 10, "partial_reps": 1,
                    "duration_s": 61.0, "avg_rom": 96.5,
                    "started_at": "2026-10-20T09:00:00", "ended_at": "2026-10-20T09:01:01"}

    storage.DB_PATH = os.path.join(tempfile.mkdtemp(), "test.db")
    client = create_app(FakeEngine()).test_client()
    assert client.get("/").status_code == 200
    assert client.post("/api/session/start", json={"exercise": "nope"}).status_code == 400
    r = client.post("/api/session/start", json={"exercise": "squat", "target": 10, "profile": "Amma"})
    assert r.status_code == 200 and r.json["session"]["exercise"] == "squat"
    r = client.post("/api/session/finish", json={})
    assert r.json["saved"] and r.json["summary"]["id"] == 1
    h = client.get("/api/history?profile=Amma").json
    assert h["sessions"][0]["reps"] == 8 and h["profiles"] == ["Amma"]
    assert len(h["daily"]) == 7
    assert client.delete("/api/history/1").json["deleted"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
