from __future__ import annotations

from pathlib import Path

from text2sql_evolver.config import Settings
from text2sql_evolver.dataset import Example
from text2sql_evolver.inner_runner import generate_sql
from text2sql_evolver.runners.base import SQLRunner


class LLMRunner(SQLRunner):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate(self, example: Example, database_path: Path) -> str:
        return generate_sql(
            self.settings,
            example.question,
            self.settings.query_skill_path,
            database_path=database_path,
            evidence=example.evidence,
        )
