from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from text2sql_evolver.config import load_settings
from text2sql_evolver.dataset import Example, load_jsonl
from text2sql_evolver.inner_runner import apply_sql_skill_checks
from text2sql_evolver.judge import judge_sql
from text2sql_evolver.utils.io import load_prediction_jsonl
from text2sql_evolver.utils.paths import resolve_database_path


console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay historical Text-to-SQL predictions through the current compiled skill checks."
    )
    parser.add_argument("--dataset", required=True, type=Path, help="JSONL dataset used by the historical run.")
    parser.add_argument("--examples", type=Path, default=None, help="Historical report examples.json.")
    parser.add_argument("--predictions", type=Path, default=None, help="Prediction JSONL with id and predicted_sql.")
    parser.add_argument("--skill", default=Path("skills/query-writing/SKILL.md"), type=Path)
    parser.add_argument("--limit", default=None, type=int)
    parser.add_argument("--output", default=None, type=Path)
    args = parser.parse_args()

    result = evaluate_skill_replay(
        dataset_path=args.dataset,
        examples_path=args.examples,
        predictions_path=args.predictions,
        skill_path=args.skill,
        limit=args.limit,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    _print_result(result, args.output)


def evaluate_skill_replay(
    *,
    dataset_path: Path,
    examples_path: Path | None = None,
    predictions_path: Path | None = None,
    skill_path: Path,
    limit: int | None = None,
) -> dict[str, Any]:
    if examples_path is None and predictions_path is None:
        raise ValueError("Either examples_path or predictions_path is required.")
    settings = load_settings()
    examples = {example.id: example for example in load_jsonl(dataset_path, limit=limit)}
    historical_rows = _load_historical_rows(examples_path=examples_path, predictions_path=predictions_path)
    if limit is not None:
        historical_rows = historical_rows[:limit]
    skill_text = skill_path.read_text(encoding="utf-8")

    changes: list[dict[str, Any]] = []
    improvements: list[str] = []
    regressions: list[str] = []
    improvements_by_category: Counter[str] = Counter()
    before_correct = 0
    after_correct = 0

    for row in historical_rows:
        example = examples.get(str(row["id"]))
        if example is None:
            continue
        database_path = resolve_database_path(example.db_path, settings.database_path)
        predicted_sql = str(row["predicted_sql"])
        before = judge_sql(database_path, predicted_sql, example.gold_sql)
        rewritten_sql = apply_sql_skill_checks(
            predicted_sql,
            example.question,
            skill_text,
            database_path=database_path,
        )
        after = judge_sql(database_path, rewritten_sql, example.gold_sql)

        before_correct += int(before.correct)
        after_correct += int(after.correct)
        category = str(row.get("category") or "correct_or_unknown")
        if not before.correct and after.correct:
            improvements.append(example.id)
            improvements_by_category[category] += 1
        elif before.correct and not after.correct:
            regressions.append(example.id)

        if predicted_sql != rewritten_sql or before.correct != after.correct:
            changes.append(_change_row(example, row, predicted_sql, rewritten_sql, before.reason, after.reason))

    total = len([row for row in historical_rows if str(row.get("id")) in examples])
    before_accuracy = before_correct / total if total else 0.0
    after_accuracy = after_correct / total if total else 0.0
    return {
        "dataset": str(dataset_path),
        "examples": str(examples_path) if examples_path else None,
        "predictions": str(predictions_path) if predictions_path else None,
        "skill": str(skill_path),
        "total": total,
        "before_correct": before_correct,
        "after_correct": after_correct,
        "before_accuracy": before_accuracy,
        "after_accuracy": after_accuracy,
        "accuracy_delta": after_accuracy - before_accuracy,
        "improvements": improvements,
        "regressions": regressions,
        "improvements_by_category": dict(improvements_by_category),
        "changed_count": len(changes),
        "changes": changes,
    }


def _load_historical_rows(
    *,
    examples_path: Path | None,
    predictions_path: Path | None,
) -> list[dict[str, Any]]:
    if examples_path is not None:
        return json.loads(examples_path.read_text(encoding="utf-8"))
    assert predictions_path is not None
    predictions = load_prediction_jsonl(str(predictions_path))
    return [
        {"id": example_id, "predicted_sql": predicted_sql, "category": None}
        for example_id, predicted_sql in predictions.items()
    ]


def _change_row(
    example: Example,
    historical_row: dict[str, Any],
    predicted_sql: str,
    rewritten_sql: str,
    before_reason: str,
    after_reason: str,
) -> dict[str, Any]:
    return {
        "id": example.id,
        "question": example.question,
        "category": historical_row.get("category"),
        "before_correct": before_reason.startswith("execution_match"),
        "after_correct": after_reason.startswith("execution_match"),
        "before_reason": before_reason,
        "after_reason": after_reason,
        "predicted_sql": predicted_sql,
        "rewritten_sql": rewritten_sql,
        "gold_sql": example.gold_sql,
    }


def _print_result(result: dict[str, Any], output: Path | None) -> None:
    table = Table(title="Compiled Skill Replay")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("examples", str(result["total"]))
    table.add_row("before", f"{result['before_correct']}/{result['total']} ({result['before_accuracy']:.2%})")
    table.add_row("after", f"{result['after_correct']}/{result['total']} ({result['after_accuracy']:.2%})")
    table.add_row("delta", f"{result['accuracy_delta']:+.2%}")
    table.add_row("improvements", json.dumps(result["improvements"], ensure_ascii=False))
    table.add_row("regressions", json.dumps(result["regressions"], ensure_ascii=False))
    table.add_row("improvements by category", json.dumps(result["improvements_by_category"], ensure_ascii=False))
    table.add_row("changed SQL", str(result["changed_count"]))
    if output:
        table.add_row("output", str(output))
    console.print(table)


if __name__ == "__main__":
    main()
