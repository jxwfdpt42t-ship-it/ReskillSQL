from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from text2sql_evolver.dataset import Example


class SQLRunner(ABC):
    @abstractmethod
    def generate(self, example: Example, database_path: Path) -> str:
        """Generate SQL for one benchmark example."""
