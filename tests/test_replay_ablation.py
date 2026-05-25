from pathlib import Path
import json
import sqlite3

from text2sql_evolver.benchmarks.replay_ablation import run_replay_ablation


def test_replay_ablation_reports_variants(tmp_path: Path):
    db_path = tmp_path / "demo.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE event (id INTEGER, location TEXT)")
        conn.execute("CREATE TABLE budget (event_id INTEGER, category TEXT)")
        conn.execute("INSERT INTO event VALUES (1, 'MU 215')")
        conn.execute("INSERT INTO budget VALUES (1, 'Food')")
        conn.execute("INSERT INTO budget VALUES (1, 'Food')")

    dataset = tmp_path / "data.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "ex1",
                "question": "State the category of events were held at MU 215.",
                "gold_sql": (
                    "SELECT DISTINCT budget.category FROM event "
                    "JOIN budget ON event.id = budget.event_id WHERE event.location = 'MU 215'"
                ),
                "tags": [],
                "db_path": str(db_path),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    predictions = tmp_path / "predictions.jsonl"
    predictions.write_text(
        json.dumps(
            {
                "id": "ex1",
                "predicted_sql": (
                    "SELECT budget.category FROM event "
                    "JOIN budget ON event.id = budget.event_id WHERE event.location = 'MU 215'"
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "## Mandatory Pre-SQL Plan\n\n### Result Shape Check\nUse DISTINCT for list outputs.\n",
        encoding="utf-8",
    )

    summary = run_replay_ablation(dataset_path=dataset, predictions_path=predictions, skill_path=skill)

    variants = {row["name"]: row for row in summary["variants"]}
    assert set(variants) == {"no_reskill", "query_skill_checks_only", "value_lookup_only", "full_system"}
    assert variants["no_reskill"]["after_correct"] == 0
    assert variants["full_system"]["after_correct"] == 1
