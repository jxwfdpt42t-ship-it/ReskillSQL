from __future__ import annotations

import json
from pathlib import Path
from argparse import Namespace

from text2sql_evolver.benchmarks.make_sql_skill_benchmark import (
    build_buckets, split_buckets, write_benchmark, write_manifest,
)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_sql_skill_benchmark_splits_exist(tmp_path) -> None:
    root = tmp_path / "benchmark"
    categories = ("ordering_limit", "ratio_numeric", "aggregation_projection")
    examples = [{"id": f"{category}-{i}", "category": "aggregation" if category == "aggregation_projection" else category,
                 "question": f"question {i}",
                 "gold_sql": "SELECT 1", "tags": []} for category in categories for i in range(24)]
    built = split_buckets(build_buckets(examples), per_split=8, seed=42)
    write_benchmark(root, built)
    write_manifest(root, Namespace(input="synthetic-fixture", bird_root=tmp_path, per_split=8, seed=42), built)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
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
