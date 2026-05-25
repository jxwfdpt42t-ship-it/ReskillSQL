from __future__ import annotations

from datetime import datetime
import json
import re
from pathlib import Path
from typing import Any

from .config import Settings
from .failure_store import FailureStore
from .llm import complete_text
from .editors.patch_aggregator import PatchBundle, SQLAwarePatchAggregator


RULES_BY_CATEGORY = {
    "schema_linking": "Before writing SQL, identify the exact table and column names from schema text; never invent pluralized or lowercase table names.",
    "join_path": "For multi-hop questions, explicitly trace the foreign-key path before writing JOINs, then include every needed ON condition.",
    "aggregation": "For totals, counts, averages, and rankings, choose the aggregate first and GROUP BY every non-aggregate selected column.",
    "filtering": "Translate entity, date, country, genre, and employee constraints into WHERE predicates before aggregation.",
    "ordering_limit": "For top/bottom/highest/lowest/latest questions, include ORDER BY with the correct direction, add LIMIT for requested ranks, and add a stable secondary tie-breaker such as name/title ascending when results can tie.",
    "projection": "Select the entity requested by the question, not only an ID or intermediate join key.",
    "aggregation_projection": "Before writing SELECT, decide the exact requested output columns separately from helper columns used for aggregation, sorting, or filtering; do not output helper aggregates unless the question asks for them.",
    "result_shape": "Before finalizing SQL, verify the result shape implied by the question: single-row ranking questions need LIMIT 1, top-k questions need k rows, and projection should match requested columns.",
    "ratio_numeric": "For rate, ratio, percentage, and per-unit questions, derive the numerator and denominator from the question/evidence, use REAL arithmetic or CAST, guard denominators with NULLIF when appropriate, and order by the computed metric for highest/lowest questions.",
    "value_grounding": "Before using literal values from the question, inspect representative database values and normalize entity wording to the stored form.",
    "syntax_or_runtime": "Prefer simple SQLite-compatible syntax and validate that every referenced alias is introduced in FROM or JOIN.",
    "semantic_mismatch": "Re-read the question after drafting SQL and verify that selected columns, filters, grouping, and ordering answer the requested intent.",
}


def generate_llm_patch_bundle(
    settings: Settings,
    store: FailureStore,
    *,
    evidence_packet: dict[str, Any] | None = None,
) -> PatchBundle:
    grouped = store.grouped_examples()
    packet_text = json.dumps(evidence_packet or {}, indent=2, ensure_ascii=False)
    user = f"""You maintain a Text-to-SQL query-writing skill.
Given these validation failures and evidence packet, write one strong reusable workflow patch.

Rules:
- Do not mention specific example IDs unless necessary.
- Write reusable SQL behavior rules, not one-off fixes.
- Keep it to the single most important supported category.
- Focus on schema linking, joins, filters, aggregation, ordering, projection, and SQLite compatibility.
- Prefer concrete rules grounded by detector evidence.
- Prioritize categories listed in weighted_support.supported_categories.
- Write patches only for categories whose trajectory cards and category summaries have fix_route="query_skill".
- Do not write query-writing skill patches for value_lookup_tool, schema_context, inner_repair, benchmark_noise, or uncertain routes.
- Use behavior_signals to distinguish hard failures from risky or overlong successes.
- Avoid generic advice such as "write SQLite-compatible SQL" unless the evidence is specifically about SQLite syntax.
- The patch must describe a concrete SQL writing action that could change future generated SQL.
- Make the patch operational: name the wrong behavior, name the replacement behavior, and provide a mandatory_pre_sql_plan.
- mandatory_pre_sql_plan.steps must contain exactly 4 imperative steps.
- Each mandatory_pre_sql_plan step must be directly executable before drafting SQL.
- The mandatory_pre_sql_plan is the text that will be inserted into the query-writing skill for the inner LLM to execute.
- Do not write vague advice such as "be careful", "verify correctness", "understand the question", or "use proper SQL".
- Do not say "compare with gold SQL" because the target agent will not have gold SQL at inference time.
- Avoid repeating rejected patch directions.
- Do not write rules for failures marked non-fixable or uncertain.
- Do not return markdown.
- Return JSON only.

Fixable failures:
{grouped}

Evidence packet:
{packet_text}

Return exactly this JSON shape:
{{
  "candidate_patches": [
    {{
      "patch_id": "ordering_limit_candidate_001",
      "category": "ordering_limit",
      "wrong_behavior": "The draft SQL outputs helper ranking columns or omits the requested LIMIT/ORDER BY behavior.",
      "replacement_behavior": "Use helper expressions only inside ORDER BY/GROUP BY/subqueries and project only the requested answer columns with explicit ORDER BY direction and LIMIT.",
      "rule_text": "For ranking questions, first determine the requested answer columns and rank/count, then use ORDER BY/LIMIT to select the rows while keeping helper ranking expressions out of SELECT unless explicitly requested.",
      "mandatory_pre_sql_plan": {{
        "title": "Ranking Projection Check",
        "steps": [
          "Set answer_columns to the exact columns or expressions requested by the question.",
          "Set helper_expressions to ranking, aggregate, or sorting expressions needed only to choose rows.",
          "Set outer_select to answer_columns only, unless the question explicitly asks to show a helper expression.",
          "Set ordering_limit_check to the ORDER BY direction and LIMIT required by the ranking phrase."
        ]
      }},
      "support_examples": ["example_id"],
      "detector_evidence": ["ORDER BY, tie-breaker, or LIMIT mismatch"],
      "contrastive_signals": ["failed SQL ranking clause differs from gold ORDER BY / tie-breaker / LIMIT"]
    }}
  ]
}}
"""
    text = complete_text(
        settings,
        "You improve modular Text-to-SQL skills from validation evidence. Return JSON only.",
        user,
        max_tokens=1800,
    )
    try:
        candidate_patches = _parse_candidate_patches(text)
    except (json.JSONDecodeError, ValueError):
        repaired_text = _repair_patch_json(settings, text)
        candidate_patches = _parse_candidate_patches(repaired_text)
    candidate_patches = _ground_candidate_patches(candidate_patches, evidence_packet or {})
    quality_issues = _candidate_patch_quality_issues(candidate_patches)
    if quality_issues:
        rewritten_text = _rewrite_low_quality_patches(settings, user, text, quality_issues)
        try:
            candidate_patches = _parse_candidate_patches(rewritten_text)
        except (json.JSONDecodeError, ValueError):
            repaired_rewrite = _repair_patch_json(settings, rewritten_text)
            candidate_patches = _parse_candidate_patches(repaired_rewrite)
        candidate_patches = _ground_candidate_patches(candidate_patches, evidence_packet or {})
        quality_issues = _candidate_patch_quality_issues(candidate_patches)
        if quality_issues:
            raise ValueError(f"Optimizer LLM returned low-quality candidate patches: {quality_issues}")
    return SQLAwarePatchAggregator().build_bundle(candidate_patches)


def generate_llm_skill_patch(
    settings: Settings,
    store: FailureStore,
    *,
    evidence_packet: dict[str, Any] | None = None,
) -> str:
    return generate_llm_patch_bundle(settings, store, evidence_packet=evidence_packet).markdown


def diagnose_fix_routes(
    settings: Settings,
    *,
    trajectory_cards: list[dict[str, Any]],
    category_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    cards = [card for card in trajectory_cards if card.get("fix_route") == "llm_review_required"]
    if not cards:
        return {"category_routes": []}
    target_categories = sorted({str(card.get("category") or "unknown") for card in cards})
    user = f"""You are the optimizer LLM for a Text-to-SQL skill evolution system.
Decide which mechanism should fix each SQL behavior category.

Route options:
- query_skill: The query-writing skill has enough information to teach a reusable writing/reasoning step.
- value_lookup_tool: The issue requires observing actual stored database values or value candidates.
- schema_context: The issue requires better schema/table/column context.
- inner_repair: The issue is mainly a malformed/truncated attempt that should be retried or repaired for the current query.
- benchmark_noise: The supervision or benchmark trace is unreliable.
- uncertain: The route cannot be determined from the compressed evidence.

Important:
- Do not fit to gold answers. Judge whether the query-writing skill has enough visible information to fix the behavior.
- Prefer query_skill for reusable clause reasoning, evidence usage, ratio formulas, aggregation, ordering, projection, and explicit evidence mappings.
- Prefer value_lookup_tool when the key missing information is the stored spelling/casing/format of a value not visible in evidence.
- Prefer schema_context when the key missing information is table/column/schema relationship context.
- Return exactly one route for every category in target_categories.
- If the evidence is insufficient for a category, route it to uncertain instead of omitting it.

target_categories:
{json.dumps(target_categories, indent=2, ensure_ascii=False)}

Compressed trajectory cards:
{json.dumps(cards[:40], indent=2, ensure_ascii=False)}

Category summaries:
{json.dumps(category_summaries, indent=2, ensure_ascii=False)}

Return JSON only:
{{
  "category_routes": [
    {{
      "category": "value_grounding",
      "fix_route": "query_skill | value_lookup_tool | schema_context | inner_repair | benchmark_noise | uncertain",
      "confidence": 0.0,
      "reason": "one concise sentence"
    }}
  ]
}}
"""
    text = complete_text(
        settings,
        "You diagnose Text-to-SQL fix routes from compressed trajectory evidence. Return JSON only.",
        user,
        max_tokens=1200,
    )
    try:
        diagnosis = _parse_route_diagnosis(text)
    except (json.JSONDecodeError, ValueError):
        repaired = _repair_route_json(settings, text)
        diagnosis = _parse_route_diagnosis(repaired)
    missing = _missing_route_categories(target_categories, diagnosis)
    if missing:
        followup = _diagnose_missing_route_categories(
            settings,
            missing,
            trajectory_cards=cards,
            category_summaries=category_summaries,
        )
        diagnosis = _merge_route_diagnoses(diagnosis, followup)
    return _ensure_all_route_categories(target_categories, diagnosis)


def _parse_candidate_patches(text: str) -> list[dict[str, Any]]:
    payload = _extract_json_object(text)
    raw_patches = payload.get("candidate_patches", []) if isinstance(payload, dict) else []
    if not raw_patches and isinstance(payload, dict):
        raw_patches = payload.get("rules", [])
    candidate_patches = []
    for idx, item in enumerate(raw_patches, 1):
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "semantic_mismatch").strip()
        rule_text = str(item.get("rule_text") or item.get("rule") or "").strip()
        if not rule_text:
            continue
        detector_evidence = item.get("detector_evidence", item.get("evidence", []))
        candidate_patches.append(
            {
                "patch_id": str(item.get("patch_id") or f"{category}_candidate_{idx:03d}"),
                "category": category,
                "wrong_behavior": str(item.get("wrong_behavior") or "").strip(),
                "replacement_behavior": str(item.get("replacement_behavior") or "").strip(),
                "rule_text": rule_text,
                "mandatory_pre_sql_plan": item.get("mandatory_pre_sql_plan", {}),
                "workflow_steps": item.get("workflow_steps", []),
                "support_examples": item.get("support_examples", []),
                "detector_evidence": detector_evidence if isinstance(detector_evidence, list) else [str(detector_evidence)],
                "contrastive_signals": item.get("contrastive_signals", []),
            }
        )
    if not candidate_patches:
        raise ValueError("Optimizer LLM did not return any usable candidate patches.")
    return candidate_patches


def _parse_route_diagnosis(text: str) -> dict[str, Any]:
    payload = _extract_json_object(text)
    routes = payload.get("category_routes", []) if isinstance(payload, dict) else []
    if not isinstance(routes, list):
        raise ValueError("Route diagnosis must contain category_routes list.")
    allowed = {"query_skill", "value_lookup_tool", "schema_context", "inner_repair", "benchmark_noise", "uncertain"}
    normalized = []
    for row in routes:
        if not isinstance(row, dict) or not row.get("category"):
            continue
        fix_route = str(row.get("fix_route") or "uncertain")
        if fix_route not in allowed:
            fix_route = "uncertain"
        normalized.append(
            {
                "category": str(row.get("category")),
                "fix_route": fix_route,
                "confidence": _float_between_zero_and_one(row.get("confidence"), 0.5),
                "reason": str(row.get("reason") or "Route assigned by optimizer LLM."),
            }
        )
    return {"category_routes": normalized}


def _missing_route_categories(categories: list[str], diagnosis: dict[str, Any]) -> list[str]:
    returned = {
        str(row.get("category"))
        for row in diagnosis.get("category_routes", [])
        if isinstance(row, dict) and row.get("category")
    }
    return [category for category in categories if category not in returned]


def _diagnose_missing_route_categories(
    settings: Settings,
    categories: list[str],
    *,
    trajectory_cards: list[dict[str, Any]],
    category_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    category_set = set(categories)
    cards = [card for card in trajectory_cards if str(card.get("category")) in category_set]
    summaries = [row for row in category_summaries if str(row.get("category")) in category_set]
    user = f"""You omitted some route diagnoses. Diagnose only these missing Text-to-SQL categories.

Route options: query_skill, value_lookup_tool, schema_context, inner_repair, benchmark_noise, uncertain.

Use query_skill only when a reusable query-writing rule can plausibly fix the behavior from visible question/evidence/schema context.
Use uncertain if the compressed evidence is insufficient.
Return exactly one route for every category below.

missing_categories:
{json.dumps(categories, indent=2, ensure_ascii=False)}

Compressed trajectory cards:
{json.dumps(cards[:30], indent=2, ensure_ascii=False)}

Category summaries:
{json.dumps(summaries, indent=2, ensure_ascii=False)}

Return JSON only:
{{
  "category_routes": [
    {{
      "category": "aggregation",
      "fix_route": "query_skill",
      "confidence": 0.8,
      "reason": "one concise sentence"
    }}
  ]
}}
"""
    text = complete_text(
        settings,
        "You diagnose missing Text-to-SQL fix routes. Return JSON only.",
        user,
        max_tokens=900,
    )
    try:
        return _parse_route_diagnosis(text)
    except (json.JSONDecodeError, ValueError):
        repaired = _repair_route_json(settings, text)
        return _parse_route_diagnosis(repaired)


def _merge_route_diagnoses(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    for source in (primary, secondary):
        for row in source.get("category_routes", []):
            if isinstance(row, dict) and row.get("category"):
                merged[str(row.get("category"))] = row
    return {"category_routes": list(merged.values())}


def _ensure_all_route_categories(categories: list[str], diagnosis: dict[str, Any]) -> dict[str, Any]:
    routes = diagnosis.get("category_routes", [])
    by_category = {
        str(row.get("category")): row
        for row in routes
        if isinstance(row, dict) and row.get("category")
    }
    completed = []
    for category in categories:
        if category in by_category:
            completed.append(by_category[category])
        else:
            completed.append(
                {
                    "category": category,
                    "fix_route": "uncertain",
                    "confidence": 0.5,
                    "reason": "Optimizer LLM did not return a route for this category.",
                }
            )
    return {"category_routes": completed}


def _repair_route_json(settings: Settings, raw_text: str) -> str:
    user = f"""Repair this malformed route diagnosis into valid JSON only.

Required shape:
{{
  "category_routes": [
    {{
      "category": "value_grounding",
      "fix_route": "query_skill",
      "confidence": 0.7,
      "reason": "one concise sentence"
    }}
  ]
}}

Malformed output:
{raw_text}
"""
    return complete_text(
        settings,
        "You repair malformed JSON. Return valid JSON only.",
        user,
        max_tokens=900,
    )


def _candidate_patch_quality_issues(candidate_patches: list[dict[str, Any]]) -> list[str]:
    issues = []
    incomplete_suffixes = {
        "a",
        "an",
        "and",
        "as",
        "by",
        "for",
        "from",
        "in",
        "of",
        "or",
        "the",
        "to",
        "with",
        "when",
    }
    for patch in candidate_patches:
        patch_id = str(patch.get("patch_id") or "unknown_patch")
        rule_text = str(patch.get("rule_text") or "").strip()
        words = re.findall(r"[A-Za-z0-9_]+", rule_text)
        last_word = words[-1].lower() if words else ""
        support_examples = patch.get("support_examples") or []
        detector_evidence = patch.get("detector_evidence") or []
        workflow_steps = patch.get("workflow_steps") or []
        mandatory_plan = patch.get("mandatory_pre_sql_plan") or {}
        mandatory_steps = mandatory_plan.get("steps", []) if isinstance(mandatory_plan, dict) else []
        if len(words) < 12:
            issues.append(f"{patch_id}: rule_text_too_short")
        if last_word in incomplete_suffixes:
            issues.append(f"{patch_id}: rule_text_looks_incomplete")
        if not support_examples and not detector_evidence:
            issues.append(f"{patch_id}: missing_support_and_evidence")
        if not isinstance(mandatory_steps, list) or len([step for step in mandatory_steps if str(step).strip()]) < 4:
            if not isinstance(workflow_steps, list) or len([step for step in workflow_steps if str(step).strip()]) < 3:
                issues.append(f"{patch_id}: mandatory_pre_sql_plan_too_weak")
    return issues


def _ground_candidate_patches(
    candidate_patches: list[dict[str, Any]],
    evidence_packet: dict[str, Any],
) -> list[dict[str, Any]]:
    metadata_by_category = {
        str(row.get("category")): row
        for row in evidence_packet.get("patch_metadata", [])
        if isinstance(row, dict) and row.get("category")
    }
    grounded = []
    for patch in candidate_patches:
        row = dict(patch)
        metadata = metadata_by_category.get(str(row.get("category")))
        if metadata:
            if not row.get("support_examples"):
                row["support_examples"] = metadata.get("support_examples", [])
            if not row.get("detector_evidence"):
                row["detector_evidence"] = metadata.get("detector_evidence", [])
            if not row.get("contrastive_signals"):
                row["contrastive_signals"] = metadata.get("contrastive_signals", [])
        row["rule_text"] = _complete_rule_text(str(row.get("category") or ""), str(row.get("rule_text") or ""))
        row["workflow_steps"] = _complete_workflow_steps(
            str(row.get("category") or ""),
            row.get("workflow_steps", []),
        )
        row["mandatory_pre_sql_plan"] = _complete_mandatory_pre_sql_plan(
            str(row.get("category") or ""),
            row.get("mandatory_pre_sql_plan", {}),
            row["workflow_steps"],
        )
        grounded.append(row)
    return grounded


def _complete_rule_text(category: str, rule_text: str) -> str:
    cleaned = rule_text.strip()
    words = re.findall(r"[A-Za-z0-9_]+", cleaned)
    if len(words) >= 18 and cleaned.endswith((".", "!", "?", ")")):
        return cleaned
    fallback = RULES_BY_CATEGORY.get(category)
    if fallback:
        return fallback
    if cleaned and not cleaned.endswith((".", "!", "?", ")")):
        return cleaned + "."
    return cleaned


def _complete_workflow_steps(category: str, workflow_steps: Any) -> list[str]:
    if isinstance(workflow_steps, list):
        cleaned = [str(step).strip() for step in workflow_steps if str(step).strip()]
        if len(cleaned) >= 2:
            return cleaned[:5]
    category_key = category.lower()
    if category_key in {"projection", "aggregation_projection", "result_shape"}:
        return [
            "Write down the exact columns requested by the question before writing SELECT.",
            "Keep helper columns used only for ORDER BY, GROUP BY, filters, or joins out of the final SELECT unless requested.",
            "If an aggregate is needed for ranking, use it in ORDER BY or a subquery but project only the requested answer.",
        ]
    if category_key == "ordering_limit":
        return [
            "Identify whether the question asks for top, bottom, highest, lowest, most, least, first, or latest.",
            "Use ORDER BY with an explicit direction and add LIMIT for the requested rank or count.",
            "Select only the requested answer columns, not the ranking score unless the question asks for it.",
        ]
    if category_key == "ratio_numeric":
        return [
            "Identify numerator, denominator, percentage multiplier, and filters from the question and evidence.",
            "Use REAL arithmetic or CAST for division.",
            "Project only the requested ratio, percentage, or entity associated with it.",
        ]
    return []


def _complete_mandatory_pre_sql_plan(category: str, plan: Any, workflow_steps: list[str]) -> dict[str, Any]:
    category_key = category.lower()
    if category_key in {"projection", "aggregation_projection", "result_shape"}:
        return {
            "title": "Projection Check",
            "steps": [
                "Set answer_columns to the entity, attribute, or metric explicitly requested after words like which, list, name, what, or how many.",
                "Set condition_columns to columns used only to filter or qualify the answer, such as labels, statuses, dates, categories, joins, or HAVING counts.",
                "Set outer_select to answer_columns only; do not include condition_columns or helper expressions unless the question explicitly asks to show them.",
                "For questions of the form 'Which/List X with condition Y', SELECT X only and keep Y only in WHERE, JOIN, GROUP BY, HAVING, ORDER BY, or subqueries.",
            ],
        }
    if isinstance(plan, dict):
        title = str(plan.get("title") or "").strip()
        steps = plan.get("steps", [])
        if title and isinstance(steps, list) and len([step for step in steps if str(step).strip()]) >= 4:
            return {"title": title, "steps": [str(step).strip() for step in steps if str(step).strip()][:4]}
    if category_key == "ordering_limit":
        return {
            "title": "Ranking And Limit Check",
            "steps": [
                "Set ranking_phrase to the top, bottom, highest, lowest, most, least, first, or latest phrase in the question.",
                "Set answer_columns to the requested entity or attributes, excluding helper ranking metrics unless requested.",
                "Set order_by_expression and order_direction from the ranking phrase and evidence.",
                "Set limit_value to the requested rank/count, using LIMIT 1 for single top/bottom questions.",
            ],
        }
    if category_key == "ratio_numeric":
        return {
            "title": "Ratio And Percentage Check",
            "steps": [
                "Set numerator to the count, sum, or filtered population requested by the question.",
                "Set denominator to the comparison or total population requested by the question.",
                "Set numeric_expression using REAL arithmetic or CAST for division.",
                "Set final_projection to the requested ratio, percentage, or entity associated with the metric.",
            ],
        }
    return {
        "title": f"{category} Check",
        "steps": workflow_steps[:4] if len(workflow_steps) >= 4 else workflow_steps,
    }


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


def _repair_patch_json(settings: Settings, raw_text: str) -> str:
    user = f"""The optimizer returned malformed JSON.
Repair it into valid JSON only. Preserve all usable candidate patch information.
If a field is missing, infer a concise safe value from the text.

Required shape:
{{
  "candidate_patches": [
    {{
      "patch_id": "category_candidate_001",
      "category": "ordering_limit",
      "rule_text": "Reusable Text-to-SQL rule.",
      "support_examples": [],
      "detector_evidence": [],
      "contrastive_signals": []
    }}
  ]
}}

Malformed output:
{raw_text}
"""
    return complete_text(
        settings,
        "You repair malformed JSON. Return valid JSON only.",
        user,
        max_tokens=1600,
    )


def _rewrite_low_quality_patches(
    settings: Settings,
    original_user_prompt: str,
    raw_text: str,
    quality_issues: list[str],
) -> str:
    user = f"""The optimizer patch JSON was syntactically valid but not usable.
Rewrite it using the original evidence. Return valid JSON only.

Quality problems:
{json.dumps(quality_issues, indent=2, ensure_ascii=False)}

Rules for the rewrite:
- Every rule_text must be a complete reusable Text-to-SQL instruction.
- Every patch must include at least one support_examples item or detector_evidence item.
- Prefer categories that are supported by the evidence packet.
- Do not invent example ids.
- Do not return markdown.

Previous low-quality output:
{raw_text}

Original task and evidence:
{original_user_prompt}
"""
    return complete_text(
        settings,
        "You rewrite low-quality Text-to-SQL skill patches into valid grounded JSON. Return JSON only.",
        user,
        max_tokens=2400,
    )


def apply_skill_patch(skill_path: Path, patch_text: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = skill_path.with_suffix(f".{timestamp}.bak")
    original = skill_path.read_text(encoding="utf-8")
    backup_path.write_text(original, encoding="utf-8")

    skill_path.write_text(render_skill_with_patch(original, patch_text), encoding="utf-8")
    return backup_path


def render_skill_with_patch(original: str, patch_text: str) -> str:
    cleaned = _strip_learned_sections(original)
    workflow = _render_learned_workflow(patch_text)
    if workflow:
        cleaned = _insert_learned_workflow(cleaned, workflow)
    return cleaned.rstrip() + "\n\n" + patch_text.strip() + "\n"


def _strip_learned_sections(text: str) -> str:
    learned_markers = [
        "\n## Mandatory Pre-SQL Plan\n",
        "\n## Learned Workflow Steps\n",
        "\n## Learned Rules From Validation Failures\n",
    ]
    cut = len(text)
    for marker in learned_markers:
        index = text.find(marker)
        if index != -1:
            cut = min(cut, index)
    return text[:cut].rstrip()


def _insert_learned_workflow(skill_text: str, workflow: str) -> str:
    marker = "\n## Quality Guidelines\n"
    if marker in skill_text:
        return skill_text.replace(marker, "\n" + workflow.strip() + "\n" + marker, 1)
    return skill_text.rstrip() + "\n\n" + workflow.strip()


def _render_learned_workflow(patch_text: str) -> str:
    rules = _extract_patch_rules(patch_text)
    if not rules:
        return ""
    lines = [
        "## Mandatory Pre-SQL Plan",
        "",
        "Before writing SQL, produce this internal plan and use it to draft the final query. This is mandatory, not an optional reminder.",
        "",
    ]
    for category, rule, workflow_steps, mandatory_plan in rules:
        if mandatory_plan:
            lines.extend(_mandatory_plan_lines(mandatory_plan, rule))
        else:
            lines.extend(_workflow_lines_for_rule(category, rule, workflow_steps))
    return "\n".join(lines).rstrip() + "\n"


def _extract_patch_rules(patch_text: str) -> list[tuple[str, str, list[str], dict[str, Any]]]:
    rules = []
    current: dict[str, Any] | None = None
    for line in patch_text.splitlines():
        match = re.match(r"- \*\*([^*]+)\*\*:\s*(.+)", line.strip())
        if match:
            current = {
                "category": match.group(1).strip(),
                "rule": match.group(2).strip(),
                "workflow_steps": [],
                "mandatory_plan": {},
            }
            rules.append(current)
            continue
        plan_match = re.match(r"- Mandatory plan:\s*(.+)", line.strip())
        if current and plan_match:
            current["mandatory_plan"] = {"title": plan_match.group(1).strip(), "steps": []}
            continue
        plan_step_match = re.match(r"\d+\.\s*(.+)", line.strip())
        if current and current.get("mandatory_plan") and plan_step_match:
            current["mandatory_plan"]["steps"].append(plan_step_match.group(1).strip())
            continue
        workflow_match = re.match(r"- Workflow \d+:\s*(.+)", line.strip())
        if current and workflow_match:
            current["workflow_steps"].append(workflow_match.group(1).strip())
    return [(row["category"], row["rule"], row["workflow_steps"], row["mandatory_plan"]) for row in rules]


def _mandatory_plan_lines(plan: dict[str, Any], rule: str) -> list[str]:
    title = str(plan.get("title") or "SQL Check").strip()
    steps = [str(step).strip() for step in plan.get("steps", []) if str(step).strip()]
    lines = [f"### {title}"]
    lines.extend(f"{index}. {step}" for index, step in enumerate(steps[:4], 1))
    lines.append(f"{len(steps[:4]) + 1}. Use this plan when applying the learned rule: {rule}")
    lines.append("")
    return lines


def _workflow_lines_for_rule(category: str, rule: str, workflow_steps: list[str] | None = None) -> list[str]:
    category_key = category.lower()
    if workflow_steps:
        title = {
            "projection": "Before Writing SELECT",
            "aggregation_projection": "Before Writing SELECT And Aggregates",
            "result_shape": "Before Finalizing Result Shape",
            "ordering_limit": "Before Finalizing Ranking Queries",
            "ratio_numeric": "Before Writing Numeric Expressions",
        }.get(category_key, f"Learned Step For {category}")
        lines = [f"### {title}"]
        lines.extend(f"{index}. {step}" for index, step in enumerate(workflow_steps[:5], 1))
        lines.append(f"{len(workflow_steps[:5]) + 1}. Learned rule: {rule}")
        lines.append("")
        return lines
    if category_key == "value_grounding":
        return [
            "### Before Writing WHERE Literals",
            "1. Extract literal values, entity names, dates, codes, and quoted terms from the question.",
            "2. Check whether external evidence gives an explicit mapping or formatting rule; if it does, use that exact value.",
            "3. Preserve stored casing and formatting when it is known, especially dates, abbreviations, and categorical values.",
            f"4. Learned rule: {rule}",
            "",
        ]
    if category_key == "ratio_numeric":
        return [
            "### Before Writing Numeric Expressions",
            "1. Identify numerator, denominator, percentage multiplier, and date/window filters from the question and evidence.",
            "2. Use REAL arithmetic or CAST when division is required.",
            "3. Guard denominator expressions when appropriate.",
            f"4. Learned rule: {rule}",
            "",
        ]
    if category_key == "ordering_limit":
        return [
            "### Before Finalizing Ranking Queries",
            "1. Identify whether the question asks for top, bottom, highest, lowest, most, least, first, or latest.",
            "2. Add explicit ORDER BY direction and LIMIT for the requested rank/count.",
            "3. Select only the requested output columns.",
            f"4. Learned rule: {rule}",
            "",
        ]
    if category_key in {"aggregation", "aggregation_projection"}:
        return [
            "### Before Writing Aggregations",
            "1. Identify the aggregate function required by the question.",
            "2. Add GROUP BY for every non-aggregate selected column.",
            "3. Keep filters that define the population in WHERE before aggregation.",
            "4. Project only the final answer requested by the question; do not output helper aggregates unless requested.",
            f"5. Learned rule: {rule}",
            "",
        ]
    if category_key in {"projection", "result_shape"}:
        return [
            "### Before Writing SELECT",
            "1. Identify the exact output columns requested by the question.",
            "2. Keep helper columns used for ranking, aggregation, joins, or filters out of SELECT unless requested.",
            "3. Check whether the final result should have one column, multiple columns, one row, or top-k rows.",
            f"4. Learned rule: {rule}",
            "",
        ]
    return [
        f"### Learned Step For {category}",
        f"1. {rule}",
        "",
    ]
