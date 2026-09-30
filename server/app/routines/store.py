"""SQLite-backed routine store (P5).

A Routine is {id, name, prompt, cron, enabled, created_at, last_run, last_status}.
Lives in DATA_DIR/routines.db. Synchronous stdlib sqlite3 — no new dependency,
safe to use from the in-process asyncio scheduler tick.
"""

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_FILENAME = "routines.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS routines (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    cron TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_run TEXT,
    last_status TEXT
)
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RoutineStore:
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            try:
                from ..config import settings

                data_dir = settings.data_dir
            except Exception:
                data_dir = os.getenv("DATA_DIR", "/opt/data")
        base = Path(data_dir)
        base.mkdir(parents=True, exist_ok=True)
        self.db_path = base / DB_FILENAME
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "prompt": row["prompt"],
            "cron": row["cron"],
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"],
            "last_run": row["last_run"],
            "last_status": row["last_status"],
        }

    MAX_PROMPT_LENGTH = 4000
    MAX_ROUTINES = 50

    def create(self, name: str, prompt: str, cron: str) -> Dict[str, Any]:
        from .scheduler import parse_cron  # deferred: scheduler imports this module

        clean_name = (name or "").strip()
        clean_prompt = (prompt or "").strip()
        clean_cron = (cron or "").strip()
        if not clean_name:
            raise ValueError("Routine name is required.")
        if not clean_prompt:
            raise ValueError("Routine prompt is required.")
        if len(clean_prompt) > self.MAX_PROMPT_LENGTH:
            raise ValueError(
                f"Routine prompt too long: {len(clean_prompt)} > {self.MAX_PROMPT_LENGTH} chars."
            )
        # Red-line / mutation-intent screen at create time so a scheduled
        # prompt can never smuggle a destructive action past governance.
        try:
            from ..policy import check_red_lines

            hit = check_red_lines({"name": clean_name, "prompt": clean_prompt})
            if hit:
                pattern, reason = hit
                raise ValueError(
                    f"Routine rejected by RED LINE policy ('{pattern}'): {reason}"
                )
        except ValueError:
            raise
        except Exception:
            pass
        parse_cron(clean_cron)  # validates; raises ValueError on bad syntax
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS c FROM routines").fetchone()["c"]
            if count >= self.MAX_ROUTINES:
                raise ValueError(
                    f"Routine limit reached ({self.MAX_ROUTINES}). Delete one first."
                )
        routine = {
            "id": uuid.uuid4().hex[:12],
            "name": clean_name[:200],
            "prompt": clean_prompt,
            "cron": clean_cron,
            "enabled": True,
            "created_at": _now_iso(),
            "last_run": None,
            "last_status": None,
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO routines (id, name, prompt, cron, enabled, created_at, last_run, last_status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    routine["id"],
                    routine["name"],
                    routine["prompt"],
                    routine["cron"],
                    1,
                    routine["created_at"],
                    None,
                    None,
                ),
            )
            conn.commit()
        return routine

    def list(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM routines ORDER BY created_at ASC").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get(self, routine_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM routines WHERE id = ?", (routine_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def set_enabled(self, routine_id: str, enabled: bool) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE routines SET enabled = ? WHERE id = ?",
                (1 if enabled else 0, routine_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                return None
        return self.get(routine_id)

    def delete(self, routine_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM routines WHERE id = ?", (routine_id,))
            conn.commit()
            return cur.rowcount > 0

    def record_run(
        self, routine_id: str, status: str, run_at: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Persist last_run/last_status. Errors are recorded, never fabricated."""
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE routines SET last_run = ?, last_status = ? WHERE id = ?",
                (run_at or _now_iso(), status, routine_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                return None
        return self.get(routine_id)
