from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from text2sql_evolver.dataset import Example
from text2sql_evolver.analyzers.base import FailureAnalyzer
from text2sql_evolver.evaluators.execution_judge import ExecutionJudge
from text2sql_evolver.evaluators.metrics import accuracy
from text2sql_evolver.runners.base import SQLRunner
from text2sql_evolver.utils.paths import resolve_database_path


@dataclass(frozen=True)
class ValidationResult:
    before_accuracy: float | None
    after_accuracy: float | None
    accepted: bool
    reason: str


class ValidationRunner:
    """Run a validation split and return execution accuracy."""

    def __init__(
        self,
        runner: SQLRunner,
        default_database: Path,
        judge: ExecutionJudge | None = None,
        analyzer: FailureAnalyzer | None = None,
    ) -> None:
        self.runner = runner
        self.default_database = default_database
        self.judge = judge or ExecutionJudge()
        self.analyzer = analyzer

    def score(self, examples: list[Example]) -> float:
        rows = self.evaluate(examples)
        return accuracy([_AccuracyOnly(correct=bool(row["correct"])) for row in rows])

    def evaluate(self, examples: list[Example]) -> list[dict[str, Any]]:
        runs = []
        for example in examples:
            database_path = resolve_database_path(example.db_path, self.default_database)
            predicted_sql = self.runner.generate(example, database_path)
            judged = self.judge.evaluate(database_path, predicted_sql, example.gold_sql)
            analysis = None
            if not judged.correct and self.analyzer is not None:
                analysis = self.analyzer.analyze(example, database_path, predicted_sql, judged)
            runs.append(
                {
                    "id": example.id,
                    "question": example.question,
                    "db_path": str(database_path),
                    "predicted_sql": predicted_sql,
                    "gold_sql": example.gold_sql,
                    "correct": judged.correct,
                    "reason": judged.reason,
                    "category": analysis.category if analysis else None,
                    "analysis_evidence": analysis.evidence if analysis else None,
                    "analysis_details": analysis.details if analysis else None,
                }
            )
        return runs

    def dry_result(self, accepted: bool, reason: str) -> ValidationResult:
        return ValidationResult(None, None, accepted, reason)


@dataclass(frozen=True)
class _AccuracyOnly:
    correct: bool
