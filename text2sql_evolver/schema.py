from __future__ import annotations

import sqlite3
from pathlib import Path


def introspect_schema(database_path: Path) -> str:
    """Return compact SQLite schema text for prompting and reports."""
    with sqlite3.connect(database_path) as conn:
        rows = conn.execute(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    return "\n\n".join(sql for _, sql in rows if sql)


def list_tables(database_path: Path) -> list[str]:
    with sqlite3.connect(database_path) as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    return [row[0] for row in rows]
