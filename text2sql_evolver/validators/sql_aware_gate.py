from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SQLAwareGateDecision:
    accepted: bool
    reason: str
    metrics: dict[str, Any]


class SQLAwareGate:
    def __init__(
        self,
        *,
        min_delta: float = 0.0,
        max_regressions: int = 1,
        max_protected_regressions: int = 0,
        require_target_improvement: bool = False,
        min_score: int = 4,
        max_patch_words: int = 120,
    ) -> None:
        self.min_delta = min_delta
        self.max_regressions = max_regressions
        self.max_protected_regressions = max_protected_regressions
        self.require_target_improvement = require_target_improvement
        self.min_score = min_score
        self.max_patch_words = max_patch_words

    def decide(
        self,
        *,
        before_rows: list[dict[str, Any]],
        after_rows: list[dict[str, Any]],
        patch_metadata: list[dict[str, Any]],
        protected_before_rows: list[dict[str, Any]] | None = None,
        protected_after_rows: list[dict[str, Any]] | None = None,
    ) -> SQLAwareGateDecision:
        before_accuracy = _accuracy(before_rows)
        after_accuracy = _accuracy(after_rows)
        delta = after_accuracy - before_accuracy
        regressions = [
            after["id"]
            for before, after in zip(before_rows, after_rows)
            if before.get("correct") and not after.get("correct")
        ]
        improvements = [
            after["id"]
            for before, after in zip(before_rows, after_rows)
            if not before.get("correct") and after.get("correct")
        ]
        target_categories = sorted({row["category"] for row in patch_metadata if row.get("category")})
        before_counts = _target_counts(before_rows, target_categories)
        after_counts = _target_counts(after_rows, target_categories)
        target_improved = any(after_counts.get(cat, 0) < before_counts.get(cat, 0) for cat in target_categories)
        quality = _patch_quality(patch_metadata, max_words=self.max_patch_words)
        protected_regressions = _regressions(protected_before_rows or [], protected_after_rows or [])
        scorecard = _scorecard(
            regressions=regressions,
            improvements=improvements,
            target_categories=target_categories,
            before_counts=before_counts,
            after_counts=after_counts,
            target_improved=target_improved,
            quality=quality,
        )

        metrics = {
            "before_accuracy": before_accuracy,
            "after_accuracy": after_accuracy,
            "accuracy_delta": delta,
            "current_score": before_accuracy,
            "candidate_score": after_accuracy,
            "score_delta": delta,
            "regressions": regressions,
            "improvements": improvements,
            "target_categories": target_categories,
            "target_category_before": before_counts,
            "target_category_after": after_counts,
            "target_category_improved": target_improved,
            "patch_quality": quality,
            "protected_regressions": protected_regressions,
            "protected_regression_total": len(protected_regressions),
            "scorecard": scorecard,
        }

        strict_min_delta = max(self.min_delta, 0.0)
        if delta <= strict_min_delta:
            metrics["gate_level"] = "reject"
            return SQLAwareGateDecision(False, f"selection_score_not_improved={delta:.4f}", metrics)
        if not quality["not_specific_to_dataset"]:
            metrics["gate_level"] = "reject"
            return SQLAwareGateDecision(False, "patch_overfits_specific_dataset_or_example", metrics)
        if not quality["length_ok"]:
            metrics["gate_level"] = "reject"
            return SQLAwareGateDecision(False, "patch_too_long", metrics)
        if len(protected_regressions) > self.max_protected_regressions:
            metrics["gate_level"] = "reject"
            return SQLAwareGateDecision(False, f"protected_regression_total={len(protected_regressions)}", metrics)
        if self.require_target_improvement and target_categories and not target_improved:
            metrics["gate_level"] = "reject"
            return SQLAwareGateDecision(False, "target_category_not_improved", metrics)
        if scorecard["total"] < self.min_score:
            metrics["gate_level"] = "reject"
            return SQLAwareGateDecision(False, f"sql_score_below_threshold={scorecard['total']}", metrics)
        if not regressions:
            metrics["gate_level"] = "strong_pass"
            return SQLAwareGateDecision(True, f"strong_pass_score={scorecard['total']}_delta={delta:.4f}", metrics)
        metrics["gate_level"] = "weak_pass"
        if len(regressions) > self.max_regressions:
            return SQLAwareGateDecision(True, f"skillopt_pass_with_regressions={len(regressions)}_delta={delta:.4f}", metrics)
        return SQLAwareGateDecision(True, f"skillopt_pass_score={scorecard['total']}_delta={delta:.4f}", metrics)


def _accuracy(rows: list[dict[str, Any]]) -> float:
    return sum(bool(row.get("correct")) for row in rows) / len(rows) if rows else 0.0


def _regressions(before_rows: list[dict[str, Any]], after_rows: list[dict[str, Any]]) -> list[str]:
    return [
        str(after["id"])
        for before, after in zip(before_rows, after_rows)
        if before.get("correct") and not after.get("correct")
    ]


def _target_counts(rows: list[dict[str, Any]], target_categories: list[str]) -> dict[str, int]:
    counts = Counter(row.get("category") for row in rows if not row.get("correct"))
    return {category: counts.get(category, 0) for category in target_categories}


def _patch_quality(patch_metadata: list[dict[str, Any]], max_words: int) -> dict[str, Any]:
    patch_text = "\n".join(str(row.get("patch_text") or "") for row in patch_metadata)
    lowered = patch_text.lower()
    word_count = len(patch_text.split())
    evidence_terms = _evidence_terms(patch_metadata)
    covered_terms = [term for term in evidence_terms if term in lowered]
    suspicious_terms = [
        token
        for token in ["chinook_", "bird_", "spider_", "db_id", "example_id"]
        if token in lowered
    ]
    return {
        "word_count": word_count,
        "length_ok": word_count <= max_words * max(len(patch_metadata), 1),
        "evidence_terms": evidence_terms,
        "covered_evidence_terms": covered_terms,
        "covers_evidence": not evidence_terms or bool(covered_terms),
        "not_specific_to_dataset": not suspicious_terms,
        "specificity_flags": suspicious_terms,
    }


def _evidence_terms(patch_metadata: list[dict[str, Any]]) -> list[str]:
    terms = set()
    for row in patch_metadata:
        category = str(row.get("category") or "").lower()
        text = " ".join(str(item) for item in row.get("detector_evidence", []))
        text += " " + " ".join(str(item) for item in row.get("contrastive_signals", []))
        text = text.lower()
        if category == "ordering_limit" or "limit" in text or "order by" in text:
            terms.update(["limit", "order"])
        if category == "aggregation" or "group by" in text:
            terms.update(["group", "aggregate"])
        if category == "ratio_numeric" or "ratio" in text or "division" in text:
            terms.update(["ratio", "cast"])
        if category == "value_grounding" or "literal" in text:
            terms.update(["value"])
        if category == "join_path" or "join" in text:
            terms.update(["join"])
    return sorted(terms)


def _scorecard(
    *,
    regressions: list[str],
    improvements: list[str],
    target_categories: list[str],
    before_counts: dict[str, int],
    after_counts: dict[str, int],
    target_improved: bool,
    quality: dict[str, Any],
) -> dict[str, Any]:
    items: dict[str, int] = {}
    items["regression_control"] = 2 if not regressions else 1
    if target_categories and any(before_counts.get(cat, 0) > 0 for cat in target_categories):
        items["target_category_improvement"] = 2 if target_improved else 0
    else:
        items["target_category_improvement"] = 1
    items["improvement_signal"] = 1 if improvements else 0
    items["patch_covers_evidence"] = 1 if quality["covers_evidence"] else 0
    items["patch_general"] = 1 if quality["not_specific_to_dataset"] else 0
    items["patch_length"] = 1 if quality["length_ok"] else 0
    return {"items": items, "total": sum(items.values())}
