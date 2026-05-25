from text2sql_evolver.benchmarks.summarize_replay_collection import summarize_collection


def test_summarize_replay_collection_accumulates_weighted_totals():
    first = {
        "total": 100,
        "before_correct": 53,
        "after_correct": 59,
        "before_accuracy": 0.53,
        "after_accuracy": 0.59,
        "accuracy_delta": 0.06,
        "improvements": ["a", "b", "c"],
        "regressions": [],
        "improvements_by_category": {"projection": 3},
        "changed_count": 10,
    }
    second = {
        "total": 50,
        "before_correct": 39,
        "after_correct": 37,
        "before_accuracy": 0.78,
        "after_accuracy": 0.74,
        "accuracy_delta": -0.04,
        "improvements": ["d"],
        "regressions": ["e", "f"],
        "improvements_by_category": {"value_grounding": 1},
        "changed_count": 5,
    }

    summary = summarize_collection([("first", first), ("second", second)])

    assert summary["total"] == 150
    assert summary["before_correct"] == 92
    assert summary["after_correct"] == 96
    assert round(summary["accuracy_delta"], 4) == round(4 / 150, 4)
    assert summary["improvement_total"] == 4
    assert summary["regression_total"] == 2
    assert summary["improvements_by_category"] == {"projection": 3, "value_grounding": 1}
