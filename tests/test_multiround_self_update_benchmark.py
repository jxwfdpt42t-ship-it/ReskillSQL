from pathlib import Path
import json

from text2sql_evolver.benchmarks.make_multiround_self_update_benchmark import build_multiround_benchmark
from text2sql_evolver.benchmarks.summarize_multiround_self_update import summarize_multiround_self_update


def test_build_multiround_benchmark_keeps_500_style_splits(tmp_path: Path):
    source = tmp_path / "source"
    combined = source / "combined"
    rows = [
        {
            "id": f"generated_transfer_{index}",
            "source_id": str(index),
            "question": f"question {index}",
            "gold_sql": "SELECT 1",
            "db_path": "demo.sqlite",
            "category": "ordering_limit" if index % 2 else "aggregation_projection",
            "validated": index != 12,
        }
        for index in range(1, 13)
    ]
    _write_jsonl(combined / "update.jsonl", rows[:4])
    _write_jsonl(combined / "validation.jsonl", rows[4:8])
    _write_jsonl(combined / "holdout.jsonl", rows[8:])

    output = tmp_path / "multi"
    summary = build_multiround_benchmark(source_dir=source, output_dir=output, rounds=3, seed=1)

    assert summary["total"] == 12
    assert summary["validated"] == 11
    assert set(summary["round_summaries"]) == {"round_1", "round_2", "round_3"}
    assert sum(row["total"] for row in summary["round_summaries"].values()) == 12
    for round_name in ("round_1", "round_2", "round_3"):
        assert (output / round_name / "update.jsonl").exists()
        assert (output / round_name / "validation.jsonl").exists()
        assert (output / round_name / "holdout.jsonl").exists()
    assert (output / "manifest.json").exists()


def test_summarize_multiround_self_update_reports_metrics(tmp_path: Path):
    source = tmp_path / "source"
    combined = source / "combined"
    rows = [
        {
            "id": f"generated_transfer_{index}",
            "source_id": str(index),
            "question": f"question {index}",
            "gold_sql": "SELECT 1",
            "db_path": "demo.sqlite",
            "category": "ordering_limit",
            "validated": True,
        }
        for index in range(1, 10)
    ]
    _write_jsonl(combined / "update.jsonl", rows[:3])
    _write_jsonl(combined / "validation.jsonl", rows[3:6])
    _write_jsonl(combined / "holdout.jsonl", rows[6:])
    benchmark = tmp_path / "benchmark"
    build_multiround_benchmark(source_dir=source, output_dir=benchmark, rounds=3, seed=2)

    round_1_validation_ids = [
        json.loads(line)["id"]
        for line in (benchmark / "round_1" / "validation.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    report = tmp_path / "live.json"
    report.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "id": round_1_validation_ids[0],
                        "before_correct": False,
                        "after_correct": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    skill = tmp_path / "skill.md"
    skill.write_text("use order by limit", encoding="utf-8")

    summary = summarize_multiround_self_update(
        benchmark_dir=benchmark,
        report_paths=[report],
        skill_path=skill,
    )

    assert summary["source_total"] == 9
    assert summary["aggregate"]["evaluated"] == 1
    assert summary["aggregate"]["failure_avoidance_rate"] == 1.0
    assert summary["skill_length"]["words"] == 4


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
