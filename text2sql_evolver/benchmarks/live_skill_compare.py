from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from rich.console import Console
from rich.table import Table

from text2sql_evolver.analyzers.sql_specialized import SQLSpecializedAnalyzer
from text2sql_evolver.config import Settings, load_settings
from text2sql_evolver.dataset import Example, load_jsonl
from text2sql_evolver.inner_runner import generate_sql
from text2sql_evolver.judge import JudgeResult, judge_sql
from text2sql_evolver.memory.regression_memory import RegressionMemoryStore
from text2sql_evolver.utils.paths import resolve_database_path, resolve_dataset_path


console = Console()
SQLGenerator = Callable[[Settings, Example, Path, Path], str]


@dataclass(frozen=True)
class LiveAttempt:
    sql: str
    judge: JudgeResult
    category: str | None
    evidence: str | None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a live old-skill vs new-skill Text-to-SQL comparison.")
    parser.add_argument("--dataset", required=True, type=str, help="JSONL dataset path.")
    parser.add_argument("--before-skill", required=True, type=Path, help="Baseline skill file.")
    parser.add_argument("--after-skill", required=True, type=Path, help="Candidate/current skill file.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON report path.")
    parser.add_argument("--max-retries", type=int, default=2, help="Retries for transient model/API failures.")
    parser.add_argument(
        "--regression-memory",
        type=Path,
        default=None,
        help="JSONL file where old-correct/new-wrong examples are stored as future protection cases.",
    )
    args = parser.parse_args()

    settings = load_settings()
    dataset_path = resolve_dataset_path(settings.dataset_path, args.dataset)
    output = args.output or _default_output_path(settings)
    result = compare_live_skills(
        settings=settings,
        dataset_path=dataset_path,
        before_skill=args.before_skill,
        after_skill=args.after_skill,
        limit=args.limit,
        output_path=output,
        max_retries=args.max_retries,
    )
    memory_path = args.regression_memory or settings.project_root / "data" / "regression_memory.jsonl"
    memory_added = _record_regression_memory(result, memory_path, run_id=output.stem)
    result["regression_memory_path"] = str(memory_path)
    result["regression_memory_added"] = len(memory_added)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    _print_summary(result, output)


def compare_live_skills(
    *,
    settings: Settings,
    dataset_path: Path,
    before_skill: Path,
    after_skill: Path,
    limit: int | None = None,
    generator: SQLGenerator | None = None,
    output_path: Path | None = None,
    max_retries: int = 2,
) -> dict[str, Any]:
    examples = load_jsonl(dataset_path, limit=limit)
    generator = generator or _generate_with_skill
    analyzer = SQLSpecializedAnalyzer()
    rows: list[dict[str, Any]] = []

    before_correct = 0
    after_correct = 0
    improvements: list[str] = []
    regressions: list[str] = []
    improvements_by_category: Counter[str] = Counter()
    regressions_by_category: Counter[str] = Counter()

    for example in examples:
        database_path = resolve_database_path(example.db_path, settings.database_path)
        console.print(f"[dim]Live compare {example.id}: {example.question}[/dim]")
        before = _run_attempt(settings, example, database_path, before_skill, generator, analyzer, max_retries=max_retries)
        after = _run_attempt(settings, example, database_path, after_skill, generator, analyzer, max_retries=max_retries)

        before_correct += int(before.judge.correct)
        after_correct += int(after.judge.correct)
        if not before.judge.correct and after.judge.correct:
            improvements.append(example.id)
            improvements_by_category[after.category or before.category or "unknown"] += 1
        elif before.judge.correct and not after.judge.correct:
            regressions.append(example.id)
            regressions_by_category[after.category or "unknown"] += 1

        rows.append(
            {
                "id": example.id,
                "question": example.question,
                "db_id": example.db_id,
                "difficulty": example.difficulty,
                "before_correct": before.judge.correct,
                "after_correct": after.judge.correct,
                "before_reason": before.judge.reason,
                "after_reason": after.judge.reason,
                "before_category": before.category,
                "after_category": after.category,
                "before_sql": before.sql,
                "after_sql": after.sql,
                "gold_sql": example.gold_sql,
                "before_rows": before.judge.predicted.rows[:5],
                "after_rows": after.judge.predicted.rows[:5],
                "gold_rows": after.judge.gold.rows[:5],
            }
        )
        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(
                    _build_result(
                        dataset_path=dataset_path,
                        before_skill=before_skill,
                        after_skill=after_skill,
                        model=settings.model_name,
                        rows=rows,
                    )
                    | {"status": "partial", "processed": len(rows), "expected": len(examples)},
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

    return _build_result(
        dataset_path=dataset_path,
        before_skill=before_skill,
        after_skill=after_skill,
        model=settings.model_name,
        rows=rows,
    ) | {"status": "complete", "processed": len(rows), "expected": len(examples)}


def _build_result(
    *,
    dataset_path: Path,
    before_skill: Path,
    after_skill: Path,
    model: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    before_correct = sum(1 for row in rows if row["before_correct"])
    after_correct = sum(1 for row in rows if row["after_correct"])
    improvements = [row["id"] for row in rows if not row["before_correct"] and row["after_correct"]]
    regressions = [row["id"] for row in rows if row["before_correct"] and not row["after_correct"]]
    improvements_by_category: Counter[str] = Counter()
    regressions_by_category: Counter[str] = Counter()
    for row in rows:
        if not row["before_correct"] and row["after_correct"]:
            improvements_by_category[row.get("after_category") or row.get("before_category") or "unknown"] += 1
        elif row["before_correct"] and not row["after_correct"]:
            regressions_by_category[row.get("after_category") or "unknown"] += 1

    total = len(rows)
    before_accuracy = before_correct / total if total else 0.0
    after_accuracy = after_correct / total if total else 0.0
    return {
        "benchmark_type": "live_skill_compare",
        "dataset": str(dataset_path),
        "before_skill": str(before_skill),
        "after_skill": str(after_skill),
        "model": model,
        "total": total,
        "before_correct": before_correct,
        "after_correct": after_correct,
        "before_accuracy": before_accuracy,
        "after_accuracy": after_accuracy,
        "accuracy_delta": after_accuracy - before_accuracy,
        "improvements": improvements,
        "regressions": regressions,
        "improvement_total": len(improvements),
        "regression_total": len(regressions),
        "improvements_by_category": dict(improvements_by_category),
        "regressions_by_category": dict(regressions_by_category),
        "rows": rows,
    }


def _run_attempt(
    settings: Settings,
    example: Example,
    database_path: Path,
    skill_path: Path,
    generator: SQLGenerator,
    analyzer: SQLSpecializedAnalyzer,
    max_retries: int = 2,
) -> LiveAttempt:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            sql = generator(settings, example, database_path, skill_path)
            break
        except Exception as exc:  # pragma: no cover - exercised by real API failures.
            last_error = exc
            console.print(
                f"[yellow]Generation failed for {example.id} with {skill_path.name} "
                f"(attempt {attempt + 1}/{max_retries + 1}): {exc}[/yellow]"
            )
    else:
        sql = ""
    judged = judge_sql(database_path, sql, example.gold_sql)
    category = None
    evidence = None
    if last_error is not None and not sql:
        category = "generation_error"
        evidence = str(last_error)
        return LiveAttempt(sql=sql, judge=judged, category=category, evidence=evidence)
    if not judged.correct:
        analysis = analyzer.analyze(example, database_path, sql, judged)
        category = analysis.category
        evidence = analysis.evidence
    return LiveAttempt(sql=sql, judge=judged, category=category, evidence=evidence)


def _generate_with_skill(settings: Settings, example: Example, database_path: Path, skill_path: Path) -> str:
    return generate_sql(
        settings,
        example.question,
        skill_path,
        database_path=database_path,
        evidence=example.evidence,
    )


def _default_output_path(settings: Settings) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return settings.reports_dir / f"live_skill_compare_{stamp}.json"


def _record_regression_memory(result: dict[str, Any], path: Path, *, run_id: str) -> list[dict[str, Any]]:
    store = RegressionMemoryStore.load(path)
    added = store.add_from_live_result(result, run_id=run_id)
    store.write_jsonl(path)
    return added


def _print_summary(result: dict[str, Any], output: Path) -> None:
    table = Table(title="Live Skill Compare")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("model", str(result["model"]))
    table.add_row("examples", str(result["total"]))
    table.add_row("before", f"{result['before_correct']}/{result['total']} ({result['before_accuracy']:.2%})")
    table.add_row("after", f"{result['after_correct']}/{result['total']} ({result['after_accuracy']:.2%})")
    table.add_row("delta", f"{result['accuracy_delta']:+.2%}")
    table.add_row("improvements", json.dumps(result["improvements"], ensure_ascii=False))
    table.add_row("regressions", json.dumps(result["regressions"], ensure_ascii=False))
    table.add_row("improvements by category", json.dumps(result["improvements_by_category"], ensure_ascii=False))
    table.add_row("regressions by category", json.dumps(result["regressions_by_category"], ensure_ascii=False))
    if "regression_memory_added" in result:
        table.add_row("regression memory added", str(result["regression_memory_added"]))
    table.add_row("output", str(output))
    console.print(table)


if __name__ == "__main__":
    main()
