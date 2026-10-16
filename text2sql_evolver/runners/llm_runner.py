from __future__ import annotations

from pathlib import Path
import json

from text2sql_evolver.config import Settings
from text2sql_evolver.dataset import Example
from text2sql_evolver.inner_runner import generate_sql
from text2sql_evolver.runners.base import SQLRunner
from text2sql_evolver.memory.memrl import database_scope, source_keys


class LLMRunner(SQLRunner):
    def __init__(self, settings: Settings, memory=None) -> None:
        self.settings = settings
        self.memory = memory
        self.details = {"attempts": [], "retrieved_memories": []}

    def execution_details(self):
        return self.details

    def generate(self, example: Example, database_path: Path) -> str:
        self.details = {"attempts": [], "retrieved_memories": []}
        if self.memory and self.settings.memory_inference:
            scope = database_scope(database_path)
            self.details["retrieved_memories"] = self.memory.retrieve(
                example.question, scope=scope, consumer="inference",
                skill_text=self.settings.query_skill_path.read_text(encoding="utf-8"),
                exclude_keys=source_keys(example.question, scope, example.id, example.source_id))
        return generate_sql(
            self.settings,
            example.question,
            self.settings.query_skill_path,
            database_path=database_path,
            evidence=example.evidence,
            attempts=self.details["attempts"],
            memory_context=json.dumps(self.details["retrieved_memories"], ensure_ascii=False)
            if self.details["retrieved_memories"] else "",
        )
