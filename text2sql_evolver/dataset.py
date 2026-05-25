from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Example:
    id: str
    question: str
    gold_sql: str
    tags: tuple[str, ...]
    db_path: str | None = None
    db_id: str | None = None
    evidence: str | None = None
    difficulty: str | None = None


def load_jsonl(path: Path, limit: int | None = None) -> list[Example]:
    examples: list[Example] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            examples.append(
                Example(
                    id=str(row["id"]),
                    question=str(row["question"]),
                    gold_sql=str(row["gold_sql"]),
                    tags=tuple(row.get("tags") or ()),
                    db_path=row.get("db_path"),
                    db_id=row.get("db_id"),
                    evidence=row.get("evidence"),
                    difficulty=row.get("difficulty"),
                )
            )
            if limit and len(examples) >= limit:
                break
    return examples
