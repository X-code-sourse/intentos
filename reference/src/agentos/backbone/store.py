"""SQLite-backed Event Store — RFC-0500 §6.

Append-only log with replay, snapshot, and compaction support.
"""

import json
import sqlite3
import threading
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .event import Event


class EventStore:
    """Append-only Event Store backed by SQLite."""

    def __init__(self, db_path: str | Path):
        self._path = Path(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript(f"""
            CREATE TABLE IF NOT EXISTS events (
                event_id        TEXT PRIMARY KEY,
                event_type      TEXT NOT NULL,
                version         INTEGER NOT NULL DEFAULT 1,
                source_module   TEXT NOT NULL,
                execution_id    TEXT,
                session_id      TEXT,
                payload         TEXT NOT NULL,
                metadata        TEXT NOT NULL,
                context         TEXT NOT NULL DEFAULT '{{}}',
                published_at    TEXT NOT NULL,
                ingested_at     TEXT NOT NULL DEFAULT (strftime('%%Y-%%m-%%dT%%H:%%M:%%fZ', 'now'))
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id     TEXT PRIMARY KEY,
                execution_id    TEXT NOT NULL,
                at_sequence     INTEGER NOT NULL,
                state           TEXT NOT NULL,
                created_at      TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_execution
                ON events(execution_id, json_extract(metadata, '$.sequence_id'));
            CREATE INDEX IF NOT EXISTS idx_events_type_time
                ON events(event_type, published_at);
            CREATE INDEX IF NOT EXISTS idx_events_source
                ON events(source_module, published_at);
            CREATE INDEX IF NOT EXISTS idx_snapshots_execution
                ON snapshots(execution_id, at_sequence DESC);
        """)
        self._conn.commit()

    # ── write ───────────────────────────────────────────────────────

    def append(self, event: Event) -> str:
        with self._lock:
            self._conn.execute(
                """INSERT INTO events
                   (event_id, event_type, version, source_module,
                    execution_id, session_id, payload, metadata, context,
                    published_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    event.event_type,
                    event.version,
                    event.source.get("module", "unknown"),
                    event.context.get("execution_id"),
                    event.context.get("session_id"),
                    json.dumps(event.payload, default=str),
                    json.dumps(event.metadata, default=str),
                    json.dumps(event.context, default=str),
                    event.metadata.get("timestamp", datetime.now(timezone.utc).isoformat()),
                ),
            )
            self._conn.commit()
        return event.event_id

    # ── replay ──────────────────────────────────────────────────────

    def replay(self, *, execution_id: str | None = None,
               event_type: str | None = None,
               from_sequence: int | None = None,
               limit: int = 0) -> Generator[dict[str, Any], None, None]:
        """Yield stored events as dicts matching the filter criteria."""
        clauses: list[str] = []
        params: list[Any] = []

        if execution_id:
            clauses.append("execution_id = ?")
            params.append(execution_id)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if from_sequence is not None:
            clauses.append("CAST(json_extract(metadata, '$.sequence_id') AS INTEGER) >= ?")
            params.append(from_sequence)

        where = " AND ".join(clauses) if clauses else "1"
        sql = f"SELECT * FROM events WHERE {where} ORDER BY rowid"
        if limit:
            sql += f" LIMIT {limit}"

        with self._lock:
            # fmt:off
            rows = self._conn.execute(sql, params).fetchall()
            # fmt:on

        for row in rows:
            yield {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "version": row["version"],
                "source": {"module": row["source_module"]},
                "payload": json.loads(row["payload"]),
                "metadata": json.loads(row["metadata"]),
                "context": json.loads(row["context"]),
                "published_at": row["published_at"],
            }

    # ── snapshot / compaction (RFC-0500 §6.3) ───────────────────────

    def save_snapshot(self, execution_id: str, at_sequence: int,
                      state: dict[str, Any]) -> str:
        snap_id = f"snapshot://ref/{execution_id}/{at_sequence}"
        self._conn.execute(
            """INSERT OR REPLACE INTO snapshots
               (snapshot_id, execution_id, at_sequence, state, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (snap_id, execution_id, at_sequence,
             json.dumps(state, default=str),
             datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
        return snap_id

    def load_snapshot(self, execution_id: str) -> dict[str, Any] | None:
        try:
            row = self._conn.execute(
                """SELECT state, at_sequence FROM snapshots
                   WHERE execution_id = ? ORDER BY at_sequence DESC LIMIT 1""",
                (execution_id,),
            ).fetchone()
            if row:
                return {"state": json.loads(row["state"]), "at_sequence": row["at_sequence"]}
        except sqlite3.OperationalError:
            pass  # table might not exist yet
        return None

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()
        return row["c"] if row else 0

    def close(self):
        self._conn.close()
