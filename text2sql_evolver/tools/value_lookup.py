from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import re
import sqlite3
from typing import Iterable


@dataclass(frozen=True)
class ValueLookupHit:
    table: str
    column: str
    query_value: str
    stored_value: str
    score: float


def apply_value_lookup_policy(sql: str, database_path: Path, *, min_score: float = 0.92) -> str:
    """Rewrite obvious literal-format mismatches using values from the same database column."""
    if not database_path.exists():
        return sql
    alias_map = _alias_map(sql)
    replacements: dict[tuple[str, str, str], str] = {}
    for reference, operator, literal in _where_literal_filters(sql):
        column = reference.split(".")[-1].strip('"[]`')
        table = _resolve_table(reference, alias_map, database_path, column)
        if table is None:
            continue
        hit = _best_value_match(database_path, table, column, literal, min_score=min_score)
        if hit and hit.stored_value != literal:
            replacements[(reference, operator, literal)] = hit.stored_value

    rewritten = sql
    for (reference, operator, old_value), new_value in replacements.items():
        pattern = (
            r"(\b"
            + re.escape(reference)
            + r"\b\s*"
            + re.escape(operator)
            + r"\s*)'"
            + re.escape(old_value)
            + r"'"
        )
        rewritten = re.sub(pattern, lambda m: m.group(1) + "'" + new_value.replace("'", "''") + "'", rewritten)
    return rewritten


def lookup_similar_values(
    database_path: Path,
    table: str,
    column: str,
    query_value: str,
    *,
    limit: int = 5,
) -> list[ValueLookupHit]:
    values = _sample_distinct_values(database_path, table, column)
    hits = [
        ValueLookupHit(table, column, query_value, value, _value_similarity(query_value, value))
        for value in values
    ]
    return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]


def _best_value_match(
    database_path: Path,
    table: str,
    column: str,
    query_value: str,
    *,
    min_score: float,
) -> ValueLookupHit | None:
    hits = lookup_similar_values(database_path, table, column, query_value, limit=1)
    if not hits:
        return None
    hit = hits[0]
    return hit if hit.score >= min_score else None


def _sample_distinct_values(database_path: Path, table: str, column: str, limit: int = 5000) -> list[str]:
    safe_table = _quote_identifier(table)
    safe_column = _quote_identifier(column)
    try:
        with sqlite3.connect(database_path) as conn:
            rows = conn.execute(
                f"SELECT DISTINCT {safe_column} FROM {safe_table} "
                f"WHERE {safe_column} IS NOT NULL LIMIT ?",
                (limit,),
            ).fetchall()
    except Exception:
        return []
    return [str(row[0]) for row in rows if row and row[0] is not None]


def _where_literal_filters(sql: str) -> Iterable[tuple[str, str, str]]:
    where_match = re.search(
        r"\bWHERE\b(.*?)(?:\bGROUP\s+BY\b|\bHAVING\b|\bORDER\s+BY\b|\bLIMIT\b|;|$)",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    if not where_match:
        return []
    where = where_match.group(1)
    return [
        (match.group("ref"), match.group("op").upper(), match.group("literal").replace("''", "'"))
        for match in re.finditer(
            r"(?P<ref>(?:\w+\.)?\w+)\s*(?P<op>=|LIKE)\s*'(?P<literal>(?:''|[^'])*)'",
            where,
            re.IGNORECASE,
        )
    ]


def _alias_map(sql: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for match in re.finditer(
        r"\b(?:FROM|JOIN)\s+(?P<table>[A-Za-z_][\w]*)\s+(?:AS\s+)?(?P<alias>[A-Za-z_][\w]*)",
        sql,
        re.IGNORECASE,
    ):
        table = match.group("table")
        alias = match.group("alias")
        if alias.upper() not in {"ON", "WHERE", "JOIN", "GROUP", "ORDER", "LIMIT"}:
            mapping[alias] = table
            mapping[table] = table
    for match in re.finditer(r"\b(?:FROM|JOIN)\s+(?P<table>[A-Za-z_][\w]*)(?=\s|;|$)", sql, re.IGNORECASE):
        table = match.group("table")
        mapping.setdefault(table, table)
    return mapping


def _resolve_table(reference: str, alias_map: dict[str, str], database_path: Path, column: str) -> str | None:
    if "." not in reference:
        return _unique_table_with_column(database_path, alias_map.values(), column)
    alias = reference.split(".", 1)[0]
    return alias_map.get(alias)


def _unique_table_with_column(database_path: Path, tables: Iterable[str], column: str) -> str | None:
    unique_tables = sorted(set(tables))
    matches = []
    try:
        with sqlite3.connect(database_path) as conn:
            for table in unique_tables:
                rows = conn.execute(f"PRAGMA table_info({_quote_identifier(table)})").fetchall()
                if any(str(row[1]).lower() == column.lower() for row in rows):
                    matches.append(table)
    except Exception:
        return None
    return matches[0] if len(matches) == 1 else None


def _value_similarity(left: str, right: str) -> float:
    left_norm = _normalize_value(left)
    right_norm = _normalize_value(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    left_date = _normalize_date(left)
    right_date = _normalize_date(right)
    if left_date and right_date and left_date == right_date:
        return 1.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _normalize_value(value: str) -> str:
    date = _normalize_date(value)
    if date:
        return date
    lowered = value.lower().strip()
    lowered = re.sub(r"['`\"]", "", lowered)
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _normalize_date(value: str) -> str:
    match = re.fullmatch(r"\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*", value)
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
