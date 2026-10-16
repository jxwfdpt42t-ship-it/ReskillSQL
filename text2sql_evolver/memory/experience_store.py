"""SQLite persistence and the small MemOS text_mem interface used by MemRL."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace


class ExperienceStore:
    def __init__(self, path: Path, *, readonly: bool = False):
        self.path = Path(path).resolve()
        self.readonly = readonly
        if readonly:
            if not self.path.is_file():
                raise FileNotFoundError(f"Memory store does not exist: {self.path}")
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS experiences (
                id TEXT PRIMARY KEY, intent TEXT NOT NULL, content TEXT NOT NULL,
                embedding TEXT NOT NULL, metadata TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS feedback (
                event_id TEXT PRIMARY KEY, payload TEXT NOT NULL)""")

    @contextmanager
    def connect(self):
        suffix = "?mode=ro" if self.readonly else "?mode=rwc"
        db = sqlite3.connect(self.path.as_uri() + suffix, uri=True, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, memory_id, intent, content, embedding, metadata):
        if self.readonly:
            raise PermissionError("Memory store is read-only")
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO experiences VALUES (?, ?, ?, ?, ?)", (
                memory_id, intent, content, json.dumps(embedding), json.dumps(metadata, ensure_ascii=False)))

    def rows(self):
        with self.connect() as db:
            return [self.decode(row) for row in db.execute("SELECT * FROM experiences ORDER BY id")]

    @staticmethod
    def decode(row):
        return {**dict(row), "embedding": json.loads(row["embedding"]),
                "metadata": json.loads(row["metadata"])}

    def has(self, memory_id):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM experiences WHERE id=?", (memory_id,)).fetchone() is not None

    @contextmanager
    def feedback_event(self, event_id, context, payload):
        """Deduplicate retries and atomically update all credited memories."""
        if self.readonly:
            raise PermissionError("Memory store is read-only")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM feedback WHERE event_id=?", (event_id,)).fetchone():
                yield None
                return
            yield _TextMemory(db, context)
            db.execute("INSERT INTO feedback VALUES (?, ?)", (event_id, json.dumps(payload)))


class _TextMemory:
    """Duck-typed MemOS adapter; separate Q estimates by consumer/skill/model."""
    def __init__(self, db, context):
        self.db, self.context = db, context

    def get(self, memory_id):
        row = self.db.execute("SELECT * FROM experiences WHERE id=?", (memory_id,)).fetchone()
        if row is None:
            raise KeyError(memory_id)
        metadata = json.loads(row["metadata"])
        metadata.update(metadata.get("utilities", {}).get(self.context, {}))
        return SimpleNamespace(memory=row["intent"], metadata=metadata)

    def update(self, memory_id, data):
        row = self.db.execute("SELECT metadata FROM experiences WHERE id=?", (memory_id,)).fetchone()
        if row is None:
            raise KeyError(memory_id)
        metadata = json.loads(row["metadata"])
        keys = ("q_value", "q_visits", "last_reward", "reward_ma", "q_updated_at", "last_used_at")
        metadata.setdefault("utilities", {})[self.context] = {k: data["metadata"][k] for k in keys}
        self.db.execute("UPDATE experiences SET metadata=? WHERE id=?",
                        (json.dumps(metadata, ensure_ascii=False), memory_id))
