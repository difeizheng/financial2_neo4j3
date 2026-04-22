"""Scenario CRUD for change simulation."""
import datetime
import json
import sqlite3
from typing import Any, Optional

from config import DB_PATH
from task_manager.sqlite_manager import _conn


def save_scenario(name: str, workbook_id: str, changes: dict[str, Any],
                  description: str = "") -> int:
    now = datetime.datetime.now().isoformat()
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO scenarios (name, workbook_id, changes_json, description, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (name, workbook_id, json.dumps(changes, ensure_ascii=False), description, now),
        )
        return cur.lastrowid


def list_scenarios(workbook_id: Optional[str] = None) -> list[dict]:
    with _conn() as conn:
        if workbook_id:
            rows = conn.execute(
                "SELECT * FROM scenarios WHERE workbook_id = ? ORDER BY created_at DESC",
                (workbook_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM scenarios ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def get_scenario(scenario_id: int) -> Optional[dict]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM scenarios WHERE id = ?", (scenario_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["changes"] = json.loads(d["changes_json"])
        return d


def delete_scenario(scenario_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM scenarios WHERE id = ?", (scenario_id,))
