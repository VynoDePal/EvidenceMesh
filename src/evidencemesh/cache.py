"""Small persistent TTL cache with no external service dependency."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class SQLiteCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            str(path),
            timeout=10,
            check_same_thread=False,
        )
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    namespace TEXT NOT NULL,
                    cache_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    PRIMARY KEY (namespace, cache_key)
                )
                """
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_expiry ON cache_entries(expires_at)"
            )

    def get_json(self, namespace: str, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            row = self._connection.execute(
                """
                SELECT value_json, expires_at
                FROM cache_entries
                WHERE namespace = ? AND cache_key = ?
                """,
                (namespace, key),
            ).fetchone()
            if row is None:
                return None
            if row[1] <= now:
                with self._connection:
                    self._connection.execute(
                        "DELETE FROM cache_entries WHERE namespace = ? AND cache_key = ?",
                        (namespace, key),
                    )
                return None
            return json.loads(row[0])

    def set_json(self, namespace: str, key: str, value: Any, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        now = time.time()
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO cache_entries (
                    namespace, cache_key, value_json, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(namespace, cache_key) DO UPDATE SET
                    value_json = excluded.value_json,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
                """,
                (namespace, key, payload, now, now + ttl_seconds),
            )

    def prune(self) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM cache_entries WHERE expires_at <= ?",
                (time.time(),),
            )
            return cursor.rowcount

    def clear(self, namespace: str | None = None) -> int:
        with self._lock, self._connection:
            if namespace is None:
                cursor = self._connection.execute("DELETE FROM cache_entries")
            else:
                cursor = self._connection.execute(
                    "DELETE FROM cache_entries WHERE namespace = ?",
                    (namespace,),
                )
            return cursor.rowcount

    def close(self) -> None:
        with self._lock:
            self._connection.close()
