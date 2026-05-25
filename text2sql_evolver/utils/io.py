from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_prediction_jsonl(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    predictions: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            predictions[str(row["id"])] = str(row["predicted_sql"])
    return predictions


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    from text2sql_evolver.failure_store import write_json as _write_json

    _write_json(path, payload)
