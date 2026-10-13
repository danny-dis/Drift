"""Lossless raw captures, retained independently of downstream processing."""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Iterator
from uuid import uuid4


MAX_TEXT_LENGTH = 1_000_000
MAX_PAGE_SIZE = 1000
STATUSES = ("captured", "queued", "processed", "needs_review")
_FIELDS = "id, text, created_at, status, idea_id, task_id, report_path"


class IdempotencyConflict(ValueError):
    """An existing client intent was retried with different raw text."""


def _identifier(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


def _limit(value: Any) -> None:
    if type(value) is not int or not 1 <= value <= MAX_PAGE_SIZE:
        raise ValueError(f"limit must be an integer between 1 and {MAX_PAGE_SIZE}")


class CaptureStore:
    """One connection per operation; SQLite serializes independent writers.

    Raw text and client intent keys never expire. WAL and FULL synchronous
    commits make successful writes durable; read transactions keep pagination
    counts and rows in the same snapshot. No capture is deleted or content-deduped.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "captures.sqlite3"
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            from drift.capture_init import enable_wal
            enable_wal(db)
            db.execute("PRAGMA synchronous=FULL")
            db.execute("""
                CREATE TABLE IF NOT EXISTS captures (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    client_id TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'captured'
                        CHECK (status IN ('captured', 'queued', 'processed', 'needs_review')),
                    idea_id TEXT,
                    task_id TEXT,
                    report_path TEXT,
                    summary TEXT NOT NULL DEFAULT ''
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS captures_order ON captures(created_at DESC, id DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS captures_status ON captures(status, created_at DESC, id DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS captures_task ON captures(task_id)")
            db.execute("""CREATE INDEX IF NOT EXISTS captures_pending
                ON captures(created_at, id) WHERE task_id IS NULL AND status = 'captured'""")
            db.commit()

    @contextmanager
    def _db(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=30, isolation_level=None)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def capture(self, text: str, client_id: str | None = None) -> dict:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a nonempty string")
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError(f"text exceeds {MAX_TEXT_LENGTH} characters; it was not saved")
        if client_id is not None:
            _identifier(client_id, "client_id")
        with self._db(write=True) as db:
            if client_id is not None:
                row = db.execute(
                    f"SELECT {_FIELDS} FROM captures WHERE client_id = ?", (client_id,)
                ).fetchone()
                if row is not None:
                    if row["text"] != text:
                        raise IdempotencyConflict("client_id already used with different text")
                    return {"capture": dict(row), "deduplicated": True}
            capture_id = uuid4().hex
            created_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            db.execute(
                "INSERT INTO captures(id, text, client_id, created_at) VALUES (?, ?, ?, ?)",
                (capture_id, text, client_id, created_at),
            )
            row = db.execute(
                f"SELECT {_FIELDS} FROM captures WHERE id = ?", (capture_id,)
            ).fetchone()
            return {"capture": dict(row), "deduplicated": False}

    def list(self, query: str = "", status: str | None = None,
             limit: int = 50, offset: int = 0) -> dict:
        _limit(limit)
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be a nonnegative integer")
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        if status is not None and status not in STATUSES:
            raise ValueError("unknown capture status")
        clauses, params = [], []
        if query:
            # instr treats %, _, backslashes and NUL as literal substring data.
            clauses.append("instr(text, ?) > 0")
            params.append(query)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._db() as db:
            total = db.execute("SELECT COUNT(*) FROM captures" + where, params).fetchone()[0]
            rows = db.execute(
                f"SELECT {_FIELDS} FROM captures{where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return {"captures": [dict(row) for row in rows], "total": total,
                "has_more": offset + len(rows) < total}

    def get(self, capture_id: str) -> dict | None:
        _identifier(capture_id, "capture_id")
        with self._db() as db:
            row = db.execute(
                f"SELECT {_FIELDS} FROM captures WHERE id = ?", (capture_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def pending(self, limit: int = 20) -> list[dict]:
        _limit(limit)
        with self._db() as db:
            rows = db.execute(
                f"SELECT {_FIELDS} FROM captures WHERE task_id IS NULL AND status = 'captured' "
                "ORDER BY created_at, id LIMIT ?", (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def link(self, capture_id: str, idea_id: str, task_id: str) -> dict:
        for name, value in (("capture_id", capture_id), ("idea_id", idea_id), ("task_id", task_id)):
            _identifier(value, name)
        with self._db(write=True) as db:
            row = db.execute(
                f"SELECT {_FIELDS} FROM captures WHERE id = ?", (capture_id,)
            ).fetchone()
            if row is None:
                raise KeyError(capture_id)
            if row["task_id"] is not None:
                if row["idea_id"] != idea_id or row["task_id"] != task_id:
                    raise ValueError("capture is already linked to another idea or task")
                return dict(row)
            db.execute(
                "UPDATE captures SET idea_id = ?, task_id = ?, status = 'queued' WHERE id = ?",
                (idea_id, task_id, capture_id),
            )
            return dict(db.execute(
                f"SELECT {_FIELDS} FROM captures WHERE id = ?", (capture_id,)
            ).fetchone())

    def finish(self, task_id: str, status: str, report_path: str = "", summary: str = "") -> int:
        """Record processing metadata for all linked captures; never change raw text."""
        _identifier(task_id, "task_id")
        if status not in ("processed", "needs_review"):
            raise ValueError("finish status must be processed or needs_review")
        if not isinstance(report_path, str) or not isinstance(summary, str):
            raise ValueError("report_path and summary must be strings")
        with self._db(write=True) as db:
            cursor = db.execute(
                "UPDATE captures SET status = ?, report_path = ?, summary = ? WHERE task_id = ?",
                (status, report_path, summary, task_id),
            )
            return cursor.rowcount
