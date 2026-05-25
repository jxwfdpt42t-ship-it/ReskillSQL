from text2sql_evolver.analyzers.behavior_signals import filter_store_by_weighted_support
from text2sql_evolver.analyzers.fixability import QuerySkillFixabilityFilter
from text2sql_evolver.editors.patch_metadata import build_patch_metadata
from text2sql_evolver.failure_store import FailureStore
from text2sql_evolver.validators.sql_aware_gate import SQLAwareGate


def test_fixability_routes_ordering_limit_to_query_skill():
    decision = QuerySkillFixabilityFilter().decide(
        {
            "category": "ordering_limit",
            "judge_reason": "execution_mismatch",
            "details": {"gold_order_by": "count desc", "predicted_order_by": "count desc"},
        }
    )

    assert decision.query_skill_fixable
    assert decision.fixability == "fixable"


def test_fixability_rejects_gold_sql_noise():
    decision = QuerySkillFixabilityFilter().decide(
        {
            "category": "syntax_or_runtime",
            "judge_reason": "gold_sql_failed: no such table",
            "details": {},
        }
    )

    assert not decision.query_skill_fixable
    assert decision.fixability == "not_fixable"


def test_fixability_uses_llm_review_for_uncertain(monkeypatch):
    def fake_complete_text(settings, system, user, max_tokens=700):
        return """{
          "query_skill_fixable": true,
          "sql_error_type": "other_sql_error",
          "reason": "The failure is a reusable SQL writing issue outside the current categories.",
          "confidence": 0.77
        }"""

    monkeypatch.setattr("text2sql_evolver.analyzers.fixability.complete_text", fake_complete_text)
    decision = QuerySkillFixabilityFilter(settings=object()).decide(
        {
            "category": "unknown_category",
            "judge_reason": "execution_mismatch",
            "details": {},
        }
    )

    assert decision.query_skill_fixable
    assert decision.fixability == "fixable"
    assert decision.sql_error_type == "other_sql_error"
    assert decision.reviewed_by_llm


def test_patch_metadata_binds_category_evidence_and_examples():
    metadata = build_patch_metadata(
        [
            {
                "id": "ex1",
                "category": "ordering_limit",
                "evidence": "LIMIT mismatch",
                "details": {},
                "fixability": {
                    "query_skill_fixable": True,
                    "confidence": 0.8,
                    "reason": "ranking behavior",
                },
            }
        ],
        max_rules=1,
        run_id="round-test",
    )

    assert metadata[0]["category"] == "ordering_limit"
    assert metadata[0]["operation_key"] == "order_limit_tiebreak_check"
    assert metadata[0]["support_examples"] == ["ex1"]
    assert metadata[0]["detector_evidence"] == ["LIMIT mismatch"]


def test_sql_aware_gate_rejects_when_selection_score_does_not_improve():
    decision = SQLAwareGate(max_regressions=0).decide(
        before_rows=[
            {"id": "a", "correct": True, "category": None},
            {"id": "b", "correct": False, "category": "ordering_limit"},
        ],
        after_rows=[
            {"id": "a", "correct": False, "category": "join_path"},
            {"id": "b", "correct": True, "category": None},
        ],
        patch_metadata=[{"category": "ordering_limit"}],
    )

    assert not decision.accepted
    assert decision.reason == "selection_score_not_improved=0.0000"


def test_sql_aware_gate_rejects_target_improvement_without_score_gain():
    decision = SQLAwareGate(max_regressions=0, require_target_improvement=True).decide(
        before_rows=[
            {"id": "a", "correct": False, "category": "ordering_limit"},
            {"id": "b", "correct": False, "category": "ordering_limit"},
            {"id": "c", "correct": True, "category": None},
        ],
        after_rows=[
            {"id": "a", "correct": False, "category": "value_grounding"},
            {"id": "b", "correct": False, "category": "ordering_limit"},
            {"id": "c", "correct": True, "category": None},
        ],
        patch_metadata=[
            {
                "category": "ordering_limit",
                "patch_text": "For ranking questions, use ORDER BY direction and LIMIT.",
                "detector_evidence": ["ORDER BY or LIMIT mismatch"],
            }
        ],
    )

    assert not decision.accepted
    assert decision.reason == "selection_score_not_improved=0.0000"
    assert decision.metrics["gate_level"] == "reject"


def test_sql_aware_gate_accepts_strict_selection_score_gain_with_regression():
    decision = SQLAwareGate(max_regressions=0).decide(
        before_rows=[
            {"id": "a", "correct": True, "category": None},
            {"id": "b", "correct": False, "category": "ordering_limit"},
            {"id": "c", "correct": False, "category": "ordering_limit"},
        ],
        after_rows=[
            {"id": "a", "correct": False, "category": "join_path"},
            {"id": "b", "correct": True, "category": None},
            {"id": "c", "correct": True, "category": None},
        ],
        patch_metadata=[
            {
                "category": "ordering_limit",
                "patch_text": "For ranking questions, use ORDER BY direction and LIMIT.",
                "detector_evidence": ["ORDER BY or LIMIT mismatch"],
            }
        ],
    )

    assert decision.accepted
    assert decision.reason.startswith("skillopt_pass_with_regressions")
    assert decision.metrics["candidate_score"] > decision.metrics["current_score"]


def test_sql_aware_gate_rejects_protected_regression_memory():
    decision = SQLAwareGate(max_protected_regressions=0).decide(
        before_rows=[
            {"id": "a", "correct": False, "category": "ordering_limit"},
            {"id": "b", "correct": False, "category": "ordering_limit"},
            {"id": "c", "correct": True, "category": None},
        ],
        after_rows=[
            {"id": "a", "correct": True, "category": None},
            {"id": "b", "correct": True, "category": None},
            {"id": "c", "correct": True, "category": None},
        ],
        protected_before_rows=[
            {"id": "p1", "correct": True, "category": None},
        ],
        protected_after_rows=[
            {"id": "p1", "correct": False, "category": "projection"},
        ],
        patch_metadata=[
            {
                "category": "ordering_limit",
                "patch_text": "For ranking questions, use ORDER BY direction and LIMIT.",
                "detector_evidence": ["ORDER BY or LIMIT mismatch"],
            }
        ],
    )

    assert not decision.accepted
    assert decision.reason == "protected_regression_total=1"
    assert decision.metrics["protected_regressions"] == ["p1"]


def test_weighted_support_filters_one_off_failures():
    store = FailureStore()
    store.add({"id": "a", "category": "ordering_limit"})
    store.add({"id": "b", "category": "value_grounding"})
    store.add({"id": "c", "category": "value_grounding"})
    cards = [
        {"example_id": "a", "category": "ordering_limit", "signal_type": "hard_failure", "weight": 1.0, "fix_route": "query_skill"},
        {"example_id": "b", "category": "value_grounding", "signal_type": "hard_failure", "weight": 1.0, "fix_route": "query_skill"},
        {"example_id": "c", "category": "value_grounding", "signal_type": "hard_failure", "weight": 1.0, "fix_route": "query_skill"},
    ]

    filtered, report = filter_store_by_weighted_support(
        store,
        cards,
        min_weighted_support=2.0,
        min_support_ratio=0.8,
    )

    assert [row["id"] for row in filtered.rows] == ["b", "c"]
    assert report["supported_categories"] == ["value_grounding"]


def test_weighted_support_ignores_non_query_skill_routes():
    store = FailureStore()
    store.add({"id": "a", "category": "value_grounding"})
    store.add({"id": "b", "category": "value_grounding"})
    cards = [
        {"example_id": "a", "category": "value_grounding", "signal_type": "hard_failure", "weight": 1.0, "fix_route": "value_lookup_tool"},
        {"example_id": "b", "category": "value_grounding", "signal_type": "hard_failure", "weight": 1.0, "fix_route": "value_lookup_tool"},
    ]

    filtered, report = filter_store_by_weighted_support(store, cards, min_weighted_support=2.0)

    assert filtered.rows == []
    assert report["supported_categories"] == []
    assert report["route_weighted_support"]["value_grounding+value_lookup_tool"] == 2.0
