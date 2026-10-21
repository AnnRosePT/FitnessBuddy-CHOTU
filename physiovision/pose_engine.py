"""Webcam capture, MediaPipe pose estimation and frame annotation.

Runs in a background thread: reads frames with OpenCV, finds 33 body
landmarks with the MediaPipe Pose Landmarker, feeds them to the active
RepCounter and keeps the latest annotated frame as JPEG for the browser.
"""
from __future__ import annotations

import math
import os
import threading
import time
import urllib.request

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

from exercises import BODY_CONNECTIONS, EXERCISES, RepCounter

MODEL_URLS = {
    "lite": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
            "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
    "full": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
            "pose_landmarker_full/float16/latest/pose_landmarker_full.task",
    "heavy": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
             "pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task",
}
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

# Colours (BGR)
C_BONE = (225, 228, 226)
C_JOINT = (255, 255, 255)
C_ACCENT = (108, 70, 226)    # tape pink  #E2466C
C_ACCENT2 = (216, 123, 30)   # tape blue  #1E7BD8
C_PILL = (32, 30, 22)


def ensure_model(variant: str = "full") -> str:
    """Return the local path of the pose model, downloading it on first run."""
    os.makedirs(MODEL_DIR, exist_ok=True)
    path = os.path.join(MODEL_DIR, f"pose_landmarker_{variant}.task")
    if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
        return path
    url = MODEL_URLS[variant]
    print(f"[PhysioVision] Downloading pose model ({variant}) ...")
    tmp = path + ".part"
    try:
        urllib.request.urlretrieve(url, tmp)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"Could not download the MediaPipe model: {exc}\n"
            f"Download it manually from\n  {url}\nand save it as\n  {path}"
        ) from exc
    os.replace(tmp, path)
    print(f"[PhysioVision] Model saved to {path}")
    return path


class Session:
    def __init__(self, exercise_key: str, side: str, target: int, profile: str):
        self.exercise = EXERCISES[exercise_key]
        self.counter = RepCounter(self.exercise, side=side, target=target)
        self.profile = profile.strip() or "Me"
        self.started_wall = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._t0 = time.monotonic()
        self._paused_total = 0.0
        self._pause_start: float | None = None

    @property
    def paused(self) -> bool:
        return self._pause_start is not None

    def pause(self):
        if self._pause_start is None:
            self._pause_start = time.monotonic()

    def resume(self):
        if self._pause_start is not None:
            self._paused_total += time.monotonic() - self._pause_start
            self._pause_start = None

    @property
    def elapsed(self) -> float:
        now = self._pause_start if self._pause_start is not None else time.monotonic()
        return max(0.0, now - self._t0 - self._paused_total)

    def summary(self) -> dict:
        c = self.counter
        return {
            "profile": self.profile,
            "exercise": self.exercise.key,
            "exercise_name": self.exercise.name,
            "side": c.active_side or c.side,
            "reps": c.reps,
            "target": c.target,
            "partial_reps": c.partial,
            "duration_s": round(self.elapsed, 1),
            "avg_rom": c.avg_rom,
            "started_at": self.started_wall,
            "ended_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }


class PoseEngine:
    def __init__(self, source=0, mirror: bool | None = None, width: int = 960,
                 model: str = "full"):
        self.source = source
        self.is_file = isinstance(source, str)
        self.mirror = (not self.is_file) if mirror is None else mirror
        self.width = width
        self.model_path = ensure_model(model)

        self.lock = threading.Lock()
        self.session: Session | None = None
        self.camera_ok = False
        self.person = False
        self.fps = 0.0
        self._jpeg = self._placeholder("Starting camera...")
        self._frame_id = 0
        self._running = False
        self._thread: threading.Thread | None = None

    # ----------------------------------------------------------- lifecycle
    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="pose-engine", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    # ------------------------------------------------------------ sessions
    def start_session(self, exercise_key: str, side: str, target: int, profile: str) -> dict:
        with self.lock:
            self.session = Session(exercise_key, side, target, profile)
            return self._state_locked()

    def pause(self, paused: bool):
        with self.lock:
            if self.session:
                self.session.pause() if paused else self.session.resume()

    def end_session(self) -> dict | None:
        with self.lock:
            s, self.session = self.session, None
            return s.summary() if s else None

    def state(self) -> dict:
        with self.lock:
            return self._state_locked()

    def _state_locked(self) -> dict:
        s = self.session
        sess = None
        if s:
            sess = s.counter.to_dict()
            sess.update(elapsed=round(s.elapsed, 1), paused=s.paused, profile=s.profile)
        return {
            "camera_ok": self.camera_ok,
            "person": self.person,
            "fps": round(self.fps, 1),
            "source": "video file" if self.is_file else "webcam",
            "session": sess,
        }

    # -------------------------------------------------------------- frames
    def latest_jpeg(self) -> tuple[int, bytes]:
        with self.lock:
            return self._frame_id, self._jpeg

    def _set_jpeg(self, data: bytes):
        with self.lock:
            self._jpeg = data
            self._frame_id += 1

    def _placeholder(self, text: str) -> bytes:
        h = int(self.width * 9 / 16)
        img = np.full((h, self.width, 3), (34, 30, 24), np.uint8)
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.putText(img, text, ((self.width - tw) // 2, (h + th) // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 205, 210), 2, cv2.LINE_AA)
        return cv2.imencode(".jpg", img)[1].tobytes()

    def _open(self):
        cap = cv2.VideoCapture(self.source)
        if not self.is_file:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        if not cap.isOpened():
            cap.release()
            return None
        return cap

    def _loop(self):
        options = vision.PoseLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=self.model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        landmarker = vision.PoseLandmarker.create_from_options(options)
        cap = None
        last_ts = -1
        last_t = time.monotonic()
        file_frame_dt = 1 / 30
        try:
            while self._running:
                if cap is None:
                    cap = self._open()
                    if cap is None:
                        self.camera_ok = False
                        self._set_jpeg(self._placeholder(
                            "Camera not found. Close other apps using it, then wait..."))
                        time.sleep(1.5)
                        continue
                    if self.is_file:
                        fps = cap.get(cv2.CAP_PROP_FPS) or 30
                        file_frame_dt = 1 / max(1, fps)

                loop_start = time.monotonic()
                ok, frame = cap.read()
                if not ok:
                    if self.is_file:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)   # loop the demo video
                        continue
                    cap.release()
                    cap = None
                    continue
                self.camera_ok = True

                h, w = frame.shape[:2]
                if w != self.width:
                    frame = cv2.resize(frame, (self.width, int(h * self.width / w)))

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                ts = int(time.monotonic() * 1000)
                if ts <= last_ts:
                    ts = last_ts + 1
                last_ts = ts
                result = landmarker.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)

                lms = None
                if result.pose_landmarks:
                    lms = [(p.x, p.y, p.visibility if p.visibility is not None else 1.0)
                           for p in result.pose_landmarks[0]]

                now = time.monotonic()
                with self.lock:
                    self.person = lms is not None
                    session = self.session
                    if session and not session.paused:
                        session.counter.update(lms, now)
                    triplet = session.counter.triplet if session and session.counter.visible else None
                    angle = session.counter.angle if session else None
                    stage = session.counter.stage if session else None

                if self.mirror:
                    frame = cv2.flip(frame, 1)
                self._draw(frame, lms, triplet, angle, stage)

                dt = now - last_t
                last_t = now
                if dt > 0:
                    self.fps = 1 / dt if self.fps == 0 else 0.9 * self.fps + 0.1 / dt
                self._set_jpeg(cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes())

                if self.is_file:
                    time.sleep(max(0.0, file_frame_dt - (time.monotonic() - loop_start)))
        finally:
            landmarker.close()
            if cap is not None:
                cap.release()

    # ------------------------------------------------------------- drawing
    def _draw(self, frame, lms, triplet, angle, stage):
        if not lms:
            return
        h, w = frame.shape[:2]

        def pt(i):
            x, y, _ = lms[i]
            x = 1 - x if self.mirror else x
            return int(x * w), int(y * h)

        def vis(i):
            return lms[i][2] > 0.5

        for a, b in BODY_CONNECTIONS:
            if vis(a) and vis(b):
                cv2.line(frame, pt(a), pt(b), C_BONE, 2, cv2.LINE_AA)
        for i in range(11, 33):
            if vis(i):
                cv2.circle(frame, pt(i), 4, C_JOINT, -1, cv2.LINE_AA)

        if not triplet or angle is None:
            return
        a, b, c = (pt(i) for i in triplet)
        colour = C_ACCENT2 if stage == "peak" else C_ACCENT
        cv2.line(frame, a, b, colour, 6, cv2.LINE_AA)
        cv2.line(frame, b, c, colour, 6, cv2.LINE_AA)
        for p in (a, b, c):
            cv2.circle(frame, p, 9, colour, -1, cv2.LINE_AA)
            cv2.circle(frame, p, 9, C_JOINT, 2, cv2.LINE_AA)

        # goniometer arc at the measured joint
        ang1 = math.degrees(math.atan2(a[1] - b[1], a[0] - b[0]))
        ang2 = math.degrees(math.atan2(c[1] - b[1], c[0] - b[0]))
        diff = (ang2 - ang1) % 360
        start, end = (ang1, ang1 + diff) if diff <= 180 else (ang2, ang2 + 360 - diff)
        r = max(24, int(0.06 * w))
        cv2.ellipse(frame, b, (r, r), 0, start, end, C_JOINT, 2, cv2.LINE_AA)

        # angle label
        label = f"{angle:.0f}"
        font, scale, thick = cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2
        (tw, th), _ = cv2.getTextSize(label, font, scale, thick)
        x = min(max(8, b[0] + r + 10), w - tw - 30)
        y = min(max(th + 12, b[1] + th // 2), h - 10)
        cv2.rectangle(frame, (x - 10, y - th - 10), (x + tw + 22, y + 10), C_PILL, -1)
        cv2.putText(frame, label, (x, y), font, scale, C_JOINT, thick, cv2.LINE_AA)
        cv2.circle(frame, (x + tw + 8, y - th + 3), 4, C_JOINT, 2, cv2.LINE_AA)  # degree sign
