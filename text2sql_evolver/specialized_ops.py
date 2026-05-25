from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpecializedOperation:
    """A SQL-specific evolver operation and the reason it belongs in the loop."""

    key: str
    name: str
    purpose: str
    sql_rationale: str
    implementation_status: str


SPECIALIZED_OPERATIONS: tuple[SpecializedOperation, ...] = (
    SpecializedOperation(
        key="clause_level_analysis",
        name="Clause-level analysis",
        purpose="Decompose SQL into SELECT/FROM/JOIN/WHERE/GROUP BY/ORDER BY/LIMIT and localize the failing clause.",
        sql_rationale="SQL is a structured language, so failures usually map to explicit clauses instead of vague free-form behavior.",
        implementation_status="implemented: heuristic clause checks plus reportable detector details",
    ),
    SpecializedOperation(
        key="schema_linking_check",
        name="Schema linking check",
        purpose="Check whether predicted tables and columns exist and whether they match the question intent.",
        sql_rationale="Text-to-SQL often fails by choosing the wrong table or business-specific column, especially on BIRD.",
        implementation_status="partial: table mismatch detection is implemented; column-level grounding is planned",
    ),
    SpecializedOperation(
        key="join_path_analysis",
        name="Join path analysis",
        purpose="Detect missing joins, extra joins, disconnected join paths, and suspicious join conditions.",
        sql_rationale="Multi-table SQL depends on schema graph connectivity and foreign-key paths, which can be inspected directly.",
        implementation_status="partial: join-count mismatch is implemented; FK graph validation is planned",
    ),
    SpecializedOperation(
        key="value_grounding_check",
        name="Value grounding check",
        purpose="Map entities in the question to actual database values and catch value mismatches.",
        sql_rationale="Many SQL errors are value errors rather than syntax errors, such as Alameda County vs Alameda.",
        implementation_status="partial: literal mismatch detector implemented; DB value retrieval is next",
    ),
    SpecializedOperation(
        key="execution_error_classification",
        name="Execution error classification",
        purpose="Classify runtime errors such as no such table, no such column, ambiguous column, syntax error, and timeout.",
        sql_rationale="SQL execution errors are strong feedback, and each error class has a natural repair strategy.",
        implementation_status="partial: read-only guard and basic runtime failure categories are implemented",
    ),
    SpecializedOperation(
        key="result_shape_comparison",
        name="Result-shape comparison",
        purpose="Compare row count, column count, single-row aggregation shape, top-k shape, and returned value types.",
        sql_rationale="A SQL query can execute but still return the wrong shape, revealing missing aggregation, projection, or LIMIT.",
        implementation_status="implemented: row/column shape comparison for mismatch diagnosis",
    ),
    SpecializedOperation(
        key="aggregation_reasoning_check",
        name="Aggregation reasoning check",
        purpose="Check COUNT/SUM/AVG/MIN/MAX, GROUP BY, and non-aggregate selected columns.",
        sql_rationale="SQL aggregation has explicit rules and common failure modes that are easy to inspect structurally.",
        implementation_status="partial: aggregate and GROUP BY mismatch detection is implemented",
    ),
    SpecializedOperation(
        key="ratio_numeric_handling",
        name="Ratio / percentage handling",
        purpose="Handle rates, percentages, averages, differences, REAL casts, NULLIF denominators, and ordering by computed metrics.",
        sql_rationale="BIRD often uses evidence-defined formulas, and numeric SQL is vulnerable to integer division and divide-by-zero issues.",
        implementation_status="partial: ratio trigger, division, REAL/NULLIF, and ORDER BY checks implemented",
    ),
    SpecializedOperation(
        key="order_limit_tiebreak_check",
        name="Order / limit / tie-break check",
        purpose="Check top/bottom/latest/highest/lowest ranking semantics, ORDER BY direction, LIMIT, and stable tie-breakers.",
        sql_rationale="Ranking questions are common, and execution-equivalent intent can fail because of missing LIMIT or unstable ordering.",
        implementation_status="partial: ORDER BY/LIMIT/tie-break clause mismatch detection is implemented",
    ),
    SpecializedOperation(
        key="evidence_usage_check",
        name="Evidence usage check",
        purpose="Check whether BIRD evidence formulas, business definitions, and filters are reflected in SQL.",
        sql_rationale="BIRD provides evidence fields, making domain-grounded diagnosis possible instead of generic reflection.",
        implementation_status="partial: evidence term coverage warning implemented",
    ),
    SpecializedOperation(
        key="sql_safety_guard",
        name="SQL safety guard",
        purpose="Block INSERT/UPDATE/DELETE/DROP/ALTER/PRAGMA and other non-read-only statements.",
        sql_rationale="A public benchmark runner must safely execute model-generated SQL against local databases.",
        implementation_status="implemented in judge.py",
    ),
    SpecializedOperation(
        key="skill_patch_validation",
        name="Skill patch validation",
        purpose="Validate skill edits on held-out examples and accept or roll back based on measured behavior.",
        sql_rationale="Execution accuracy gives a concrete acceptance signal, preventing prompt edits from becoming unchecked reflection.",
        implementation_status="implemented: optional validation split with rollback on accuracy regression",
    ),
)


def operations_as_markdown_table() -> str:
    lines = [
        "| Operation | Purpose | Why It Fits SQL | Status |",
        "|---|---|---|---|",
    ]
    for op in SPECIALIZED_OPERATIONS:
        lines.append(
            f"| {op.name} | {op.purpose} | {op.sql_rationale} | {op.implementation_status} |"
        )
    return "\n".join(lines)


def operations_as_dicts() -> list[dict[str, str]]:
    return [
        {
            "key": op.key,
            "name": op.name,
            "purpose": op.purpose,
            "sql_rationale": op.sql_rationale,
            "implementation_status": op.implementation_status,
        }
        for op in SPECIALIZED_OPERATIONS
    ]
