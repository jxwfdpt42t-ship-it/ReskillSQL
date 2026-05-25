from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any


@dataclass
class RegressionMemoryStore:
    rows: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "RegressionMemoryStore":
        if not path.exists():
            return cls()
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return cls(rows)

    def add_from_live_result(self, result: dict[str, Any], *, run_id: str) -> list[dict[str, Any]]:
        existing_keys = {_memory_key(row) for row in self.rows}
        added = []
        for row in result.get("rows", []):
            if not row.get("before_correct") or row.get("after_correct"):
                continue
            memory_row = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "run_id": run_id,
                "dataset": result.get("dataset"),
                "before_skill": result.get("before_skill"),
                "after_skill": result.get("after_skill"),
                "model": result.get("model"),
                "id": row.get("id"),
                "question": row.get("question"),
                "db_id": row.get("db_id"),
                "difficulty": row.get("difficulty"),
                "category": row.get("after_category") or row.get("before_category"),
                "before_sql": row.get("before_sql"),
                "after_sql": row.get("after_sql"),
                "gold_sql": row.get("gold_sql"),
                "before_reason": row.get("before_reason"),
                "after_reason": row.get("after_reason"),
                "suspected_cause": _suspected_cause(row),
            }
            key = _memory_key(memory_row)
            if key in existing_keys:
                continue
            self.rows.append(memory_row)
            existing_keys.add(key)
            added.append(memory_row)
        return added

    def write_jsonl(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "\n".join(json.dumps(row, ensure_ascii=False) for row in self.rows)
        path.write_text(text + ("\n" if text else ""), encoding="utf-8")


def _memory_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("dataset")), str(row.get("after_skill")), str(row.get("id")))


def _suspected_cause(row: dict[str, Any]) -> str:
    category = str(row.get("after_category") or row.get("before_category") or "unknown")
    return f"candidate skill/tool policy regressed a previously correct {category} example"
