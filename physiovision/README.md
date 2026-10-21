# PhysioVision AI

A computer-vision exercise monitor that runs on a normal webcam. It finds 33 body
landmarks with **MediaPipe Pose**, works out joint angles in **Python**, counts
repetitions in real time and shows everything in a **web interface** (Flask + HTML/JS).

> Educational prototype. It does not replace assessment or advice from a
> physiotherapist or doctor.

## Features

- Live webcam view with the body skeleton, the measured joint highlighted and its angle drawn on the frame
- 5 exercises: Bicep Curl, Squat, Shoulder Press, Lateral Raise, Standing Knee Raise
- Automatic rep counting with a target, a progress ring and a goniometer-style angle gauge
- Movement phases (Start position → Moving → Target reached)
- Feedback: partial reps, too-fast reps, joint not visible, no one in view
- Left / right / auto-detect side
- Reps counted out loud (browser speech)
- Profiles for each family member, session history saved in SQLite, a 7-day reps chart
- Works with a video file too (useful for demos and testing)

## Setup

Python 3.9 or newer.

```bash
cd physiovision
python -m venv venv
# Windows:  venv\Scripts\activate
# macOS/Linux:  source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

On first run the app downloads the MediaPipe pose model (about 9 MB) into `models/`.
If you are offline, download `pose_landmarker_full.task` from the URL printed in the error
message and put it in `models/` yourself.

### Options

```bash
python app.py --source 1            # use a second webcam
python app.py --source demo.mp4     # run on a recorded video (loops)
python app.py --model lite          # faster on slow laptops (heavy = most accurate)
python app.py --no-mirror           # don't mirror the webcam image
python app.py --host 0.0.0.0        # open it from a phone/tablet on the same Wi-Fi
```

### Tests

```bash
python -m pytest tests      # or: python tests/test_counter.py
```

The tests cover angle maths, rep counting for every exercise, partial reps, too-fast reps,
noise near the thresholds, side detection and the web API. They need no camera or model.

## How it works

```
Webcam ──OpenCV──▶ frame ──MediaPipe Pose Landmarker──▶ 33 landmarks (x, y, visibility)
                                                            │
                         joint angle at B for landmarks A-B-C (e.g. shoulder-elbow-wrist)
                                                            │
                         smoothing (EMA) ─▶ rep state machine ─▶ reps, phase, feedback
                                                            │
             Flask: /video_feed (MJPEG)   /api/state (JSON)   /api/history (SQLite)
                                                            │
                                          Browser UI (HTML/CSS/JS)
```

**Joint angle.** For landmarks A, B, C the angle at B is
`θ = arccos( (BA · BC) / (|BA| |BC|) )`.

**Rep counting.** Each exercise has a *rest angle* (start position) and a *peak angle*
(the target). Progress is `p = (θ − rest) / (peak − rest)`, so 0 = start and 1 = target.

| Phase  | Enters when            |
|--------|------------------------|
| Start  | p ≤ 0.10               |
| Moving | p > 0.25 (from Start)  |
| Peak   | p ≥ 1.0                |

A rep counts when the user goes Start → Moving → Peak → back to Start, taking at least
0.6 s. Leaving Start but returning without reaching Peak counts as a **partial rep**. The
gap between the 0.10 and 0.25 thresholds (hysteresis) plus smoothing stops jitter from
double-counting. Landmarks with visibility below 0.5 are ignored.

| Exercise            | Joint (A-B-C)               | Rest | Peak |
|---------------------|-----------------------------|------|------|
| Bicep Curl          | Elbow (shoulder-elbow-wrist)| 150° | 55°  |
| Squat               | Knee (hip-knee-ankle)       | 160° | 100° |
| Shoulder Press      | Elbow (shoulder-elbow-wrist)| 95°  | 155° |
| Lateral Raise       | Shoulder (hip-shoulder-elbow)| 30° | 80°  |
| Standing Knee Raise | Hip (shoulder-hip-knee)     | 160° | 115° |

Change these values in `exercises.py`. Adding an exercise means adding one `Exercise(...)` entry.

**Avg range** is the average range of motion per full rep, in degrees.

## Project structure

```
app.py            Flask server, routes, command-line options
pose_engine.py    Camera thread, MediaPipe inference, drawing on frames, sessions
exercises.py      Exercise definitions, angle maths, RepCounter state machine
storage.py        SQLite session history (data/physiovision.db)
templates/        index.html
static/           style.css, app.js
tests/            test_counter.py
```

## Tips for accurate counting

- Stand 2–3 m from the camera with good front lighting and the whole working limb in view.
- Squats and knee raises work best side-on; arm exercises work facing the camera.
- Only one person should be in the frame.

## Limitations

- 2D angles from a single camera change with the viewing angle.
- Thresholds are general, not personalised or clinically validated.
- Tracks one person at a time.
