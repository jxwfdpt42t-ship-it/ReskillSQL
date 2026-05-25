from __future__ import annotations

from typing import Any

from text2sql_evolver.config import Settings
from text2sql_evolver.failure_store import FailureStore
from text2sql_evolver.skill_manager import generate_llm_patch_bundle


class SkillPatchGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build_evidence_packet(
        self,
        store: FailureStore,
        *,
        patch_metadata: list[dict[str, Any]] | None = None,
        contrast: dict[str, Any] | None = None,
        rejected_patches: list[dict[str, Any]] | None = None,
        behavior_signals: list[dict[str, Any]] | None = None,
        trajectory_cards: list[dict[str, Any]] | None = None,
        category_summaries: list[dict[str, Any]] | None = None,
        weighted_support: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "fixable_failures": store.grouped_examples(max_per_category=5),
            "behavior_signals": _compact_behavior_signals(behavior_signals or []),
            "trajectory_cards": _compact_trajectory_cards(trajectory_cards or []),
            "category_summaries": category_summaries or [],
            "weighted_support": weighted_support or {},
            "detector_evidence": _detector_evidence(store.rows),
            "patch_metadata": patch_metadata or [],
            "success_failure_contrast": contrast or {},
            "rejected_patch_memory": _compact_rejected(rejected_patches or []),
        }

    def generate(
        self,
        store: FailureStore,
        *,
        evidence_packet: dict[str, Any] | None = None,
    ) -> str:
        return self.generate_bundle(store, evidence_packet=evidence_packet).markdown

    def generate_bundle(
        self,
        store: FailureStore,
        *,
        evidence_packet: dict[str, Any] | None = None,
    ):
        if not store.rows:
            from text2sql_evolver.editors.patch_aggregator import PatchBundle

            return PatchBundle([], [], "")
        return generate_llm_patch_bundle(self.settings, store, evidence_packet=evidence_packet)


def _detector_evidence(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    evidence: dict[str, list[str]] = {}
    for row in rows:
        category = str(row.get("category") or "unknown")
        evidence.setdefault(category, [])
        text = str(row.get("evidence") or "").strip()
        if text and text not in evidence[category]:
            evidence[category].append(text)
        details = row.get("details") or {}
        for key in [
            "result_shape_warning",
            "ratio_numeric_warning",
            "value_grounding_warning",
            "evidence_usage_warning",
        ]:
            value = str(details.get(key) or "").strip()
            if value and value not in evidence[category]:
                evidence[category].append(value)
    return {category: rows[:8] for category, rows in evidence.items()}


def _compact_rejected(rows: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    compacted = []
    for row in rows[-limit:]:
        compacted.append(
            {
                "run_id": row.get("run_id"),
                "reason": row.get("reason"),
                "patch_preview": str(row.get("patch_text") or "")[:800],
                "metadata": row.get("metadata", {}),
            }
        )
    return compacted


def _compact_behavior_signals(rows: list[dict[str, Any]], limit: int = 40) -> list[dict[str, Any]]:
    priority = {"hard_failure": 0, "repair_heavy_success": 1, "risky_success": 2, "overlong_success": 3}
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            priority.get(str(row.get("signal_type")), 9),
            -float(row.get("weight") or 0.0),
            str(row.get("example_id") or ""),
        ),
    )
    return [
        {
            "example_id": row.get("example_id"),
            "outcome": row.get("outcome"),
            "signal_type": row.get("signal_type"),
            "category": row.get("category"),
            "severity": row.get("severity"),
            "weight": row.get("weight"),
            "evidence": row.get("evidence"),
        }
        for row in sorted_rows[:limit]
        if float(row.get("weight") or 0.0) > 0
    ]


def _compact_trajectory_cards(rows: list[dict[str, Any]], limit: int = 40) -> list[dict[str, Any]]:
    priority = {"hard_failure": 0, "repair_heavy_success": 1, "risky_success": 2, "overlong_success": 3}
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            priority.get(str(row.get("signal_type")), 9),
            str(row.get("fix_route") or ""),
            -float(row.get("weight") or 0.0),
            str(row.get("example_id") or ""),
        ),
    )
    compacted = []
    for row in sorted_rows[:limit]:
        if float(row.get("weight") or 0.0) <= 0 and row.get("fix_route") != "contrast_only":
            continue
        compacted.append(
            {
                "example_id": row.get("example_id"),
                "outcome": row.get("outcome"),
                "category": row.get("category"),
                "signal_type": row.get("signal_type"),
                "weight": row.get("weight"),
                "evidence": row.get("evidence"),
                "relevant_sql_diff": row.get("relevant_sql_diff"),
                "execution_signal": row.get("execution_signal"),
                "bird_evidence": row.get("bird_evidence"),
                "tool_trace": row.get("tool_trace"),
                "fix_route": row.get("fix_route"),
                "route_reason": row.get("route_reason"),
            }
        )
    return compacted
