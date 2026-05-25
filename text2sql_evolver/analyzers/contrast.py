from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_success_failure_contrast(runs: list[Any]) -> dict[str, dict[str, Any]]:
    """Summarize clause-level differences between successful and failed traces."""

    successes = [run for run in runs if run.correct]
    failures = [run for run in runs if not run.correct and run.analysis is not None]
    if not successes or not failures:
        return {}

    success_signals = [_signals(run.predicted_sql) for run in successes]
    by_category: dict[str, list[Any]] = defaultdict(list)
    for run in failures:
        by_category[run.analysis.category].append(run)

    contrasts: dict[str, dict[str, Any]] = {}
    for category, rows in by_category.items():
        detail_signals = _detail_signals(category, rows)
        failure_signals = [_signals(run.predicted_sql) for run in rows]
        differences = _contrast_signal_sets(success_signals, failure_signals)
        signals = (detail_signals + differences)[:8]
        if signals:
            contrasts[category] = {
                "num_successes": len(successes),
                "num_failures": len(rows),
                "contrastive_signals": signals,
            }
    return contrasts


def _signals(sql: str) -> set[str]:
    lowered = sql.lower()
    signals = set()
    for keyword in ["join", "where", "group by", "order by", "limit", "having", "distinct"]:
        if keyword in lowered:
            signals.add(f"has_{keyword.replace(' ', '_')}")
        else:
            signals.add(f"missing_{keyword.replace(' ', '_')}")
    for agg in ["count(", "sum(", "avg(", "min(", "max("]:
        if agg in lowered:
            signals.add(f"uses_{agg[:-1]}")
    if "/" in lowered:
        signals.add("uses_division")
    if any(token in lowered for token in ["cast(", "nullif(", "1.0"]):
        signals.add("uses_numeric_guard")
    return signals


def _contrast_signal_sets(successes: list[set[str]], failures: list[set[str]]) -> list[str]:
    if not successes or not failures:
        return []
    success_common = set.intersection(*successes)
    failure_common = set.intersection(*failures)
    useful_missing = {"missing_limit", "missing_order_by", "missing_group_by", "missing_join"}
    success_only = sorted(signal for signal in success_common - failure_common if not signal.startswith("missing_"))
    failure_only = sorted(signal for signal in failure_common - success_common if signal in useful_missing)
    return (success_only + failure_only)[:8]


def _detail_signals(category: str, rows: list[Any]) -> list[str]:
    signals: list[str] = []
    for run in rows:
        details = run.analysis.details or {}
        if category == "ordering_limit" and details.get("predicted_order_by") != details.get("gold_order_by"):
            signals.append("failed SQL ranking clause differs from gold ORDER BY / tie-breaker / LIMIT")
        if category == "aggregation" and details.get("predicted_aggregates") != details.get("gold_aggregates"):
            signals.append("failed SQL aggregate functions differ from gold SQL")
        if category == "result_shape" and details.get("predicted_shape") != details.get("gold_shape"):
            signals.append("failed SQL result row/column shape differs from gold SQL")
        if category == "ratio_numeric" and details.get("ratio_numeric_warning"):
            signals.append(str(details["ratio_numeric_warning"]))
        if category == "value_grounding" and details.get("value_grounding_warning"):
            signals.append(str(details["value_grounding_warning"]))
    deduped: list[str] = []
    for signal in signals:
        if signal not in deduped:
            deduped.append(signal)
    return deduped
