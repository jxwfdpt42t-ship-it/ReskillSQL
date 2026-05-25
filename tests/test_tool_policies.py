from pathlib import Path
import sqlite3

from text2sql_evolver.inner_runner import apply_sql_skill_checks
from text2sql_evolver.tools import build_schema_context, lookup_similar_values


def test_value_lookup_policy_rewrites_date_literal(tmp_path: Path):
    db = tmp_path / "events.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE expense (expense_date TEXT, description TEXT)")
        conn.execute("INSERT INTO expense VALUES ('2019-08-20', 'Post Cards, Posters')")

    sql = "SELECT description FROM expense WHERE expense_date = '2019-8-20';"

    rewritten = apply_sql_skill_checks(
        sql,
        'What happened on 2019/8/20?',
        "## Mandatory Pre-SQL Plan\n\n### Value Lookup Policy\nVerify stored literal values.\n",
        database_path=db,
    )

    assert "expense_date = '2019-08-20'" in rewritten


def test_value_lookup_finds_similar_stored_value(tmp_path: Path):
    db = tmp_path / "places.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE county (name TEXT)")
        conn.execute("INSERT INTO county VALUES ('Alameda')")

    hits = lookup_similar_values(db, "county", "name", "Alameda County")

    assert hits
    assert hits[0].stored_value == "Alameda"


def test_value_lookup_policy_does_not_rewrite_unrelated_short_categories(tmp_path: Path):
    db = tmp_path / "patients.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE Patient (SEX TEXT, first_name TEXT)")
        conn.executemany("INSERT INTO Patient VALUES (?, ?)", [("F", "Angela"), ("M", "Carlo")])

    sql = "SELECT first_name FROM Patient WHERE SEX = 'M' AND first_name = 'Carlo';"

    rewritten = apply_sql_skill_checks(
        sql,
        "Tell the name of the male patient Carlo.",
        "## Mandatory Pre-SQL Plan\n\n### Value Lookup Policy\nVerify stored literal values.\n",
        database_path=db,
    )

    assert rewritten == sql


def test_schema_context_returns_relevant_columns(tmp_path: Path):
    db = tmp_path / "schema.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE player (player_name TEXT, height_cm REAL)")

    context = build_schema_context(db, "Which player has the greatest height?")

    assert "player.player_name" in context or "player.height_cm" in context
