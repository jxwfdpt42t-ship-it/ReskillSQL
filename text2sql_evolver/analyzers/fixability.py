from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from text2sql_evolver.config import Settings
from text2sql_evolver.llm import complete_text


FIXABLE_CATEGORIES = {
    "aggregation",
    "filtering",
    "ordering_limit",
    "projection",
    "ratio_numeric",
    "result_shape",
    "semantic_mismatch",
    "syntax_or_runtime",
}

CONDITIONAL_CATEGORIES = {
    "join_path",
    "schema_linking",
    "value_grounding",
}


@dataclass(frozen=True)
class FixabilityDecision:
    fixability: str
    query_skill_fixable: bool
    confidence: float
    reason: str
    sql_error_type: str = "unknown"
    reviewed_by_llm: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixability": self.fixability,
            "query_skill_fixable": self.query_skill_fixable,
            "confidence": self.confidence,
            "reason": self.reason,
            "sql_error_type": self.sql_error_type,
            "reviewed_by_llm": self.reviewed_by_llm,
        }


class QuerySkillFixabilityFilter:
    """Route failures into or away from query-writing skill evolution."""

    def __init__(self, settings: Settings | None = None, review_uncertain_with_llm: bool = True) -> None:
        self.settings = settings
        self.review_uncertain_with_llm = review_uncertain_with_llm

    def decide(self, failure: dict[str, Any]) -> FixabilityDecision:
        rule_decision = self._rule_decide(failure)
        if (
            rule_decision.fixability == "uncertain"
            and self.review_uncertain_with_llm
            and self.settings is not None
        ):
            return self._review_uncertain_with_llm(failure, rule_decision)
        return rule_decision

    def _rule_decide(self, failure: dict[str, Any]) -> FixabilityDecision:
        category = str(failure.get("category") or "")
        reason = str(failure.get("judge_reason") or "").lower()
        details = failure.get("details") or {}

        if reason.startswith("gold_sql_failed"):
            return FixabilityDecision(
                "not_fixable",
                False,
                0.95,
                "Gold SQL failed to execute, so updating query-writing skill would learn from noisy supervision.",
                "not_applicable",
            )
        if "only read-only" in reason or "database" in reason and "not found" in reason:
            return FixabilityDecision(
                "not_fixable",
                False,
                0.9,
                "The failure is an execution or environment issue, not a reusable SQL-writing behavior.",
                "not_applicable",
            )

        if category in FIXABLE_CATEGORIES:
            return FixabilityDecision(
                "fixable",
                True,
                0.85,
                f"{category} is a reusable SQL-writing behavior that can be taught in query-writing skill.",
                category,
            )

        if category == "join_path":
            if details.get("predicted_tables") and details.get("gold_tables"):
                return FixabilityDecision(
                    "fixable",
                    True,
                    0.75,
                    "Join/table evidence is available, so query-writing skill can teach explicit join-path tracing.",
                    category,
                )
            return FixabilityDecision(
                "uncertain",
                False,
                0.45,
                "Join failure may require better schema context or foreign-key retrieval.",
                category,
            )

        if category == "schema_linking":
            if "no such table" in reason or "no such column" in reason:
                return FixabilityDecision(
                    "fixable",
                    True,
                    0.7,
                    "The predicted SQL referenced invalid schema items; query-writing skill can emphasize schema-grounded names.",
                    category,
                )
            return FixabilityDecision(
                "uncertain",
                False,
                0.45,
                "Schema mismatch may be caused by missing schema context rather than query-writing behavior.",
                category,
            )

        if category == "value_grounding":
            if details.get("evidence_usage_warning") or details.get("value_grounding_warning"):
                return FixabilityDecision(
                    "fixable",
                    True,
                    0.75,
                    "Value evidence is available in the trace, so query-writing skill can teach literal grounding and evidence usage.",
                    category,
                )
            return FixabilityDecision(
                "uncertain",
                False,
                0.5,
                "Value grounding may require a database value lookup tool, not only a writing skill rule.",
                category,
            )

        if category in CONDITIONAL_CATEGORIES:
            return FixabilityDecision(
                "uncertain",
                False,
                0.5,
                f"{category} may be skill-fixable, but this trace lacks enough evidence for a safe skill update.",
                category,
            )

        return FixabilityDecision(
            "uncertain",
            False,
            0.35,
            "The failure is outside the currently supported query-skill-fixable categories.",
            "unknown",
        )

    def _review_uncertain_with_llm(
        self,
        failure: dict[str, Any],
        rule_decision: FixabilityDecision,
    ) -> FixabilityDecision:
        user = f"""You are a Text-to-SQL skill evolution reviewer.

Your task is NOT to fix the current SQL and NOT to write a skill patch.
Your task is to decide whether this failure should be used to update the query-writing skill.

Known SQL error types:
- schema_linking
- join_path
- filtering
- aggregation
- projection
- result_shape
- ordering_limit
- ratio_numeric
- value_grounding
- evidence_usage
- syntax_or_runtime
- semantic_mismatch
- other_sql_error
- unknown

Decision rules:
1. Use query_skill_fixable=true only when the failure is a reusable SQL writing/reasoning behavior that a query-writing skill could improve.
2. Use query_skill_fixable=false when the issue is gold SQL noise, missing database/schema context, missing tool support, judge/runtime/API problem, or clearly outside query-writing behavior.
3. Use query_skill_fixable="uncertain" when evidence is insufficient.
4. If the failure is SQL-related but not covered by known categories, use sql_error_type="other_sql_error".
5. Do not mention concrete table names or example IDs in the reason.

Failure:
{json.dumps(failure, indent=2, ensure_ascii=False)}

Rule-based initial decision:
{json.dumps(rule_decision.to_dict(), indent=2, ensure_ascii=False)}

Return JSON only:
{{
  "query_skill_fixable": true | false | "uncertain",
  "sql_error_type": "schema_linking | join_path | filtering | aggregation | projection | result_shape | ordering_limit | ratio_numeric | value_grounding | evidence_usage | syntax_or_runtime | semantic_mismatch | other_sql_error | unknown | not_applicable",
  "reason": "one concise sentence",
  "confidence": 0.0
}}
"""
        try:
            text = complete_text(
                self.settings,
                "You review Text-to-SQL failures for skill evolution. Return JSON only.",
                user,
                max_tokens=500,
            )
            payload = _extract_json_object(text)
        except Exception:
            return rule_decision

        raw_fixable = payload.get("query_skill_fixable", "uncertain")
        if raw_fixable is True or str(raw_fixable).lower() == "true":
            fixability = "fixable"
            query_skill_fixable = True
        elif raw_fixable is False or str(raw_fixable).lower() == "false":
            fixability = "not_fixable"
            query_skill_fixable = False
        else:
            fixability = "uncertain"
            query_skill_fixable = False

        confidence = _float_between_zero_and_one(payload.get("confidence"), rule_decision.confidence)
        reason = str(payload.get("reason") or rule_decision.reason).strip()
        sql_error_type = str(payload.get("sql_error_type") or rule_decision.sql_error_type).strip()
        return FixabilityDecision(
            fixability=fixability,
            query_skill_fixable=query_skill_fixable,
            confidence=confidence,
            reason=reason,
            sql_error_type=sql_error_type,
            reviewed_by_llm=True,
        )


def _extract_json_object(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _float_between_zero_and_one(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(0.0, min(1.0, number))
