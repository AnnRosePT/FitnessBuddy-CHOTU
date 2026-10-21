"""PhysioVision AI - web application entry point.

Run:  python app.py                 (default webcam)
      python app.py --source 1      (second webcam)
      python app.py --source demo.mp4
Then open http://127.0.0.1:5000 in your browser.
"""
from __future__ import annotations

import argparse
import time

from flask import Flask, Response, jsonify, render_template, request

import storage
from exercises import EXERCISES


def create_app(engine) -> Flask:
    app = Flask(__name__)
    storage.init()

    @app.get("/")
    def index():
        return render_template("index.html",
                               exercises=[e.to_dict() for e in EXERCISES.values()])

    @app.get("/video_feed")
    def video_feed():
        def frames():
            last_id = -1
            while True:
                fid, jpeg = engine.latest_jpeg()
                if fid != last_id:
                    last_id = fid
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n"
                           b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                           + jpeg + b"\r\n")
                time.sleep(0.02)
        return Response(frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.get("/api/exercises")
    def exercises():
        return jsonify([e.to_dict() for e in EXERCISES.values()])

    @app.get("/api/state")
    def state():
        return jsonify(engine.state())

    @app.post("/api/session/start")
    def start():
        body = request.get_json(silent=True) or {}
        key = body.get("exercise")
        side = body.get("side", "auto")
        if key not in EXERCISES:
            return jsonify(error=f"Unknown exercise '{key}'"), 400
        if side not in ("auto", "left", "right"):
            return jsonify(error="Side must be auto, left or right"), 400
        try:
            target = int(body.get("target", 10))
        except (TypeError, ValueError):
            return jsonify(error="Target reps must be a number"), 400
        target = max(1, min(target, 200))
        profile = str(body.get("profile", "Me"))[:40]
        return jsonify(engine.start_session(key, side, target, profile))

    @app.post("/api/session/pause")
    def pause():
        engine.pause(bool((request.get_json(silent=True) or {}).get("paused", True)))
        return jsonify(engine.state())

    @app.post("/api/session/finish")
    def finish():
        summary = engine.end_session()
        if summary is None:
            return jsonify(error="No session is running"), 400
        saved = summary["reps"] > 0 or summary["partial_reps"] > 0
        if saved:
            summary["id"] = storage.save(summary)
        return jsonify(saved=saved, summary=summary)

    @app.post("/api/session/cancel")
    def cancel():
        engine.end_session()
        return jsonify(engine.state())

    @app.get("/api/history")
    def history():
        profile = request.args.get("profile") or None
        return jsonify(
            sessions=storage.recent(15, profile),
            daily=storage.daily_totals(7, profile),
            profiles=storage.profiles(),
        )

    @app.delete("/api/history/<int:session_id>")
    def delete_session(session_id: int):
        return jsonify(deleted=storage.delete(session_id))

    return app


def main():
    ap = argparse.ArgumentParser(description="PhysioVision AI exercise monitor")
    ap.add_argument("--source", default="0",
                    help="webcam index (0, 1, ...) or path to a video file")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--model", choices=["lite", "full", "heavy"], default="full",
                    help="pose model size: lite is fastest, heavy is most accurate")
    ap.add_argument("--no-mirror", action="store_true", help="don't mirror the webcam image")
    args = ap.parse_args()

    from pose_engine import PoseEngine  # imported here so tests can skip MediaPipe

    source = int(args.source) if args.source.isdigit() else args.source
    engine = PoseEngine(source=source, mirror=False if args.no_mirror else None,
                        model=args.model)
    engine.start()
    app = create_app(engine)
    print(f"\n  PhysioVision AI running at http://{args.host}:{args.port}\n")
    try:
        app.run(host=args.host, port=args.port, threaded=True, debug=False)
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
