from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from text2sql_evolver.dataset import Example
from text2sql_evolver.judge import JudgeResult
from text2sql_evolver.sql_analyzer import FailureAnalysis


class FailureAnalyzer(ABC):
    @abstractmethod
    def analyze(
        self,
        example: Example,
        database_path: Path,
        predicted_sql: str,
        judge: JudgeResult,
    ) -> FailureAnalysis:
        """Return the best available failure diagnosis."""
