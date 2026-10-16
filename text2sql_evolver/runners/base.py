from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from text2sql_evolver.dataset import Example


class SQLRunner(ABC):
    def execution_details(self) -> dict:
        """Optional telemetry; cached/custom runners need not claim a repair trace."""
        return {"attempts": [], "retrieved_memories": []}

    @abstractmethod
    def generate(self, example: Example, database_path: Path) -> str:
        """Generate SQL for one benchmark example."""
