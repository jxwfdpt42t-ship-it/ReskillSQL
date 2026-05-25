from __future__ import annotations

from pathlib import Path

from text2sql_evolver.analyzers.base import FailureAnalyzer
from text2sql_evolver.dataset import Example
from text2sql_evolver.judge import JudgeResult
from text2sql_evolver.sql_analyzer import FailureAnalysis, analyze_failure


class SQLSpecializedAnalyzer(FailureAnalyzer):
    """Default SQL-aware analyzer.

    The current implementation wraps the heuristic analyzer and gives us a stable
    extension point for stronger detectors such as value grounding, result shape,
    ratio handling, and evidence usage.
    """

    def analyze(
        self,
        example: Example,
        database_path: Path,
        predicted_sql: str,
        judge: JudgeResult,
    ) -> FailureAnalysis:
        return analyze_failure(
            example.question,
            predicted_sql,
            example.gold_sql,
            judge.reason,
            predicted_rows=judge.predicted.rows,
            gold_rows=judge.gold.rows,
            evidence_hint=example.evidence,
        )
