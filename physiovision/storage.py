"""SQLite storage for completed exercise sessions."""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
import threading

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "physiovision.db")
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _lock, _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                profile       TEXT NOT NULL,
                exercise      TEXT NOT NULL,
                exercise_name TEXT NOT NULL,
                side          TEXT,
                reps          INTEGER NOT NULL,
                target        INTEGER NOT NULL,
                partial_reps  INTEGER NOT NULL DEFAULT 0,
                duration_s    REAL NOT NULL,
                avg_rom       REAL,
                started_at    TEXT NOT NULL,
                ended_at      TEXT NOT NULL
            )""")


def save(s: dict) -> int:
    cols = ["profile", "exercise", "exercise_name", "side", "reps", "target",
            "partial_reps", "duration_s", "avg_rom", "started_at", "ended_at"]
    with _lock, _conn() as c:
        cur = c.execute(
            f"INSERT INTO sessions ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [s.get(k) for k in cols])
        return cur.lastrowid


def delete(session_id: int) -> bool:
    with _lock, _conn() as c:
        return c.execute("DELETE FROM sessions WHERE id = ?", (session_id,)).rowcount > 0


def recent(limit: int = 15, profile: str | None = None) -> list[dict]:
    q, args = "SELECT * FROM sessions", []
    if profile:
        q += " WHERE profile = ?"
        args.append(profile)
    q += " ORDER BY started_at DESC LIMIT ?"
    args.append(limit)
    with _lock, _conn() as c:
        return [dict(r) for r in c.execute(q, args)]


def profiles() -> list[str]:
    with _lock, _conn() as c:
        return [r[0] for r in c.execute(
            "SELECT profile FROM sessions GROUP BY profile ORDER BY MAX(started_at) DESC")]


def daily_totals(days: int = 7, profile: str | None = None) -> list[dict]:
    today = dt.date.today()
    first = today - dt.timedelta(days=days - 1)
    q = ("SELECT substr(started_at, 1, 10) AS day, SUM(reps) AS reps, COUNT(*) AS sessions "
         "FROM sessions WHERE substr(started_at, 1, 10) >= ?")
    args: list = [first.isoformat()]
    if profile:
        q += " AND profile = ?"
        args.append(profile)
    q += " GROUP BY day"
    with _lock, _conn() as c:
        found = {r["day"]: dict(r) for r in c.execute(q, args)}
    out = []
    for i in range(days):
        d = (first + dt.timedelta(days=i)).isoformat()
        row = found.get(d, {"reps": 0, "sessions": 0})
        out.append({"day": d, "reps": row["reps"] or 0, "sessions": row["sessions"]})
    return out
