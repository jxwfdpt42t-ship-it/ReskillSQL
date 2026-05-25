import json
from pathlib import Path

from text2sql_evolver.benchmarks.evaluate_skill_replay import evaluate_skill_replay


def test_evaluate_skill_replay_accepts_predictions_jsonl(tmp_path: Path):
    dataset = tmp_path / "data.jsonl"
    predictions = tmp_path / "predictions.jsonl"
    skill = tmp_path / "SKILL.md"
    dataset.write_text(
        json.dumps(
            {
                "id": "ex1",
                "question": "How many rows?",
                "gold_sql": "SELECT COUNT(*) FROM t;",
                "tags": [],
                "db_path": str(tmp_path / "db.sqlite"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    predictions.write_text(json.dumps({"id": "ex1", "predicted_sql": "SELECT COUNT(*) FROM t;"}) + "\n")
    skill.write_text("## Mandatory Pre-SQL Plan\n", encoding="utf-8")

    import sqlite3

    with sqlite3.connect(tmp_path / "db.sqlite") as conn:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.executemany("INSERT INTO t VALUES (?)", [(1,), (2,)])

    result = evaluate_skill_replay(dataset_path=dataset, predictions_path=predictions, skill_path=skill)

    assert result["total"] == 1
    assert result["before_correct"] == 1
    assert result["after_correct"] == 1
