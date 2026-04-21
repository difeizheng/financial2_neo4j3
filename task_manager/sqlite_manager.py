"""SQLite-backed task manager for Excel upload/parse jobs."""
import sqlite3
import datetime
import os
from typing import Optional

from config import DB_PATH


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                filename    TEXT    NOT NULL,
                filepath    TEXT    NOT NULL,
                status      TEXT    NOT NULL DEFAULT 'pending',
                sheets      TEXT,
                workbook_id TEXT,
                cell_count  INTEGER,
                dep_count   INTEGER,
                error_msg   TEXT,
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            )
        """)


def create_task(filename: str, filepath: str,
                sheets: Optional[list[str]] = None) -> int:
    now = datetime.datetime.now().isoformat()
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO tasks (filename, filepath, status, sheets, created_at, updated_at)
               VALUES (?, ?, 'pending', ?, ?, ?)""",
            (filename, filepath, ",".join(sheets) if sheets else None, now, now),
        )
        return cur.lastrowid


def update_task(task_id: int, **kwargs) -> None:
    kwargs["updated_at"] = datetime.datetime.now().isoformat()
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [task_id]
    with _conn() as conn:
        conn.execute(f"UPDATE tasks SET {cols} WHERE id = ?", vals)


def get_task(task_id: int) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def list_tasks() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def delete_task(task_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
