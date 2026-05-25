from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from text2sql_evolver.benchmarks.evaluate_skill_replay import evaluate_skill_replay
from text2sql_evolver.utils.paths import resolve_dataset_path


console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a lightweight replay ablation over compiled skill policies.")
    parser.add_argument("--dataset", required=True, type=Path, help="JSONL dataset used by the historical run.")
    parser.add_argument("--examples", type=Path, default=None, help="Historical report examples.json.")
    parser.add_argument("--predictions", type=Path, default=None, help="Prediction JSONL with id and predicted_sql.")
    parser.add_argument("--skill", default=Path("skills/query-writing/SKILL.md"), type=Path)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    dataset_path = resolve_dataset_path(Path("data/chinook_eval.jsonl"), str(args.dataset))
    summary = run_replay_ablation(
        dataset_path=dataset_path,
        examples_path=args.examples,
        predictions_path=args.predictions,
        skill_path=args.skill,
        limit=args.limit,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _print_summary(summary, args.output)


def run_replay_ablation(
    *,
    dataset_path: Path,
    skill_path: Path,
    examples_path: Path | None = None,
    predictions_path: Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    if examples_path is None and predictions_path is None:
        raise ValueError("Either examples_path or predictions_path is required.")
    base_skill = skill_path.read_text(encoding="utf-8")
    variants = {
        "no_reskill": _no_reskill_skill(),
        "query_skill_checks_only": _without_tool_policies(base_skill),
        "value_lookup_only": _value_lookup_only_skill(),
        "full_system": base_skill,
    }
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for name, skill_text in variants.items():
            variant_skill = tmp_path / f"{name}.md"
            variant_skill.write_text(skill_text, encoding="utf-8")
            result = evaluate_skill_replay(
                dataset_path=dataset_path,
                examples_path=examples_path,
                predictions_path=predictions_path,
                skill_path=variant_skill,
                limit=limit,
            )
            results.append(_compact(name, result))
    baseline = results[0]
    return {
        "benchmark_type": "replay_ablation",
        "dataset": str(dataset_path),
        "examples": str(examples_path) if examples_path else None,
        "predictions": str(predictions_path) if predictions_path else None,
        "skill": str(skill_path),
        "total": baseline["total"],
        "baseline_correct": baseline["after_correct"],
        "baseline_accuracy": baseline["after_accuracy"],
        "variants": results,
    }


def _compact(name: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "total": result["total"],
        "before_correct": result["before_correct"],
        "after_correct": result["after_correct"],
        "before_accuracy": result["before_accuracy"],
        "after_accuracy": result["after_accuracy"],
        "accuracy_delta": result["after_accuracy"] - result["before_accuracy"],
        "improvement_total": len(result.get("improvements", [])),
        "regression_total": len(result.get("regressions", [])),
        "improvements_by_category": result.get("improvements_by_category", {}),
    }


def _no_reskill_skill() -> str:
    return "# No Reskill\n\nNo compiled skill checks or tool policies are enabled.\n"


def _without_tool_policies(skill_text: str) -> str:
    text = skill_text.replace("Value Lookup Policy", "Value Lookup Disabled")
    text = text.replace("Schema Context Policy", "Schema Context Disabled")
    return text


def _value_lookup_only_skill() -> str:
    return """# Value Lookup Only

## Mandatory Pre-SQL Plan

### Value Lookup Policy

Normalize high-confidence literal formats against stored database values.
"""


def _print_summary(summary: dict[str, Any], output: Path | None) -> None:
    table = Table(title="Replay Ablation")
    table.add_column("Variant")
    table.add_column("Before")
    table.add_column("After")
    table.add_column("Delta")
    table.add_column("Improvements")
    table.add_column("Regressions")
    for row in summary["variants"]:
        total = row["total"]
        table.add_row(
            row["name"],
            f"{row['before_correct']}/{total} ({row['before_accuracy']:.2%})",
            f"{row['after_correct']}/{total} ({row['after_accuracy']:.2%})",
            f"{row['accuracy_delta']:+.2%}",
            str(row["improvement_total"]),
            str(row["regression_total"]),
        )
    if output:
        table.add_row("output", str(output), "", "", "", "")
    console.print(table)


if __name__ == "__main__":
    main()
