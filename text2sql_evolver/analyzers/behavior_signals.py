from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from text2sql_evolver.core.state import ExampleRun
from text2sql_evolver.failure_store import FailureStore


@dataclass(frozen=True)
class BehaviorSignal:
    example_id: str
    outcome: str
    signal_type: str
    category: str
    severity: str
    weight: float
    evidence: str
    skill_fixable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "example_id": self.example_id,
            "outcome": self.outcome,
            "signal_type": self.signal_type,
            "category": self.category,
            "severity": self.severity,
            "weight": self.weight,
            "evidence": self.evidence,
            "skill_fixable": self.skill_fixable,
        }


@dataclass(frozen=True)
class TrajectoryCard:
    example_id: str
    outcome: str
    category: str
    signal_type: str
    weight: float
    evidence: str
    question: str
    relevant_sql_diff: dict[str, str]
    execution_signal: str
    bird_evidence: str | None
    tool_trace: dict[str, Any]
    fix_route: str
    route_confidence: float
    route_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "example_id": self.example_id,
            "outcome": self.outcome,
            "category": self.category,
            "signal_type": self.signal_type,
            "weight": self.weight,
            "evidence": self.evidence,
            "question": self.question,
            "relevant_sql_diff": self.relevant_sql_diff,
            "execution_signal": self.execution_signal,
            "bird_evidence": self.bird_evidence,
            "tool_trace": self.tool_trace,
            "fix_route": self.fix_route,
            "route_confidence": self.route_confidence,
            "route_reason": self.route_reason,
        }


def annotate_behavior_signals(runs: list[ExampleRun]) -> list[dict[str, Any]]:
    signals: list[BehaviorSignal] = []
    for run in runs:
        if not run.correct and run.analysis is not None:
            signals.append(
                BehaviorSignal(
                    example_id=str(run.example.id),
                    outcome="failed",
                    signal_type="hard_failure",
                    category=run.analysis.category,
                    severity="high",
                    weight=1.0,
                    evidence=run.analysis.evidence,
                    skill_fixable=True,
                )
            )
            continue

        risky = _risky_success_signals(run)
        signals.extend(risky)
        if not risky and run.correct:
            signals.append(
                BehaviorSignal(
                    example_id=str(run.example.id),
                    outcome="success",
                    signal_type="clean_success",
                    category="clean_success",
                    severity="low",
                    weight=0.0,
                    evidence="SQL executed correctly with no rule-based risk signal.",
                    skill_fixable=False,
                )
            )
    return [signal.to_dict() for signal in signals]


def build_trajectory_cards(runs: list[ExampleRun], behavior_signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs_by_id = {str(run.example.id): run for run in runs}
    cards = []
    for signal in behavior_signals:
        run = runs_by_id.get(str(signal.get("example_id")))
        if run is None:
            continue
        category = str(signal.get("category") or "unknown")
        route, confidence, reason = _minimal_fix_route(run, category)
        cards.append(
            TrajectoryCard(
                example_id=str(run.example.id),
                outcome=str(signal.get("outcome") or ("success" if run.correct else "failed")),
                category=category,
                signal_type=str(signal.get("signal_type") or "unknown"),
                weight=float(signal.get("weight") or 0.0),
                evidence=str(signal.get("evidence") or ""),
                question=run.example.question,
                relevant_sql_diff=_relevant_sql_diff(category, run.predicted_sql, run.example.gold_sql),
                execution_signal=run.judge.reason,
                bird_evidence=run.example.evidence,
                tool_trace={"value_lookup_performed": False, "lookup_result": None},
                fix_route=route,
                route_confidence=confidence,
                route_reason=reason,
            ).to_dict()
        )
    return cards


def apply_route_diagnosis(
    trajectory_cards: list[dict[str, Any]],
    route_diagnosis: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not route_diagnosis:
        return trajectory_cards
    by_category = {
        str(row.get("category")): row
        for row in route_diagnosis.get("category_routes", [])
        if isinstance(row, dict) and row.get("category")
    }
    routed = []
    for card in trajectory_cards:
        row = dict(card)
        if row.get("fix_route") == "llm_review_required":
            diagnosis = by_category.get(str(row.get("category")))
            if diagnosis:
                row["fix_route"] = str(diagnosis.get("fix_route") or "uncertain")
                row["route_confidence"] = float(diagnosis.get("confidence") or 0.5)
                row["route_reason"] = str(diagnosis.get("reason") or "Route assigned by optimizer LLM.")
            else:
                row["fix_route"] = "uncertain"
                row["route_confidence"] = 0.5
                row["route_reason"] = "No optimizer route was returned for this category."
        routed.append(row)
    return routed


def filter_store_by_weighted_support(
    store: FailureStore,
    trajectory_cards: list[dict[str, Any]],
    *,
    min_weighted_support: float = 2.0,
    min_support_ratio: float = 0.25,
) -> tuple[FailureStore, dict[str, Any]]:
    totals: dict[tuple[str, str], float] = defaultdict(float)
    examples: dict[tuple[str, str], list[str]] = defaultdict(list)
    total_weight = 0.0
    for card in trajectory_cards:
        weight = float(card.get("weight") or 0.0)
        if weight <= 0:
            continue
        category = str(card.get("category") or "unknown")
        fix_route = str(card.get("fix_route") or "uncertain")
        key = (category, fix_route)
        totals[key] += weight
        total_weight += weight
        example_id = str(card.get("example_id") or "")
        if example_id and example_id not in examples[key]:
            examples[key].append(example_id)

    eligible = {
        category: weight
        for (category, fix_route), weight in totals.items()
        if fix_route == "query_skill"
        and (weight >= min_weighted_support or (total_weight > 0 and weight / total_weight >= min_support_ratio))
    }
    dominant_category = None
    if eligible:
        category_priority = {
            "projection": 0,
            "aggregation_projection": 1,
            "ordering_limit": 2,
            "ratio_numeric": 3,
            "aggregation": 4,
        }
        dominant_category = sorted(
            eligible.items(),
            key=lambda item: (-item[1], category_priority.get(item[0], 99), item[0]),
        )[0][0]
    supported = {dominant_category} if dominant_category else set()

    filtered = FailureStore()
    excluded = []
    for row in store.rows:
        if row.get("category") in supported:
            filtered.add(row)
        else:
            excluded.append(row.get("id"))

    report = {
        "min_weighted_support": min_weighted_support,
        "min_support_ratio": min_support_ratio,
        "total_weight": round(total_weight, 4),
        "route_weighted_support": {
            f"{category}+{fix_route}": round(weight, 4)
            for (category, fix_route), weight in sorted(totals.items())
        },
        "route_support_ratio": {
            f"{category}+{fix_route}": round(weight / total_weight, 4) if total_weight else 0.0
            for (category, fix_route), weight in sorted(totals.items())
        },
        "support_examples": {
            f"{category}+{fix_route}": ids
            for (category, fix_route), ids in sorted(examples.items())
        },
        "supported_categories": sorted(supported),
        "dominant_category": dominant_category,
        "eligible_categories": {category: round(weight, 4) for category, weight in sorted(eligible.items())},
        "excluded_failure_ids": excluded,
    }
    return filtered, report


def summarize_trajectory_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        if float(card.get("weight") or 0.0) <= 0:
            continue
        grouped[(str(card.get("category") or "unknown"), str(card.get("fix_route") or "uncertain"))].append(card)
    summaries = []
    for (category, fix_route), rows in sorted(grouped.items()):
        support = sum(float(row.get("weight") or 0.0) for row in rows)
        summaries.append(
            {
                "category": category,
                "fix_route": fix_route,
                "weighted_support": round(support, 4),
                "support_examples": [row.get("example_id") for row in rows[:8]],
                "common_evidence": _dedupe(str(row.get("evidence") or "") for row in rows)[:8],
                "representative_cards": rows[:5],
            }
        )
    return summaries


def _risky_success_signals(run: ExampleRun) -> list[BehaviorSignal]:
    sql = run.predicted_sql or ""
    question = run.example.question or ""
    signals: list[BehaviorSignal] = []
    if re.search(r"\bSELECT\s+\*", sql, re.IGNORECASE):
        signals.append(
            BehaviorSignal(
                example_id=str(run.example.id),
                outcome="success",
                signal_type="risky_success",
                category="projection",
                severity="medium",
                weight=0.4,
                evidence="Correct SQL used SELECT *, which is brittle for Text-to-SQL projection.",
                skill_fixable=True,
            )
        )
    if _ranking_question(question) and _has_order_by(sql) and not _has_limit(sql):
        signals.append(
            BehaviorSignal(
                example_id=str(run.example.id),
                outcome="success",
                signal_type="risky_success",
                category="ordering_limit",
                severity="medium",
                weight=0.4,
                evidence="Correct ranking SQL used ORDER BY without LIMIT.",
                skill_fixable=True,
            )
        )
    gold_len = max(len(run.example.gold_sql.split()), 1)
    pred_len = len(sql.split())
    if pred_len > gold_len * 2.5 and pred_len > 80:
        signals.append(
            BehaviorSignal(
                example_id=str(run.example.id),
                outcome="success",
                signal_type="overlong_success",
                category="semantic_mismatch",
                severity="low",
                weight=0.25,
                evidence=f"Correct SQL is much longer than gold SQL: predicted_words={pred_len}, gold_words={gold_len}.",
                skill_fixable=True,
            )
        )
    return signals


def _ranking_question(question: str) -> bool:
    return bool(re.search(r"\b(highest|lowest|top|bottom|most|least|first|last)\b", question, re.IGNORECASE))


def _has_order_by(sql: str) -> bool:
    return bool(re.search(r"\bORDER\s+BY\b", sql, re.IGNORECASE))


def _has_limit(sql: str) -> bool:
    return bool(re.search(r"\bLIMIT\b", sql, re.IGNORECASE))


def _minimal_fix_route(run: ExampleRun, category: str) -> tuple[str, float, str]:
    if run.correct:
        if category == "clean_success":
            return "contrast_only", 0.95, "Clean success is useful as contrast, not as an update trigger."
        return "llm_review_required", 0.5, "Risky success route should be judged by optimizer LLM."

    reason = run.judge.reason.lower()
    if reason.startswith("gold_sql_failed"):
        return "benchmark_noise", 0.95, "Gold SQL failed, so this trace should not drive skill updates."
    if "database" in reason and "not found" in reason:
        return "environment", 0.95, "Database/environment issue should not drive skill updates."
    return "llm_review_required", 0.5, "Fix route should be judged by optimizer LLM from the compressed trajectory card."


def _relevant_sql_diff(category: str, predicted_sql: str, gold_sql: str) -> dict[str, str]:
    if category == "value_grounding":
        return {
            "predicted_literals": ", ".join(_literals(predicted_sql)),
            "gold_literals": ", ".join(_literals(gold_sql)),
            "predicted_where": _clause(predicted_sql, "where"),
            "gold_where": _clause(gold_sql, "where"),
        }
    if category == "ratio_numeric":
        return {"predicted_select": _select_clause(predicted_sql), "gold_select": _select_clause(gold_sql)}
    if category == "ordering_limit":
        return {
            "predicted_order_limit": _order_limit(predicted_sql),
            "gold_order_limit": _order_limit(gold_sql),
        }
    if category in {"schema_linking", "join_path"}:
        return {"predicted_from_join": _from_join(predicted_sql), "gold_from_join": _from_join(gold_sql)}
    if category == "aggregation":
        return {
            "predicted_select_group": f"{_select_clause(predicted_sql)} {_clause(predicted_sql, 'group by')}",
            "gold_select_group": f"{_select_clause(gold_sql)} {_clause(gold_sql, 'group by')}",
        }
    if category == "projection":
        return {"predicted_select": _select_clause(predicted_sql), "gold_select": _select_clause(gold_sql)}
    return {"predicted_sql_snippet": predicted_sql[:500], "gold_sql_snippet": gold_sql[:500]}


def _literals(sql: str) -> list[str]:
    return re.findall(r"'([^']+)'", sql or "")


def _select_clause(sql: str) -> str:
    match = re.search(r"\bSELECT\b(.*?)\bFROM\b", sql or "", re.IGNORECASE | re.DOTALL)
    return _compact(match.group(1)) if match else ""


def _clause(sql: str, clause: str) -> str:
    next_clause = r"\b(GROUP\s+BY|ORDER\s+BY|LIMIT|HAVING|UNION|EXCEPT|INTERSECT)\b"
    if clause.lower() == "group by":
        next_clause = r"\b(ORDER\s+BY|LIMIT|HAVING|UNION|EXCEPT|INTERSECT)\b"
    pattern = r"\b" + re.escape(clause).replace("\\ ", r"\s+") + r"\b(.*?)(?:" + next_clause + r"|$)"
    match = re.search(pattern, sql or "", re.IGNORECASE | re.DOTALL)
    return _compact(match.group(1)) if match else ""


def _order_limit(sql: str) -> str:
    order = _clause(sql, "order by")
    limit_match = re.search(r"\bLIMIT\b(.*?)(?:;|$)", sql or "", re.IGNORECASE | re.DOTALL)
    limit = _compact(limit_match.group(1)) if limit_match else ""
    return " ".join(part for part in [f"ORDER BY {order}" if order else "", f"LIMIT {limit}" if limit else ""] if part)


def _from_join(sql: str) -> str:
    match = re.search(r"\bFROM\b(.*?)(?:\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|;|$)", sql or "", re.IGNORECASE | re.DOTALL)
    return _compact(match.group(1)) if match else ""


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:500]


def _dedupe(values) -> list[str]:
    seen = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen
