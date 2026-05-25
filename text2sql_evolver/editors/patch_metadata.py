from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from text2sql_evolver.skill_manager import RULES_BY_CATEGORY


CATEGORY_TO_OPERATION = {
    "aggregation": "aggregation_reasoning_check",
    "filtering": "clause_level_analysis",
    "join_path": "join_path_analysis",
    "ordering_limit": "order_limit_tiebreak_check",
    "projection": "clause_level_analysis",
    "ratio_numeric": "ratio_numeric_handling",
    "result_shape": "result_shape_comparison",
    "schema_linking": "schema_linking_check",
    "semantic_mismatch": "clause_level_analysis",
    "syntax_or_runtime": "execution_error_classification",
    "value_grounding": "value_grounding_check",
}


def build_patch_metadata(
    failures: list[dict[str, Any]],
    *,
    max_rules: int,
    run_id: str,
    contrast: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for failure in failures:
        grouped[str(failure.get("category") or "unknown")].append(failure)

    timestamp = datetime.now().strftime("%Y%m%d")
    rows: list[dict[str, Any]] = []
    ordered = sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))
    for idx, (category, category_rows) in enumerate(ordered[:max_rules], 1):
        rows.append(
            {
                "patch_id": f"{category}_{timestamp}_{idx:03d}",
                "run_id": run_id,
                "category": category,
                "operation_key": CATEGORY_TO_OPERATION.get(category, "other_sql_error"),
                "support_examples": [str(row.get("id")) for row in category_rows],
                "detector_evidence": _evidence(category_rows),
                "fixability": _fixability_summary(category_rows),
                "contrastive_signals": (contrast or {}).get(category, {}).get("contrastive_signals", []),
                "patch_text": RULES_BY_CATEGORY.get(category, RULES_BY_CATEGORY["semantic_mismatch"]),
            }
        )
    return rows


def _evidence(rows: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for row in rows:
        text = str(row.get("evidence") or "").strip()
        if text and text not in seen:
            seen.append(text)
        details = row.get("details") or {}
        for key in [
            "result_shape_warning",
            "ratio_numeric_warning",
            "value_grounding_warning",
            "evidence_usage_warning",
        ]:
            value = str(details.get(key) or "").strip()
            if value and value not in seen:
                seen.append(value)
    return seen[:8]


def _fixability_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    decisions = [row.get("fixability") or {} for row in rows]
    return {
        "query_skill_fixable": all(bool(decision.get("query_skill_fixable")) for decision in decisions),
        "reasons": [str(decision.get("reason")) for decision in decisions if decision.get("reason")][:5],
        "min_confidence": min(
            [float(decision.get("confidence", 0.0)) for decision in decisions] or [0.0]
        ),
    }
