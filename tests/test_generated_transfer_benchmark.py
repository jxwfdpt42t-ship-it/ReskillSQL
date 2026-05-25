from pathlib import Path
import json
import sqlite3

from text2sql_evolver.benchmarks.make_generated_transfer_benchmark import build_generated_transfer_benchmark


def test_build_generated_transfer_benchmark_writes_validated_splits(tmp_path: Path):
    bird_root = tmp_path / "bird"
    db_dir = bird_root / "dev_databases" / "demo"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "demo.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE sale (id INTEGER, region TEXT, amount REAL)")
        conn.execute("INSERT INTO sale VALUES (1, 'west', 10.0)")
        conn.execute("INSERT INTO sale VALUES (2, 'east', 20.0)")

    input_path = bird_root / "mini_dev_sqlite.json"
    rows = [
        {
            "question_id": i,
            "db_id": "demo",
            "question": f"What is the top sale amount for row {i}?",
            "SQL": "SELECT region FROM sale ORDER BY amount DESC LIMIT 1",
            "evidence": None,
            "difficulty": "simple",
        }
        for i in range(10)
    ]
    input_path.write_text(json.dumps(rows), encoding="utf-8")

    output_dir = tmp_path / "generated"
    summary = build_generated_transfer_benchmark(
        input_path=input_path,
        bird_root=bird_root,
        output_dir=output_dir,
        limit=10,
        seed=7,
    )

    assert summary["total"] == 10
    assert summary["validated"] == 10
    assert summary["split_counts"] == {"update": 4, "validation": 3, "holdout": 3}
    assert summary["category_counts"] == {"ordering_limit": 10}
    assert (output_dir / "manifest.json").exists()
    assert _jsonl_count(output_dir / "combined" / "update.jsonl") == 4
    assert _jsonl_count(output_dir / "ordering_limit" / "validation.jsonl") == 3


def _jsonl_count(path: Path) -> int:
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])
