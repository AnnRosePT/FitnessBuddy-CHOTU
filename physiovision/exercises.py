"""Exercise definitions and the repetition-counting state machine.

Every exercise is described by one joint angle (three MediaPipe landmarks:
A-B-C, the angle is measured at B) plus two reference angles:

  rest_angle  - the angle at the start / end position of the movement
  peak_angle  - the angle the user must reach for the rep to count as full

A repetition is counted when the user leaves the rest position, reaches the
peak, and returns to rest again. Movements that leave rest but never reach
the peak are counted separately as "partial" reps so the user gets feedback
on range of motion.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

# MediaPipe Pose landmark indices (33-point model)
NOSE = 0
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28

# Body connections drawn on the video (face points are skipped on purpose)
BODY_CONNECTIONS = [
    (L_SHOULDER, R_SHOULDER), (L_SHOULDER, L_ELBOW), (L_ELBOW, L_WRIST),
    (R_SHOULDER, R_ELBOW), (R_ELBOW, R_WRIST),
    (L_SHOULDER, L_HIP), (R_SHOULDER, R_HIP), (L_HIP, R_HIP),
    (L_HIP, L_KNEE), (L_KNEE, L_ANKLE), (R_HIP, R_KNEE), (R_KNEE, R_ANKLE),
    (L_ANKLE, 29), (29, 31), (L_ANKLE, 31), (R_ANKLE, 30), (30, 32), (R_ANKLE, 32),
]

# Fractions of the rest->peak range used as thresholds (hysteresis)
START_FRACTION = 0.25   # user has clearly left the rest position
RETURN_FRACTION = 0.10  # user is back at rest


@dataclass(frozen=True)
class Exercise:
    key: str
    name: str
    joint: str
    left: tuple[int, int, int]
    right: tuple[int, int, int]
    rest_angle: float
    peak_angle: float
    cue_start: str
    cue_peak: str
    cue_return: str
    description: str
    camera_tip: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("left")
        d.pop("right")
        return d


EXERCISES: dict[str, Exercise] = {
    e.key: e for e in [
        Exercise(
            key="bicep_curl", name="Bicep Curl", joint="Elbow",
            left=(L_SHOULDER, L_ELBOW, L_WRIST), right=(R_SHOULDER, R_ELBOW, R_WRIST),
            rest_angle=150, peak_angle=55,
            cue_start="Stand tall, arm straight by your side",
            cue_peak="Curl your hand up towards your shoulder",
            cue_return="Good. Lower your arm slowly",
            description="Elbow flexion. Keep the upper arm still against your side.",
            camera_tip="Face the camera or stand side-on, with your whole arm in view.",
        ),
        Exercise(
            key="squat", name="Squat", joint="Knee",
            left=(L_HIP, L_KNEE, L_ANKLE), right=(R_HIP, R_KNEE, R_ANKLE),
            rest_angle=160, peak_angle=100,
            cue_start="Stand with feet shoulder-width apart",
            cue_peak="Bend your knees and sit back",
            cue_return="Good depth. Push up to standing",
            description="Knee flexion. Keep your chest up and knees over your toes.",
            camera_tip="Stand side-on, 2-3 m from the camera, hips to ankles in view.",
        ),
        Exercise(
            key="shoulder_press", name="Shoulder Press", joint="Elbow",
            left=(L_SHOULDER, L_ELBOW, L_WRIST), right=(R_SHOULDER, R_ELBOW, R_WRIST),
            rest_angle=95, peak_angle=155,
            cue_start="Hands at shoulder height, elbows bent",
            cue_peak="Press your hands straight overhead",
            cue_return="Good. Bring your hands back to your shoulders",
            description="Elbow extension overhead. Avoid arching your lower back.",
            camera_tip="Face the camera with your hands visible above your head.",
        ),
        Exercise(
            key="lateral_raise", name="Lateral Raise", joint="Shoulder",
            left=(L_HIP, L_SHOULDER, L_ELBOW), right=(R_HIP, R_SHOULDER, R_ELBOW),
            rest_angle=30, peak_angle=80,
            cue_start="Arms relaxed by your sides",
            cue_peak="Lift your arm out sideways to shoulder height",
            cue_return="Good. Lower your arm with control",
            description="Shoulder abduction. Keep a soft bend in the elbow.",
            camera_tip="Face the camera with hips and hands in view.",
        ),
        Exercise(
            key="knee_raise", name="Standing Knee Raise", joint="Hip",
            left=(L_SHOULDER, L_HIP, L_KNEE), right=(R_SHOULDER, R_HIP, R_KNEE),
            rest_angle=160, peak_angle=115,
            cue_start="Stand straight; hold a chair for balance if needed",
            cue_peak="Lift your knee up towards your chest",
            cue_return="Good. Lower your foot back down",
            description="Hip flexion. Keep your back upright.",
            camera_tip="Stand side-on, with shoulders to knees in view.",
        ),
    ]
}


def joint_angle(a, b, c) -> float:
    """Angle ABC in degrees (0-180) from three (x, y) points."""
    bax, bay = a[0] - b[0], a[1] - b[1]
    bcx, bcy = c[0] - b[0], c[1] - b[1]
    na = math.hypot(bax, bay)
    nc = math.hypot(bcx, bcy)
    if na == 0 or nc == 0:
        return 0.0
    cos = (bax * bcx + bay * bcy) / (na * nc)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


class RepCounter:
    """Counts repetitions of one exercise from a stream of pose landmarks."""

    def __init__(self, exercise: Exercise, side: str = "auto", target: int = 10,
                 min_rep_seconds: float = 0.6, smoothing: float = 0.4,
                 visibility_threshold: float = 0.5):
        if side not in ("auto", "left", "right"):
            raise ValueError("side must be auto, left or right")
        self.ex = exercise
        self.side = side
        self.target = max(1, int(target))
        self.min_rep_seconds = min_rep_seconds
        self.alpha = smoothing
        self.vis_threshold = visibility_threshold

        self.reps = 0
        self.partial = 0
        self.stage = "rest"            # rest | moving | peak
        self.angle: float | None = None
        self.visible = False
        self.active_side: str | None = None if side == "auto" else side
        self.feedback = exercise.cue_start
        self.rep_id = 0                # increments on every counted rep
        self.rom_history: list[float] = []   # degrees of motion per full rep
        self._move_start = 0.0
        self._best = 0.0               # best progress reached this movement
        self._best_angle: float | None = None
        self._ready = False            # user has been seen in the rest position
        self._rest_extreme: float | None = None  # most rest-ward angle before this movement

    # ------------------------------------------------------------------ helpers
    def progress(self, angle: float) -> float:
        """0 at the rest angle, 1 at the peak angle (can go outside 0..1)."""
        return (angle - self.ex.rest_angle) / (self.ex.peak_angle - self.ex.rest_angle)

    @property
    def triplet(self) -> tuple[int, int, int] | None:
        if self.active_side is None:
            return None
        return self.ex.left if self.active_side == "left" else self.ex.right

    def _side_visibility(self, lms, idx) -> float:
        return min(lms[i][2] for i in idx)

    # ------------------------------------------------------------------- update
    def update(self, landmarks, t: float) -> None:
        """landmarks: list of 33 (x, y, visibility) tuples, or None."""
        if not landmarks:
            self.visible = False
            self.feedback = "No one detected. Step into the camera view"
            return

        if self.side == "auto":
            vl = self._side_visibility(landmarks, self.ex.left)
            vr = self._side_visibility(landmarks, self.ex.right)
            if self.active_side is None:
                self.active_side = "left" if vl >= vr else "right"
            # switch side only when the other is clearly better (avoids flicker)
            elif self.active_side == "left" and vr > vl + 0.2 and self.stage == "rest":
                self.active_side = "right"
            elif self.active_side == "right" and vl > vr + 0.2 and self.stage == "rest":
                self.active_side = "left"

        idx = self.triplet
        vis = self._side_visibility(landmarks, idx)
        if vis < self.vis_threshold:
            self.visible = False
            self.feedback = f"Can't see your {self.active_side} {self.ex.joint.lower()} clearly. " \
                            f"{self.ex.camera_tip}"
            return
        self.visible = True
        a, b, c = (landmarks[i] for i in idx)
        self.update_angle(joint_angle(a, b, c), t)

    def update_angle(self, raw_angle: float, t: float) -> None:
        """Advance the state machine with a new joint angle (degrees)."""
        if self.angle is None:
            self.angle = raw_angle
        else:
            self.angle = self.alpha * raw_angle + (1 - self.alpha) * self.angle
        p = self.progress(self.angle)

        if not self._ready:
            if p <= RETURN_FRACTION:
                self._ready = True
                self.feedback = self.ex.cue_peak
            else:
                self.feedback = self.ex.cue_start
            return

        if self.stage == "rest":
            if self._rest_extreme is None or p < self.progress(self._rest_extreme):
                self._rest_extreme = self.angle
            if p > START_FRACTION:
                self.stage = "moving"
                self._move_start = t
                self._best = p
                self._best_angle = self.angle
        if self.stage in ("moving", "peak"):
            if p > self._best:
                self._best = p
                self._best_angle = self.angle
            if self.stage == "moving":
                if p >= 1.0:
                    self.stage = "peak"
                    self.feedback = self.ex.cue_return
                else:
                    self.feedback = f"Keep going: {min(99, int(p * 100))}% of the range"
            if p <= RETURN_FRACTION:
                self._finish_movement(t)

    def _finish_movement(self, t: float) -> None:
        if self.stage == "peak":
            if t - self._move_start < self.min_rep_seconds:
                self.feedback = "Too fast. Slow down and control the movement"
            else:
                self.reps += 1
                self.rep_id += 1
                start = self._rest_extreme if self._rest_extreme is not None else self.ex.rest_angle
                self.rom_history.append(round(abs(start - self._best_angle), 1))
                if self.reps == self.target:
                    self.feedback = f"Target of {self.target} reached! Well done"
                elif self.reps > self.target:
                    self.feedback = f"Rep {self.reps}. Past your target"
                else:
                    self.feedback = f"Rep {self.reps} done. {self.target - self.reps} to go"
        else:
            self.partial += 1
            self.feedback = (f"Partial rep. Try to reach {self.ex.peak_angle:.0f}° "
                             f"(you reached {self._best_angle:.0f}°)")
        self.stage = "rest"
        self._rest_extreme = self.angle
        self._best = 0.0
        self._best_angle = None

    # -------------------------------------------------------------------- state
    @property
    def avg_rom(self) -> float | None:
        if not self.rom_history:
            return None
        return round(sum(self.rom_history) / len(self.rom_history), 1)

    def to_dict(self) -> dict:
        return {
            "exercise": self.ex.key,
            "name": self.ex.name,
            "joint": self.ex.joint,
            "rest_angle": self.ex.rest_angle,
            "peak_angle": self.ex.peak_angle,
            "side": self.side,
            "active_side": self.active_side,
            "reps": self.reps,
            "target": self.target,
            "partial": self.partial,
            "stage": self.stage,
            "angle": None if self.angle is None else round(self.angle, 1),
            "progress": None if self.angle is None else round(self.progress(self.angle), 3),
            "visible": self.visible,
            "feedback": self.feedback,
            "rep_id": self.rep_id,
            "avg_rom": self.avg_rom,
            "completed": self.reps >= self.target,
        }
