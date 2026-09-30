import hashlib
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

    @staticmethod
    def _safe_category(category: str) -> str:
        """Sanitize category path: each segment must match [a-z0-9-_]+, else 'general'."""
        parts = re.split(r"[/\\]+", (category or "").strip().lower())
        safe: List[str] = []
        for p in parts:
            p = re.sub(r"[^a-z0-9-_]", "", p.strip())
            if p and p not in (".", ".."):
                safe.append(p)
        return "/".join(safe) or "general"

    @staticmethod
    def _yaml_escape(value: str) -> str:
        """Escape a scalar for double-quoted YAML frontmatter."""
        return (value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

    @staticmethod
    def safe_slug(text: str) -> str:
        """Collision-resistant slug: sha256 hexdigest, 12 chars."""
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _escape_like(query: str) -> str:
        """Escape LIKE wildcards so % _ \\ are matched literally."""
        return (
            (query or "")
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )

    async def save_note(self, title: str, category: str, content: str) -> Dict[str, Any]:
        await self.init_db()
        now = datetime.now(timezone.utc).isoformat()

        # 1. Save as physical Markdown file in vault
        safe_category = self._safe_category(category)
        cat_dir = self.vault_path / safe_category
        # Contain within vault dir (defense in depth against traversal).
        try:
            cat_dir.resolve().relative_to(self.vault_path.resolve())
        except ValueError:
            safe_category = "general"
            cat_dir = self.vault_path / safe_category
        cat_dir.mkdir(parents=True, exist_ok=True)
        safe_title = self._safe_title(title)
        file_path = cat_dir / f"{safe_title}.md"
        if file_path.exists():
            # Dedupe on collision (e.g. hash()%10000 slugs from callers):
            # append a short sha256 suffix instead of overwriting.
            suffix = hashlib.sha256(
                f"{title}:{now}".encode("utf-8")
            ).hexdigest()[:12]
            file_path = cat_dir / f"{safe_title}-{suffix}.md"

        frontmatter = (
            f"---\ntitle: \"{self._yaml_escape(title)}\"\n"
            f"category: \"{self._yaml_escape(safe_category)}\"\n"
            f"updated_at: \"{now}\"\n---\n\n"
        )
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
            """, (title, safe_category, content, now))
            await db.commit()

        return {"title": title, "category": safe_category, "path": str(file_path), "status": "persisted"}

    async def query_notes(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        await self.init_db()
        q = self._escape_like((query or "")[:500])
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT title, category, content, updated_at FROM notes
                WHERE content LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\'
                ORDER BY updated_at DESC LIMIT ?
            """, (f"%{q}%", f"%{q}%", int(limit)))
            rows = await cursor.fetchall()
            return [
                {"title": r[0], "category": r[1], "snippet": r[2][:300], "updated_at": r[3]}
                for r in rows
            ]

knowledge_vault = KnowledgeVault()
