from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import re
import sqlite3


@dataclass(frozen=True)
class SchemaColumnCandidate:
    table: str
    column: str
    score: float


def build_schema_context(database_path: Path, question: str, *, limit: int = 12) -> str:
    candidates = find_schema_candidates(database_path, question, limit=limit)
    if not candidates:
        return "No schema candidates found."
    lines = ["Relevant schema candidates:"]
    for candidate in candidates:
        lines.append(f"- {candidate.table}.{candidate.column} score={candidate.score:.2f}")
    return "\n".join(lines)


def find_schema_candidates(database_path: Path, question: str, *, limit: int = 12) -> list[SchemaColumnCandidate]:
    tokens = _question_tokens(question)
    if not database_path.exists() or not tokens:
        return []
    columns = _schema_columns(database_path)
    candidates = []
    for table, column in columns:
        score = max(_similarity(token, column) for token in tokens)
        table_score = max(_similarity(token, table) for token in tokens)
        score = max(score, table_score * 0.8)
        if score >= 0.55:
            candidates.append(SchemaColumnCandidate(table, column, score))
    return sorted(candidates, key=lambda item: item.score, reverse=True)[:limit]


def _schema_columns(database_path: Path) -> list[tuple[str, str]]:
    with sqlite3.connect(database_path) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        columns = []
        for table in tables:
            for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table)})").fetchall():
                columns.append((table, str(row[1])))
    return columns


def _question_tokens(question: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_]+", question.lower())
    stop = {
        "what",
        "which",
        "where",
        "when",
        "with",
        "from",
        "that",
        "this",
        "their",
        "have",
        "has",
        "list",
        "give",
        "show",
        "state",
        "please",
    }
    return [word for word in words if word not in stop and len(word) > 2]


def _similarity(left: str, right: str) -> float:
    left_norm = _normalize_identifier(left)
    right_norm = _normalize_identifier(right)
    if left_norm == right_norm:
        return 1.0
    if left_norm in right_norm or right_norm in left_norm:
        return 0.85
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
