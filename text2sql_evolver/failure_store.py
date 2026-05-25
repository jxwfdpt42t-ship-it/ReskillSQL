from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any


class FailureStore:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, row: dict[str, Any]) -> None:
        self.rows.append(row)

    def category_counts(self) -> dict[str, int]:
        return dict(Counter(row["category"] for row in self.rows))

    def grouped_examples(self, max_per_category: int = 3) -> dict[str, list[dict[str, Any]]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in self.rows:
            if len(groups[row["category"]]) < max_per_category:
                groups[row["category"]].append(row)
        return dict(groups)

    def to_jsonable(self) -> list[dict[str, Any]]:
        return [_jsonable(row) for row in self.rows]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), indent=2, ensure_ascii=False), encoding="utf-8")


def _jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value
