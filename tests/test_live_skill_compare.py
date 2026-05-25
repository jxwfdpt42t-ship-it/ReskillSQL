from pathlib import Path
import sqlite3

from text2sql_evolver.benchmarks.live_skill_compare import _record_regression_memory, compare_live_skills
from text2sql_evolver.config import Settings


def test_live_skill_compare_counts_improvements(tmp_path: Path):
    db_path = tmp_path / "demo.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE player (player_name TEXT, height INTEGER)")
        conn.execute("INSERT INTO player VALUES ('Ana', 180)")
        conn.execute("INSERT INTO player VALUES ('Bo', 170)")

    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text(
        '{"id":"ex1","question":"Which player is the tallest?",'
        '"gold_sql":"SELECT player_name FROM player ORDER BY height DESC LIMIT 1",'
        f'"db_path":"{db_path}","tags":["test"]}}\n',
        encoding="utf-8",
    )
    before_skill = tmp_path / "before.md"
    after_skill = tmp_path / "after.md"
    before_skill.write_text("old", encoding="utf-8")
    after_skill.write_text("new", encoding="utf-8")
    settings = Settings(
        project_root=tmp_path,
        database_path=db_path,
        dataset_path=dataset,
        reports_dir=tmp_path / "reports",
        model_name="fake",
        api_key="",
        base_url="",
        query_skill_path=after_skill,
    )

    def fake_generator(settings, example, database_path, skill_path):
        if skill_path == before_skill:
            return "SELECT player_name, height FROM player ORDER BY height DESC LIMIT 1"
        return "SELECT player_name FROM player ORDER BY height DESC LIMIT 1"

    result = compare_live_skills(
        settings=settings,
        dataset_path=dataset,
        before_skill=before_skill,
        after_skill=after_skill,
        generator=fake_generator,
    )

    assert result["before_correct"] == 0
    assert result["after_correct"] == 1
    assert result["improvements"] == ["ex1"]
    assert result["regressions"] == []


def test_live_skill_compare_records_regression_memory(tmp_path: Path):
    result = {
        "dataset": "dataset.jsonl",
        "before_skill": "old.md",
        "after_skill": "new.md",
        "model": "fake",
        "rows": [
            {
                "id": "ex1",
                "question": "Which player is the tallest?",
                "db_id": "demo",
                "difficulty": "simple",
                "before_correct": True,
                "after_correct": False,
                "before_reason": "execution_match",
                "after_reason": "execution_mismatch",
                "before_category": None,
                "after_category": "projection",
                "before_sql": "SELECT player_name FROM player",
                "after_sql": "SELECT player_name, height FROM player",
                "gold_sql": "SELECT player_name FROM player",
            }
        ],
    }

    path = tmp_path / "regression_memory.jsonl"
    added = _record_regression_memory(result, path, run_id="run1")
    duplicate = _record_regression_memory(result, path, run_id="run1")

    assert len(added) == 1
    assert duplicate == []
    text = path.read_text(encoding="utf-8")
    assert "candidate skill/tool policy regressed" in text
    assert text.count("ex1") == 1
