from text2sql_evolver.benchmarks.summarize_replay_suite import summarize_suite


def test_summarize_replay_suite_checks_holdout_and_regressions():
    update = {
        "total": 10,
        "before_correct": 5,
        "after_correct": 7,
        "before_accuracy": 0.5,
        "after_accuracy": 0.7,
        "accuracy_delta": 0.2,
        "improvements": ["u1", "u2"],
        "regressions": [],
        "improvements_by_category": {"projection": 2},
    }
    holdout = {
        "total": 5,
        "before_correct": 2,
        "after_correct": 3,
        "before_accuracy": 0.4,
        "after_accuracy": 0.6,
        "accuracy_delta": 0.2,
        "improvements": ["h1"],
        "regressions": [],
        "improvements_by_category": {"value_grounding": 1},
    }

    summary = summarize_suite(update, holdout)

    assert summary["passes_no_regression_check"]
    assert summary["passes_holdout_positive_check"]
    assert summary["improvement_total"] == 3
    assert summary["categories_improved"] == ["projection", "value_grounding"]
