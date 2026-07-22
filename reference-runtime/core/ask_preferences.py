"""
ask_preferences.py — User preference and conversation history storage for Ask sessions.

Stores preferences and conversation history in a local SQLite database
at ~/.intent-os/ask_preferences.db.  Both stores are thread-safe.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_DB_DIR = Path.home() / ".intent-os"
_DB_PATH = _DB_DIR / "ask_preferences.db"


def _get_connection() -> sqlite3.Connection:
    """Return a connection to the local preference database.

    The database file and its parent directory are created on demand.
    Connections use ``check_same_thread=False`` so they can be handed
    across threads; callers **must** acquire the relevant lock before
    executing anything.
    """
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# PreferencesStore
# ---------------------------------------------------------------------------

class PreferencesStore:
    """Simple key-value preference store backed by SQLite.

    Thread-safe: every public method acquires ``_lock`` before touching
    the database.
    """

    def __init__(self, db_path: Optional[os.PathLike] = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else _DB_PATH
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None

    # -- initialisation ----------------------------------------------------

    def _ensure_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._create_tables()
        return self._conn

    def _create_tables(self) -> None:
        assert self._conn is not None
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS preferences (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    # -- public API --------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for *key*, or *default* when the key is absent."""
        with self._lock:
            conn = self._ensure_connection()
            row = conn.execute(
                "SELECT value FROM preferences WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return default
            # Attempt to deserialize JSON; fall back to raw text.
            try:
                return json.loads(row["value"])
            except (json.JSONDecodeError, TypeError):
                return row["value"]

    def set(self, key: str, value: Any) -> None:
        """Upsert *value* for *key*.

        Values are serialised as JSON so that lists, dicts, numbers, etc.
        survive a round-trip.
        """
        serialised = json.dumps(value, ensure_ascii=False, default=str)
        with self._lock:
            conn = self._ensure_connection()
            conn.execute(
                "INSERT OR REPLACE INTO preferences (key, value) VALUES (?, ?)",
                (key, serialised),
            )
            conn.commit()

    def get_all(self) -> dict[str, Any]:
        """Return every preference as a ``{key: deserialised_value}`` dict."""
        with self._lock:
            conn = self._ensure_connection()
            rows = conn.execute("SELECT key, value FROM preferences").fetchall()
        result: dict[str, Any] = {}
        for row in rows:
            try:
                result[row["key"]] = json.loads(row["value"])
            except (json.JSONDecodeError, TypeError):
                result[row["key"]] = row["value"]
        return result

    def _close(self) -> None:
        """Close the underlying connection (testing / cleanup only)."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None


# ---------------------------------------------------------------------------
# ConversationHistoryStore
# ---------------------------------------------------------------------------

class ConversationHistoryStore:
    """Persist and retrieve Ask conversation entries.

    Each entry records a single turn (user or assistant) within a session.
    Thread-safe.
    """

    def __init__(self, db_path: Optional[os.PathLike] = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else _DB_PATH
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None

    # -- initialisation ----------------------------------------------------

    def _ensure_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._create_tables()
        return self._conn

    def _create_tables(self) -> None:
        assert self._conn is not None
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT    NOT NULL,
                role        TEXT    NOT NULL,
                content     TEXT,
                metadata    TEXT,
                created_at  TEXT    NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ch_session_id "
            "ON conversation_history (session_id)"
        )
        self._conn.commit()

    # -- public API --------------------------------------------------------

    def add_entry(
        self,
        session_id: str,
        role: str,
        content: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        """Append a conversation entry and return its row id.

        Parameters
        ----------
        session_id:
            Opaque identifier scoping the conversation (e.g. a UUID).
        role:
            ``"user"`` or ``"assistant"`` (or any other label the caller
            wishes to use).
        content:
            The text payload of the turn.
        metadata:
            Optional structured data attached to this turn (JSON-serialised
            automatically).
        """
        now = datetime.now(timezone.utc).isoformat()
        metadata_json = json.dumps(metadata, ensure_ascii=False, default=str) if metadata else None
        with self._lock:
            conn = self._ensure_connection()
            cursor = conn.execute(
                """
                INSERT INTO conversation_history
                    (session_id, role, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, metadata_json, now),
            )
            conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    def get_history(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """Return conversation entries for *session_id*, oldest first.

        Parameters
        ----------
        session_id:
            The session to fetch.
        limit:
            Maximum number of entries to return (``None`` = unlimited).
        """
        with self._lock:
            conn = self._ensure_connection()
            query = (
                "SELECT id, session_id, role, content, metadata, created_at "
                "FROM conversation_history "
                "WHERE session_id = ? "
                "ORDER BY id ASC"
            )
            params: tuple[Any, ...] = (session_id,)
            if limit is not None:
                query += " LIMIT ?"
                params = (session_id, limit)
            rows = conn.execute(query, params).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            entry = dict(row)
            if entry["metadata"] is not None:
                try:
                    entry["metadata"] = json.loads(entry["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass  # leave as-is
            result.append(entry)
        return result

    def clear_session(self, session_id: str) -> int:
        """Delete **all** entries for *session_id*.

        Returns the number of rows deleted.
        """
        with self._lock:
            conn = self._ensure_connection()
            cursor = conn.execute(
                "DELETE FROM conversation_history WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            return cursor.rowcount

    def _close(self) -> None:
        """Close the underlying connection (testing / cleanup only)."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
