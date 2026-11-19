"""SQLite ledger: every call event is stored before it is processed, and every write to GHL is
recorded per step, so a retry resumes where the last pass stopped instead of starting over.

Step statuses:
  done        the write landed; the stored result is reused on every later pass
  failed      the write definitely did not land (or is safe to repeat); retry it
  sending     an at-most-once write was attempted and its outcome is unknown; never repeat
              it automatically, a person checks
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS call_events (
    call_id     TEXT PRIMARY KEY,
    received_at TEXT NOT NULL,
    payload     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',   -- pending | done | failed | dead | needs_check
    attempts    INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS steps (
    call_id    TEXT NOT NULL,
    step       TEXT NOT NULL,
    status     TEXT NOT NULL,
    result     TEXT,
    error      TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (call_id, step)
);
CREATE TABLE IF NOT EXISTS alerts (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    at      TEXT NOT NULL,
    level   TEXT NOT NULL,
    call_id TEXT,
    message TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)

    def _exec(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, args)

    # call events -----------------------------------------------------------------------------
    def record_event(self, call_id: str, payload: dict) -> bool:
        """Store an end-of-call report. Returns False if this call was already received
        (Vapi or a proxy can deliver twice); the first payload is kept."""
        cur = self._exec(
            "INSERT OR IGNORE INTO call_events (call_id, received_at, payload, updated_at) VALUES (?,?,?,?)",
            (call_id, _now(), json.dumps(payload), _now()),
        )
        return cur.rowcount == 1

    def get_event(self, call_id: str) -> dict | None:
        row = self._exec("SELECT * FROM call_events WHERE call_id=?", (call_id,)).fetchone()
        return dict(row) if row else None

    def start_attempt(self, call_id: str) -> int:
        self._exec("UPDATE call_events SET attempts=attempts+1, updated_at=? WHERE call_id=?", (_now(), call_id))
        return self.get_event(call_id)["attempts"]

    def finish_event(self, call_id: str, status: str, error: str | None = None) -> None:
        self._exec(
            "UPDATE call_events SET status=?, last_error=?, updated_at=? WHERE call_id=?",
            (status, error, _now(), call_id),
        )

    def events(self, *statuses: str) -> list[dict]:
        marks = ",".join("?" * len(statuses))
        rows = self._exec(f"SELECT * FROM call_events WHERE status IN ({marks}) ORDER BY received_at", statuses)
        return [dict(r) for r in rows.fetchall()]

    def known_call_ids(self) -> set[str]:
        return {r["call_id"] for r in self._exec("SELECT call_id FROM call_events").fetchall()}

    # steps -----------------------------------------------------------------------------------
    def get_step(self, call_id: str, step: str) -> dict | None:
        row = self._exec("SELECT * FROM steps WHERE call_id=? AND step=?", (call_id, step)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["result"] = json.loads(out["result"]) if out["result"] else None
        return out

    def set_step(self, call_id: str, step: str, status: str, result=None, error: str | None = None) -> None:
        self._exec(
            "INSERT INTO steps (call_id, step, status, result, error, updated_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(call_id, step) DO UPDATE SET status=excluded.status, result=excluded.result, "
            "error=excluded.error, updated_at=excluded.updated_at",
            (call_id, step, status, json.dumps(result) if result is not None else None, error, _now()),
        )

    def has_done_step(self, call_id: str, prefix: str) -> bool:
        row = self._exec("SELECT 1 FROM steps WHERE call_id=? AND step LIKE ? AND status='done'",
                         (call_id, prefix + "%")).fetchone()
        return row is not None

    def steps_with_status(self, status: str) -> list[dict]:
        rows = self._exec("SELECT call_id, step, error, updated_at FROM steps WHERE status=?", (status,))
        return [dict(r) for r in rows.fetchall()]

    # alerts ----------------------------------------------------------------------------------
    def add_alert(self, level: str, message: str, call_id: str | None = None) -> None:
        self._exec("INSERT INTO alerts (at, level, call_id, message) VALUES (?,?,?,?)", (_now(), level, call_id, message))

    def alerts(self) -> list[dict]:
        return [dict(r) for r in self._exec("SELECT * FROM alerts ORDER BY id").fetchall()]
