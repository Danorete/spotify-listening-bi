"""SQLite storage. One connection, one lock, explicit transactions."""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- What the companion knows about the user. `kind` decides who may read it (see context.py).
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, audience TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL, provenance TEXT NOT NULL, is_sample INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY, title TEXT NOT NULL, claim TEXT NOT NULL,
    metrics TEXT NOT NULL DEFAULT '[]', source_ref TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'unverified_user_claim',
    permitted_uses TEXT NOT NULL DEFAULT '[]', do_not_claim TEXT NOT NULL DEFAULT '',
    confidential INTEGER NOT NULL DEFAULT 0, provenance TEXT NOT NULL,
    is_sample INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

-- Opportunities and relationships.
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, org TEXT NOT NULL DEFAULT '',
    private_notes TEXT NOT NULL DEFAULT '', shareable_context TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active', is_sample INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY, item_id INTEGER REFERENCES items(id) ON DELETE SET NULL,
    kind TEXT NOT NULL, title TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'suggested',
    commitment INTEGER NOT NULL DEFAULT 0, importance INTEGER NOT NULL DEFAULT 2,
    effort_min INTEGER NOT NULL DEFAULT 15, deadline TEXT, where_left_off TEXT NOT NULL DEFAULT '',
    is_sample INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    completed_at TEXT);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY, action_id INTEGER REFERENCES actions(id) ON DELETE CASCADE,
    purpose TEXT NOT NULL, audience TEXT NOT NULL DEFAULT '', body TEXT NOT NULL,
    claims TEXT NOT NULL DEFAULT '[]', gaps TEXT NOT NULL DEFAULT '[]',
    report TEXT NOT NULL DEFAULT '{}', source TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS outcomes (
    id INTEGER PRIMARY KEY, item_id INTEGER REFERENCES items(id) ON DELETE CASCADE,
    action_id INTEGER REFERENCES actions(id) ON DELETE SET NULL,
    type TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', occurred_on TEXT NOT NULL,
    created_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY, action_id INTEGER REFERENCES actions(id) ON DELETE CASCADE,
    text TEXT NOT NULL, due_on TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL);

-- Curiosity parking lot. An idea is never an obligation until the user promotes it.
CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY, text TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'parked',
    created_at TEXT NOT NULL);

-- Pasted, untrusted material.
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL, content TEXT NOT NULL,
    created_at TEXT NOT NULL);

-- Model suggestions waiting for a click.
CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
    rationale TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'pending',
    session_id INTEGER, created_at TEXT NOT NULL, decided_at TEXT);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, ended_at TEXT,
    minutes INTEGER NOT NULL DEFAULT 20, focus_action_id INTEGER);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY, session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL, content TEXT NOT NULL, has_import INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL);

-- Spend ledger. status: reserved, settled, unknown, released, adjustment.
CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, month TEXT NOT NULL, day TEXT NOT NULL,
    session_id INTEGER, call_type TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,
    reserved_usd REAL NOT NULL DEFAULT 0, cost_usd REAL NOT NULL DEFAULT 0,
    in_tok INTEGER NOT NULL DEFAULT 0, out_tok INTEGER NOT NULL DEFAULT 0,
    cw_tok INTEGER NOT NULL DEFAULT 0, cr_tok INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '');

-- Metadata only. Never private content.
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
"""

USER_TABLES = (
    "kv", "memory", "evidence", "items", "actions", "drafts", "outcomes", "reminders",
    "ideas", "imports", "proposals", "sessions", "messages", "ledger", "activity",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.lock = threading.RLock()
        self._open()

    def _open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        for pragma in ("journal_mode=WAL", "foreign_keys=ON", "secure_delete=ON"):
            self.conn.execute(f"PRAGMA {pragma}")
        self.conn.executescript(SCHEMA)
        self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def q(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
        rows = self.q(sql, params)
        return rows[0] if rows else None

    def run(self, sql: str, params: tuple | list = ()) -> int:
        with self.lock:
            cur = self.conn.execute(sql, params)
            return cur.lastrowid or cur.rowcount

    @contextmanager
    def tx(self) -> Iterator[None]:
        """Serialised write transaction. Used where check-then-write must be atomic."""
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self.conn.execute("ROLLBACK")
                raise
            self.conn.execute("COMMIT")

    def log(self, event: str, detail: str = "") -> None:
        """Activity log. Callers pass identifiers and counts, never user content."""
        self.run("INSERT INTO activity(ts,event,detail) VALUES(?,?,?)", (now(), event, detail[:200]))

    def wipe(self) -> None:
        """Delete the database files and start empty. See README for what this cannot reach."""
        with self.lock:
            self.conn.close()
            for suffix in ("", "-wal", "-shm"):
                p = Path(str(self.path) + suffix)
                if p.exists():
                    p.unlink()
            self._open()

    def close(self) -> None:
        with self.lock:
            self.conn.close()
