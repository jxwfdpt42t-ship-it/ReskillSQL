from __future__ import annotations

from collections import Counter
from typing import Iterable

from text2sql_evolver.core.state import ExampleRun


def accuracy(runs: Iterable[ExampleRun]) -> float:
    rows = list(runs)
    return sum(run.correct for run in rows) / len(rows) if rows else 0.0


def failure_counts(runs: Iterable[ExampleRun]) -> dict[str, int]:
    return dict(Counter(run.analysis.category for run in runs if run.analysis is not None))
