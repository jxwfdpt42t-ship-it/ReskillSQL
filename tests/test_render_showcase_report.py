from text2sql_evolver.benchmarks.render_showcase_report import render_showcase_report


def test_render_showcase_report_contains_core_metrics():
    live = {
        "total": 2,
        "before_correct": 1,
        "after_correct": 2,
        "before_accuracy": 0.5,
        "after_accuracy": 1.0,
        "accuracy_delta": 0.5,
        "improvement_total": 1,
        "regression_total": 0,
        "improvements_by_category": {"projection": 1},
        "rows": [
            {
                "id": "ex1",
                "question": "List names.",
                "before_correct": False,
                "after_correct": True,
                "before_reason": "execution_mismatch",
                "after_reason": "execution_match",
                "after_category": "projection",
                "before_sql": "SELECT name, helper FROM t",
                "after_sql": "SELECT name FROM t",
            }
        ],
    }
    replay = {
        "total": 2,
        "before_correct": 1,
        "after_correct": 2,
        "accuracy_delta": 0.5,
        "splits": [
            {
                "label": "update",
                "total": 2,
                "before_correct": 1,
                "after_correct": 2,
                "before_accuracy": 0.5,
                "after_accuracy": 1.0,
                "accuracy_delta": 0.5,
                "improvements": ["ex1"],
                "regressions": [],
            }
        ],
    }
    ablation = {
        "variants": [
            {
                "name": "full_system",
                "total": 2,
                "before_correct": 1,
                "after_correct": 2,
                "before_accuracy": 0.5,
                "after_accuracy": 1.0,
                "accuracy_delta": 0.5,
                "improvement_total": 1,
                "regression_total": 0,
            }
        ]
    }

    html = render_showcase_report(live=live, replay=replay, ablation=ablation)

    assert "Self-Reskilling Text-to-SQL Agent" in html
    assert "Live BIRD 100" in html
    assert "full_system" in html
    assert "SELECT name FROM t" in html
