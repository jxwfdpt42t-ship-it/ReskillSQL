from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table


console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize multi-round self-update benchmark reports.")
    parser.add_argument(
        "--benchmark-dir",
        type=Path,
        default=Path("data/self_update/generated_transfer_500_multiround"),
    )
    parser.add_argument(
        "--report",
        action="append",
        default=[],
        help="Live report path. Can be repeated. Rows are matched to benchmark ids.",
    )
    parser.add_argument("--skill", type=Path, default=Path("skills/query-writing/SKILL.md"))
    parser.add_argument("--output", type=Path, default=Path("reports/multiround_self_update_summary_20260719.json"))
    args = parser.parse_args()

    summary = summarize_multiround_self_update(
        benchmark_dir=args.benchmark_dir,
        report_paths=[Path(item) for item in args.report],
        skill_path=args.skill,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _print_summary(summary, args.output)


def summarize_multiround_self_update(
    *,
    benchmark_dir: Path,
    report_paths: list[Path],
    skill_path: Path,
) -> dict[str, Any]:
    manifest = json.loads((benchmark_dir / "manifest.json").read_text(encoding="utf-8"))
    report_rows = _load_report_rows(report_paths)
    skill_text = skill_path.read_text(encoding="utf-8") if skill_path.exists() else ""
    rounds = {}
    for round_name in sorted(manifest["round_summaries"]):
        round_result = {}
        for split in ("update", "validation", "holdout"):
            split_rows = _read_jsonl(benchmark_dir / round_name / f"{split}.jsonl")
            matched = _match_report_rows(split_rows, report_rows)
            round_result[split] = _split_metrics(split_rows, matched)
        round_result["round_metrics"] = _round_metrics(round_result)
        rounds[round_name] = round_result

    evaluated = [
        metrics
        for row in rounds.values()
        for split, metrics in row.items()
        if split in {"validation", "holdout"} and metrics["evaluated"] > 0
    ]
    total_evaluated = sum(row["evaluated"] for row in evaluated)
    total_before = sum(row["before_correct"] for row in evaluated)
    total_after = sum(row["after_correct"] for row in evaluated)
    total_improvements = sum(row["improvement_total"] for row in evaluated)
    total_regressions = sum(row["regression_total"] for row in evaluated)
    total_before_failures = sum(row["evaluated"] - row["before_correct"] for row in evaluated)
    return {
        "benchmark_type": "multi_round_self_update",
        "benchmark_dir": str(benchmark_dir),
        "source_total": manifest["total"],
        "source_validated": manifest["validated"],
        "round_count": manifest["rounds"],
        "rounds": rounds,
        "aggregate": {
            "evaluated": total_evaluated,
            "before_correct": total_before,
            "after_correct": total_after,
            "before_accuracy": total_before / total_evaluated if total_evaluated else 0.0,
            "after_accuracy": total_after / total_evaluated if total_evaluated else 0.0,
            "accuracy_delta": (total_after - total_before) / total_evaluated if total_evaluated else 0.0,
            "improvement_total": total_improvements,
            "regression_total": total_regressions,
            "failure_avoidance_rate": total_improvements / total_before_failures if total_before_failures else 0.0,
            "estimated_model_calls": total_evaluated * 2,
        },
        "skill_length": _skill_length(skill_text),
        "estimated_cost": _estimate_cost(rounds, skill_text),
        "report_paths": [str(path) for path in report_paths],
    }


def _load_report_rows(report_paths: list[Path]) -> dict[str, dict[str, Any]]:
    rows = {}
    for path in report_paths:
        if not path.exists():
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        for row in report.get("rows", []):
            rows[str(row["id"])] = row
    return rows


def _match_report_rows(split_rows: list[dict[str, Any]], report_rows: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    matched = []
    for row in split_rows:
        report_row = report_rows.get(str(row["id"]))
        if report_row is None and row.get("original_id"):
            report_row = report_rows.get(str(row["original_id"]))
        if report_row is not None:
            merged = dict(report_row)
            merged["benchmark_category"] = row.get("category")
            matched.append(merged)
    return matched


def _split_metrics(split_rows: list[dict[str, Any]], matched: list[dict[str, Any]]) -> dict[str, Any]:
    before_correct = sum(1 for row in matched if row.get("before_correct"))
    after_correct = sum(1 for row in matched if row.get("after_correct"))
    improvements = [row for row in matched if not row.get("before_correct") and row.get("after_correct")]
    regressions = [row for row in matched if row.get("before_correct") and not row.get("after_correct")]
    before_failures = len(matched) - before_correct
    return {
        "planned": len(split_rows),
        "validated_planned": sum(1 for row in split_rows if row.get("validated", True)),
        "evaluated": len(matched),
        "coverage": len(matched) / len(split_rows) if split_rows else 0.0,
        "before_correct": before_correct,
        "after_correct": after_correct,
        "before_accuracy": before_correct / len(matched) if matched else 0.0,
        "after_accuracy": after_correct / len(matched) if matched else 0.0,
        "accuracy_delta": (after_correct - before_correct) / len(matched) if matched else 0.0,
        "improvement_total": len(improvements),
        "regression_total": len(regressions),
        "failure_avoidance_rate": len(improvements) / before_failures if before_failures else 0.0,
        "category_transfer_gain": _category_transfer_gain(matched),
        "improvements_by_category": dict(Counter(str(row.get("benchmark_category") or "unknown") for row in improvements)),
        "regressions_by_category": dict(Counter(str(row.get("benchmark_category") or "unknown") for row in regressions)),
    }


def _round_metrics(round_result: dict[str, dict[str, Any]]) -> dict[str, Any]:
    validation = round_result["validation"]
    holdout = round_result["holdout"]
    return {
        "gate_split": "validation",
        "final_split": "holdout",
        "gate_accuracy_delta": validation["accuracy_delta"],
        "final_accuracy_delta": holdout["accuracy_delta"],
        "gate_regressions": validation["regression_total"],
        "final_regressions": holdout["regression_total"],
        "gate_failure_avoidance_rate": validation["failure_avoidance_rate"],
        "final_failure_avoidance_rate": holdout["failure_avoidance_rate"],
        "status": "evaluated" if validation["evaluated"] or holdout["evaluated"] else "planned",
    }


def _category_transfer_gain(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get("benchmark_category") or "unknown")].append(row)
    result = {}
    for category, category_rows in sorted(buckets.items()):
        before = sum(1 for row in category_rows if row.get("before_correct"))
        after = sum(1 for row in category_rows if row.get("after_correct"))
        total = len(category_rows)
        result[category] = {
            "total": total,
            "before_correct": before,
            "after_correct": after,
            "delta": (after - before) / total if total else 0.0,
        }
    return result


def _skill_length(skill_text: str) -> dict[str, int]:
    return {
        "words": len(skill_text.split()),
        "characters": len(skill_text),
        "lines": len(skill_text.splitlines()),
    }


def _estimate_cost(rounds: dict[str, Any], skill_text: str) -> dict[str, Any]:
    evaluated = sum(
        metrics["evaluated"]
        for round_result in rounds.values()
        for split, metrics in round_result.items()
        if split in {"validation", "holdout"}
    )
    skill_words = len(skill_text.split())
    estimated_model_calls = evaluated * 2
    estimated_prompt_tokens = int(estimated_model_calls * skill_words * 1.3)
    return {
        "estimated_model_calls": estimated_model_calls,
        "estimated_prompt_tokens_from_skill": estimated_prompt_tokens,
        "note": "Token/cost values are estimates from evaluated examples and skill length; provider billing logs are not available.",
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _print_summary(summary: dict[str, Any], output: Path) -> None:
    table = Table(title="Multi-Round Self-Update Summary")
    table.add_column("Round")
    table.add_column("Validation")
    table.add_column("Holdout")
    table.add_column("FAR")
    for round_name, row in summary["rounds"].items():
        validation = row["validation"]
        holdout = row["holdout"]
        table.add_row(
            round_name,
            _format_split(validation),
            _format_split(holdout),
            f"gate={validation['failure_avoidance_rate']:.2%}, final={holdout['failure_avoidance_rate']:.2%}",
        )
    aggregate = summary["aggregate"]
    table.add_row(
        "aggregate",
        "-",
        f"{aggregate['before_correct']}/{aggregate['evaluated']} -> {aggregate['after_correct']}/{aggregate['evaluated']} ({aggregate['accuracy_delta']:+.2%})",
        f"{aggregate['failure_avoidance_rate']:.2%}",
    )
    console.print(table)
    console.print(f"[green]Wrote summary to {output}[/green]")


def _format_split(row: dict[str, Any]) -> str:
    if not row["evaluated"]:
        return f"planned={row['planned']}"
    return f"{row['before_correct']}/{row['evaluated']} -> {row['after_correct']}/{row['evaluated']} ({row['accuracy_delta']:+.2%})"


if __name__ == "__main__":
    main()
