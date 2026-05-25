from __future__ import annotations

import re
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


WRITE_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|DETACH|VACUUM|PRAGMA)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    rows: list[tuple[Any, ...]]
    error: str | None = None


@dataclass(frozen=True)
class JudgeResult:
    correct: bool
    predicted: ExecutionResult
    gold: ExecutionResult
    reason: str


def is_read_only_sql(sql: str) -> bool:
    return bool(re.match(r"^\s*(WITH\b.*?SELECT|SELECT)\b", sql, re.IGNORECASE | re.DOTALL)) and not WRITE_PATTERN.search(sql)


def execute_sql(database_path: Path, sql: str, timeout_ms: int = 5000) -> ExecutionResult:
    if not is_read_only_sql(sql):
        return ExecutionResult(ok=False, rows=[], error="Only read-only SELECT SQL is allowed.")

    try:
        with sqlite3.connect(database_path) as conn:
            conn.execute("PRAGMA query_only = ON")
            conn.execute(f"PRAGMA busy_timeout = {timeout_ms}")
            started = time.monotonic()

            def _interrupt_if_slow() -> int:
                return int((time.monotonic() - started) * 1000 > timeout_ms)

            conn.set_progress_handler(_interrupt_if_slow, 1000)
            rows = conn.execute(sql).fetchall()
            conn.set_progress_handler(None, 0)
        return ExecutionResult(ok=True, rows=_normalize_rows(rows))
    except Exception as exc:
        return ExecutionResult(ok=False, rows=[], error=str(exc))


def judge_sql(database_path: Path, predicted_sql: str, gold_sql: str) -> JudgeResult:
    predicted = execute_sql(database_path, predicted_sql)
    gold = execute_sql(database_path, gold_sql)

    if not gold.ok:
        return JudgeResult(False, predicted, gold, f"gold_sql_failed: {gold.error}")
    if not predicted.ok:
        return JudgeResult(False, predicted, gold, f"predicted_sql_failed: {predicted.error}")
    if predicted.rows == gold.rows:
        return JudgeResult(True, predicted, gold, "execution_match")
    if not _has_order_by(gold_sql) and Counter(predicted.rows) == Counter(gold.rows):
        return JudgeResult(True, predicted, gold, "execution_match_unordered")
    return JudgeResult(False, predicted, gold, "execution_mismatch")


def _normalize_rows(rows: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    normalized = []
    for row in rows:
        normalized.append(tuple(_normalize_value(value) for value in row))
    return normalized


def _has_order_by(sql: str) -> bool:
    return bool(re.search(r"\bORDER\s+BY\b", sql, re.IGNORECASE))


def _normalize_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    return value
