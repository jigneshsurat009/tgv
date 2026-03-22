from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS active_jobs (
                    user_id INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS preset_rules (
                    preset_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS batch_jobs (
                    job_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    batch_mode TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_value TEXT NOT NULL,
                    default_preset_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_error TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS batch_items (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    preset_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    step TEXT NOT NULL DEFAULT '',
                    error TEXT DEFAULT '',
                    output_path TEXT DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(job_id, item_id)
                );
                CREATE TABLE IF NOT EXISTS job_history (
                    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            con.commit()

    def upsert_active_job(self, user_id: int, payload: dict[str, Any]) -> None:
        blob = json.dumps(payload)
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO active_jobs(user_id, payload, updated_at) VALUES(?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload, updated_at=CURRENT_TIMESTAMP
                """,
                (user_id, blob),
            )
            con.commit()

    def get_active_job(self, user_id: int) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute("SELECT payload FROM active_jobs WHERE user_id=?", (user_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def clear_active_job(self, user_id: int) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM active_jobs WHERE user_id=?", (user_id,))
            con.commit()

    def save_preset(self, user_id: int, preset_id: str, name: str, payload: dict[str, Any]) -> None:
        blob = json.dumps(payload)
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO preset_rules(preset_id, user_id, name, payload, updated_at)
                VALUES(?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(preset_id) DO UPDATE SET name=excluded.name, payload=excluded.payload, updated_at=CURRENT_TIMESTAMP
                """,
                (preset_id, user_id, name, blob),
            )
            con.commit()

    def list_presets(self, user_id: int) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT preset_id, name, payload, created_at, updated_at FROM preset_rules WHERE user_id=? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in rows]

    def get_preset(self, preset_id: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute("SELECT preset_id, name, payload FROM preset_rules WHERE preset_id=?", (preset_id,)).fetchone()
        return ({**dict(row), "payload": json.loads(row["payload"])}) if row else None

    def create_batch_job(self, job_payload: dict[str, Any], item_rows: list[dict[str, Any]], last_error: str = "") -> None:
        with self._connect() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO batch_jobs(job_id, user_id, chat_id, status, batch_mode, source_type, source_value, default_preset_id, payload, updated_at, last_error)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                """,
                (
                    job_payload["job_id"], job_payload["user_id"], job_payload["chat_id"], job_payload["status"], job_payload["batch_mode"],
                    job_payload["source_type"], job_payload["source_value"], job_payload["default_preset_id"], json.dumps(job_payload), last_error,
                ),
            )
            for row in item_rows:
                con.execute(
                    """
                    INSERT OR REPLACE INTO batch_items(job_id, item_id, item_name, source_url, preset_id, status, step, error, output_path, attempts, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        row["job_id"], row["item_id"], row["item_name"], row["source_url"], row["preset_id"], row["status"], row["step"], row["error"], row["output_path"], row["attempts"],
                    ),
                )
            con.commit()

    def update_batch_item(self, job_id: str, item_id: str, *, status: str, step: str = "", error: str = "", output_path: str = "", attempts: int | None = None) -> None:
        sql = "UPDATE batch_items SET status=?, step=?, error=?, output_path=?, updated_at=CURRENT_TIMESTAMP"
        params: list[Any] = [status, step, error, output_path]
        if attempts is not None:
            sql += ", attempts=?"
            params.append(attempts)
        sql += " WHERE job_id=? AND item_id=?"
        params.extend([job_id, item_id])
        with self._connect() as con:
            con.execute(sql, params)
            con.commit()

    def update_batch_status(self, job_id: str, status: str, payload: dict[str, Any], last_error: str = "") -> None:
        with self._connect() as con:
            con.execute(
                "UPDATE batch_jobs SET status=?, payload=?, last_error=?, updated_at=CURRENT_TIMESTAMP WHERE job_id=?",
                (status, json.dumps(payload), last_error, job_id),
            )
            con.commit()

    def get_failed_or_paused_job(self, user_id: int) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM batch_jobs WHERE user_id=? AND status IN ('failed','paused') ORDER BY updated_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_batch_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM batch_jobs WHERE job_id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def get_batch_items(self, job_id: str) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM batch_items WHERE job_id=? ORDER BY row_id ASC", (job_id,)).fetchall()
        return [dict(r) for r in rows]

    def add_history(self, job_id: str, user_id: int, event_type: str, message: str) -> None:
        with self._connect() as con:
            con.execute("INSERT INTO job_history(job_id, user_id, event_type, message) VALUES(?, ?, ?, ?)", (job_id, user_id, event_type, message))
            con.commit()

    def list_history(self, user_id: int, limit: int = 15) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT job_id, event_type, message, created_at FROM job_history WHERE user_id=? ORDER BY history_id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
