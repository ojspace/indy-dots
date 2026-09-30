"""Conversation persistence: per-session chat history in SQLite.

Table: conversations(id, session_id, role, content, created_at)
DB file: <DATA_DIR>/conversations.db (DATA_DIR from settings, resolved live
so tests can monkeypatch settings.data_dir to an isolated tmp dir).
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

import aiosqlite

from ..config import settings


def _db_path() -> Path:
    p = Path(settings.data_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p / "conversations.db"


async def init_db() -> None:
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_session "
            "ON conversations(session_id, id)"
        )
        await db.commit()


async def save_message(session_id: str, role: str, content: str) -> Dict[str, Any]:
    await init_db()
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            "INSERT INTO conversations (session_id, role, content, created_at)"
            " VALUES (?, ?, ?, ?)",
            (session_id, role, content, now),
        )
        await db.commit()
        return {
            "id": cursor.lastrowid,
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": now,
        }


async def list_history(session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    await init_db()
    limit = max(1, min(int(limit), 1000))
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            "SELECT id, session_id, role, content, created_at FROM conversations"
            " WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "session_id": r[1],
                "role": r[2],
                "content": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]


async def clear_history(session_id: str) -> int:
    await init_db()
    async with aiosqlite.connect(_db_path()) as db:
        cursor = await db.execute(
            "DELETE FROM conversations WHERE session_id = ?", (session_id,)
        )
        await db.commit()
        return cursor.rowcount or 0
