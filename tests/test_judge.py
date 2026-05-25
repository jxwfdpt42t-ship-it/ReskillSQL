from pathlib import Path
import sqlite3

from text2sql_evolver.judge import execute_sql
from text2sql_evolver.judge import judge_sql
from text2sql_evolver.llm import extract_sql


ROOT = Path(__file__).resolve().parents[1]


def test_judge_accepts_execution_equivalent_sql():
    result = judge_sql(
        ROOT / "chinook.db",
        "SELECT COUNT(CustomerId) FROM Customer WHERE Country = 'Canada';",
        "SELECT COUNT(*) FROM Customer WHERE Country = 'Canada';",
    )
    assert result.correct


def test_judge_rejects_wrong_result():
    result = judge_sql(
        ROOT / "chinook.db",
        "SELECT COUNT(*) FROM Customer WHERE Country = 'USA';",
        "SELECT COUNT(*) FROM Customer WHERE Country = 'Canada';",
    )
    assert not result.correct


def test_judge_accepts_unordered_rows_when_gold_has_no_order_by():
    result = judge_sql(
        ROOT / "chinook.db",
        "SELECT Country FROM Customer WHERE Country IN ('Brazil', 'Canada') GROUP BY Country ORDER BY Country DESC;",
        "SELECT Country FROM Customer WHERE Country IN ('Brazil', 'Canada') GROUP BY Country;",
    )
    assert result.correct
    assert result.reason == "execution_match_unordered"


def test_judge_blocks_write_sql():
    result = judge_sql(
        ROOT / "chinook.db",
        "DELETE FROM Customer;",
        "SELECT COUNT(*) FROM Customer;",
    )
    assert not result.correct
    assert "read-only" in (result.predicted.error or "")


def test_extract_sql_handles_sqlite_fence():
    assert extract_sql("```sqlite\nSELECT 1;\n```") == "SELECT 1;"


def test_execute_sql_times_out_expensive_query(tmp_path: Path):
    db = tmp_path / "slow.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE nums (n INTEGER)")
        conn.executemany("INSERT INTO nums VALUES (?)", [(i,) for i in range(300)])

    result = execute_sql(
        db,
        "SELECT COUNT(*) FROM nums a, nums b, nums c, nums d, nums e",
        timeout_ms=1,
    )

    assert not result.ok
