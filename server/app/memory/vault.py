import os
import re
import aiosqlite
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

from ..config import settings

class KnowledgeVault:
    def __init__(self):
        self.vault_path = Path(settings.vault_dir)
        self.vault_path.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(settings.data_dir) / "vault_index.db"
        self._initialized = False

    async def init_db(self):
        if self._initialized:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT UNIQUE,
                    category TEXT,
                    content TEXT,
                    updated_at TEXT
                )
            """)
            await db.commit()
        self._initialized = True

    @staticmethod
    def _safe_title(title: str) -> str:
        # Keep alphanumerics, dash, underscore, and dots (e.g. "v1.2 notes");
        # collapse whitespace to dashes; strip leading/trailing separators.
        t = re.sub(r"\s+", "-", title.strip().lower())
        t = re.sub(r"[^a-z0-9._-]", "", t)
        return t.strip("-._") or "untitled"

    async def save_note(self, title: str, category: str, content: str) -> Dict[str, Any]:
        await self.init_db()
        now = datetime.now(timezone.utc).isoformat()

        # 1. Save as physical Markdown file in vault
        cat_dir = self.vault_path / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        safe_title = self._safe_title(title)
        file_path = cat_dir / f"{safe_title}.md"

        frontmatter = f"---\ntitle: \"{title}\"\ncategory: \"{category}\"\nupdated_at: \"{now}\"\n---\n\n"
        tmp_path = file_path.with_suffix(".md.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(frontmatter + content)
        os.replace(tmp_path, file_path)  # atomic on POSIX & Windows

        # 2. Update SQLite index
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO notes (title, category, content, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(title) DO UPDATE SET
                    category=excluded.category,
                    content=excluded.content,
                    updated_at=excluded.updated_at
            """, (title, category, content, now))
            await db.commit()

        return {"title": title, "category": category, "path": str(file_path), "status": "persisted"}

    async def query_notes(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        await self.init_db()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT title, category, content, updated_at FROM notes
                WHERE content LIKE ? OR title LIKE ?
                ORDER BY updated_at DESC LIMIT ?
            """, (f"%{query}%", f"%{query}%", int(limit)))
            rows = await cursor.fetchall()
            return [
                {"title": r[0], "category": r[1], "snippet": r[2][:300], "updated_at": r[3]}
                for r in rows
            ]

knowledge_vault = KnowledgeVault()
