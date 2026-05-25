from __future__ import annotations

import json
from pathlib import Path


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_sql_skill_benchmark_splits_exist() -> None:
    root = Path("data/self_update/sql_skill_benchmark")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    categories = ("ordering_limit", "ratio_numeric", "aggregation_projection")
    splits = ("update", "validation", "holdout")

    for category in categories:
        for split in splits:
            rows = _read_jsonl(root / category / f"{split}.jsonl")
            assert len(rows) == 8
            assert all(category in row["tags"] for row in rows)
            assert manifest["categories"][category][split] == [row["id"] for row in rows]

    for split in splits:
        combined = _read_jsonl(root / "combined" / f"{split}.jsonl")
        assert len(combined) == 24
