from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FailureAnalysis:
    category: str
    evidence: str
    details: dict[str, Any] | None = None


def analyze_failure(
    question: str,
    predicted_sql: str,
    gold_sql: str,
    judge_reason: str,
    predicted_rows: list[tuple[Any, ...]] | None = None,
    gold_rows: list[tuple[Any, ...]] | None = None,
    evidence_hint: str | None = None,
) -> FailureAnalysis:
    predicted = predicted_sql or ""
    gold = gold_sql or ""
    reason = judge_reason.lower()
    signals = _collect_signals(
        question=question,
        predicted_sql=predicted,
        gold_sql=gold,
        predicted_rows=predicted_rows or [],
        gold_rows=gold_rows or [],
        evidence_hint=evidence_hint,
    )

    if "failed" in reason or "syntax" in reason or "no such" in reason:
        if "no such table" in reason or "no such column" in reason:
            return FailureAnalysis("schema_linking", judge_reason, signals)
        if signals.get("value_grounding_warning"):
            return FailureAnalysis("value_grounding", signals["value_grounding_warning"], signals)
        if signals.get("ratio_numeric_warning"):
            return FailureAnalysis("ratio_numeric", signals["ratio_numeric_warning"], signals)
        if signals.get("result_shape_warning"):
            return FailureAnalysis("result_shape", signals["result_shape_warning"], signals)
        return FailureAnalysis("syntax_or_runtime", judge_reason, signals)

    if signals.get("value_grounding_warning"):
        return FailureAnalysis("value_grounding", signals["value_grounding_warning"], signals)

    if signals.get("ratio_numeric_warning"):
        return FailureAnalysis("ratio_numeric", signals["ratio_numeric_warning"], signals)

    pred_tables = _tables(predicted)
    gold_tables = _tables(gold)
    if pred_tables != gold_tables:
        return FailureAnalysis(
            "schema_linking",
            f"table mismatch: predicted={sorted(pred_tables)} gold={sorted(gold_tables)}",
            signals,
        )

    pred_join_count = len(re.findall(r"\bJOIN\b", predicted, re.IGNORECASE))
    gold_join_count = len(re.findall(r"\bJOIN\b", gold, re.IGNORECASE))
    if pred_join_count != gold_join_count:
        return FailureAnalysis("join_path", f"join count mismatch: predicted={pred_join_count} gold={gold_join_count}", signals)

    if _has_clause(gold, "group by") != _has_clause(predicted, "group by") or _aggregate_set(gold) != _aggregate_set(predicted):
        return FailureAnalysis("aggregation", "GROUP BY or aggregate function mismatch", signals)

    if _has_clause(gold, "where") != _has_clause(predicted, "where"):
        return FailureAnalysis("filtering", "WHERE clause presence mismatch", signals)

    if (
        _has_clause(gold, "order by") != _has_clause(predicted, "order by")
        or _has_clause(gold, "limit") != _has_clause(predicted, "limit")
        or _order_by_clause(gold) != _order_by_clause(predicted)
    ):
        return FailureAnalysis("ordering_limit", "ORDER BY, tie-breaker, or LIMIT mismatch", signals)

    if _selected_columns(gold) != _selected_columns(predicted):
        return FailureAnalysis("projection", "selected column mismatch", signals)

    if signals.get("result_shape_warning"):
        return FailureAnalysis("result_shape", signals["result_shape_warning"], signals)

    return FailureAnalysis("semantic_mismatch", "execution results differ but no simple clause mismatch was detected", signals)


def _tables(sql: str) -> set[str]:
    return {
        match.group(2).strip('"[]`')
        for match in re.finditer(r"\b(FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", sql, re.IGNORECASE)
    }


def _has_clause(sql: str, clause: str) -> bool:
    return bool(re.search(r"\b" + re.escape(clause).replace("\\ ", r"\s+") + r"\b", sql, re.IGNORECASE))


def _aggregate_set(sql: str) -> set[str]:
    return {name.lower() for name in re.findall(r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\(", sql, re.IGNORECASE)}


def _selected_columns(sql: str) -> set[str]:
    match = re.search(r"\bSELECT\b(.*?)\bFROM\b", sql, re.IGNORECASE | re.DOTALL)
    if not match:
        return set()
    return {part.strip().lower() for part in match.group(1).split(",") if part.strip()}


def _order_by_clause(sql: str) -> str:
    match = re.search(r"\bORDER\s+BY\b(.*?)(?:\bLIMIT\b|;|$)", sql, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip().lower()


def _collect_signals(
    question: str,
    predicted_sql: str,
    gold_sql: str,
    predicted_rows: list[tuple[Any, ...]],
    gold_rows: list[tuple[Any, ...]],
    evidence_hint: str | None,
) -> dict[str, Any]:
    signals: dict[str, Any] = {
        "predicted_shape": _shape(predicted_rows),
        "gold_shape": _shape(gold_rows),
        "predicted_tables": sorted(_tables(predicted_sql)),
        "gold_tables": sorted(_tables(gold_sql)),
        "predicted_aggregates": sorted(_aggregate_set(predicted_sql)),
        "gold_aggregates": sorted(_aggregate_set(gold_sql)),
        "predicted_order_by": _order_by_clause(predicted_sql),
        "gold_order_by": _order_by_clause(gold_sql),
        "question_triggers": _question_triggers(question),
    }

    shape_warning = _shape_warning(signals["predicted_shape"], signals["gold_shape"], question)
    if shape_warning:
        signals["result_shape_warning"] = shape_warning

    ratio_warning = _ratio_warning(question, predicted_sql, gold_sql, evidence_hint)
    if ratio_warning:
        signals["ratio_numeric_warning"] = ratio_warning

    value_warning = _value_warning(question, predicted_sql, gold_sql)
    if value_warning:
        signals["value_grounding_warning"] = value_warning

    evidence_warning = _evidence_warning(evidence_hint, predicted_sql)
    if evidence_warning:
        signals["evidence_usage_warning"] = evidence_warning

    return signals


def _shape(rows: list[tuple[Any, ...]]) -> dict[str, Any]:
    return {
        "row_count": len(rows),
        "column_count": len(rows[0]) if rows else 0,
        "types": [type(value).__name__ for value in rows[0]] if rows else [],
    }


def _shape_warning(predicted_shape: dict[str, Any], gold_shape: dict[str, Any], question: str) -> str | None:
    if predicted_shape == gold_shape:
        return None
    q = question.lower()
    if re.search(r"\b(highest|lowest|top|bottom|first|last|most|least)\b", q) and predicted_shape["row_count"] != gold_shape["row_count"]:
        return f"ranking result row count mismatch: predicted={predicted_shape['row_count']} gold={gold_shape['row_count']}"
    if predicted_shape["column_count"] != gold_shape["column_count"]:
        return f"result column count mismatch: predicted={predicted_shape['column_count']} gold={gold_shape['column_count']}"
    return None


def _ratio_warning(question: str, predicted_sql: str, gold_sql: str, evidence_hint: str | None) -> str | None:
    combined = " ".join(part for part in [question, evidence_hint or ""] if part).lower()
    ratio_trigger = re.search(r"\b(rate|ratio|percentage|percent|average|avg|per|proportion)\b", combined)
    if not ratio_trigger:
        return None
    gold_has_division = "/" in gold_sql
    pred_has_division = "/" in predicted_sql
    if gold_has_division and not pred_has_division:
        return "question/evidence suggests ratio calculation but predicted SQL has no division"
    if pred_has_division and not re.search(r"\b(CAST|REAL|1\.0|NULLIF)\b", predicted_sql, re.IGNORECASE):
        return "ratio calculation may need REAL cast or NULLIF denominator guard"
    if pred_has_division and _has_clause(gold_sql, "order by") and not _has_clause(predicted_sql, "order by"):
        return "ratio query likely needs ORDER BY on computed metric"
    return None


def _value_warning(question: str, predicted_sql: str, gold_sql: str) -> str | None:
    question_values = set(re.findall(r"\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\b", question))
    pred_flat = set(re.findall(r"'([^']+)'", predicted_sql))
    gold_flat = set(re.findall(r"'([^']+)'", gold_sql))
    if gold_flat and pred_flat and pred_flat != gold_flat:
        return f"literal value mismatch: predicted={sorted(pred_flat)} gold={sorted(gold_flat)}"
    if question_values and gold_flat and not any(value in pred_flat for value in gold_flat):
        return f"question entity may not be grounded to gold literal values: expected one of {sorted(gold_flat)}"
    return None


def _evidence_warning(evidence_hint: str | None, predicted_sql: str) -> str | None:
    if not evidence_hint:
        return None
    quoted_terms = re.findall(r"`([^`]+)`", evidence_hint)
    missing = [term for term in quoted_terms if term not in predicted_sql]
    if quoted_terms and missing:
        return f"predicted SQL may ignore evidence terms: {missing[:5]}"
    return None


def _question_triggers(question: str) -> list[str]:
    triggers = []
    lowered = question.lower()
    for name, pattern in {
        "ranking": r"\b(highest|lowest|top|bottom|most|least)\b",
        "ratio": r"\b(rate|ratio|percentage|percent|per|proportion)\b",
        "aggregation": r"\b(count|sum|average|avg|total|number of)\b",
        "value_filter": r"\b(where|in|from|for)\b",
    }.items():
        if re.search(pattern, lowered):
            triggers.append(name)
    return triggers
