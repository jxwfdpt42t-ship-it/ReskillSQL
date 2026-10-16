from __future__ import annotations

from pathlib import Path

from text2sql_evolver.dataset import Example
from text2sql_evolver.inner_runner import apply_sql_skill_checks
from text2sql_evolver.runners.base import SQLRunner


class CachedRunner(SQLRunner):
    def __init__(self, predictions: dict[str, str], fallback: SQLRunner | None = None) -> None:
        self.predictions = predictions
        self.fallback = fallback
        self.used_fallback = False

    def execution_details(self):
        if self.used_fallback and self.fallback:
            return self.fallback.execution_details()
        return super().execution_details()

    def generate(self, example: Example, database_path: Path) -> str:
        self.used_fallback = False
        if example.id in self.predictions:
            return self._apply_skill_compiled_checks(example, self.predictions[example.id], database_path)
        if self.fallback is None:
            raise KeyError(f"No cached prediction for example {example.id}")
        self.used_fallback = True
        return self.fallback.generate(example, database_path)

    def _apply_skill_compiled_checks(self, example: Example, sql: str, database_path: Path) -> str:
        settings = getattr(self.fallback, "settings", None)
        skill_path = getattr(settings, "query_skill_path", None)
        if not skill_path or not Path(skill_path).exists():
            return sql
        skill_text = Path(skill_path).read_text(encoding="utf-8")
        return apply_sql_skill_checks(sql, example.question, skill_text, database_path=database_path)
