from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from text2sql_evolver.benchmarks.make_sql_skill_benchmark import classify_example
from text2sql_evolver.bird_adapter import from_official_bird
from text2sql_evolver.judge import execute_sql


console = Console()

SKILL_TARGETS = {
    "ordering_limit": "Ranking questions should make the requested order, row count, and tie-break behavior explicit.",
    "ratio_numeric": "Ratio, rate, and percentage questions should use the correct numerator, denominator, casts, and denominator guard.",
    "aggregation_projection": "Aggregate questions should choose the right aggregate and return only the requested output columns.",
    "value_grounding": "Filter values should match the literal values stored in the database, not only the surface form in the question.",
    "schema_linking": "The SQL should choose the correct tables, columns, and join path before writing predicates.",
    "filtering": "The SQL should preserve every requested condition and avoid adding unsupported filters.",
    "semantic_mismatch": "The SQL should preserve the full intent when no narrower detector category is confident.",
}

QUESTION_PREFIXES = {
    "ordering_limit": "Ranking transfer challenge. Return the requested ordered result with the correct row count: ",
    "ratio_numeric": "Numeric reasoning transfer challenge. Compute the requested ratio, rate, percentage, or average exactly: ",
    "aggregation_projection": "Aggregation and result-shape transfer challenge. Return only the requested final answer: ",
    "value_grounding": "Value grounding transfer challenge. Match filters to stored database values: ",
    "schema_linking": "Schema linking transfer challenge. Use the correct tables, columns, and joins: ",
    "filtering": "Filtering transfer challenge. Apply every condition in the question exactly: ",
    "semantic_mismatch": "General SQL transfer challenge. Answer the question exactly: ",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a 500-question generated transfer benchmark for self-update evaluation."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/bird/raw/minidev/minidev/MINIDEV/mini_dev_sqlite.json"),
        help="Official BIRD MiniDev SQLite JSON file.",
    )
    parser.add_argument(
        "--bird-root",
        type=Path,
        default=Path("data/bird/raw/minidev/minidev/MINIDEV"),
        help="BIRD root containing dev_databases/.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/self_update/generated_transfer_500"),
        help="Directory where generated transfer splits are written.",
    )
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20260713)
    parser.add_argument("--update-ratio", type=float, default=0.4)
    parser.add_argument("--validation-ratio", type=float, default=0.3)
    args = parser.parse_args()

    summary = build_generated_transfer_benchmark(
        input_path=args.input,
        bird_root=args.bird_root,
        output_dir=args.output_dir,
        limit=args.limit,
        seed=args.seed,
        update_ratio=args.update_ratio,
        validation_ratio=args.validation_ratio,
    )
    _print_summary(summary)


def build_generated_transfer_benchmark(
    *,
    input_path: Path,
    bird_root: Path,
    output_dir: Path,
    limit: int,
    seed: int,
    update_ratio: float = 0.4,
    validation_ratio: float = 0.3,
) -> dict[str, Any]:
    source_examples = from_official_bird(input_path, bird_root, split="minidev", limit=limit)
    generated_rows = [_make_transfer_row(row) for row in source_examples]
    validated_rows = [_validate_row(row) for row in generated_rows]
    splits = _stratified_split(validated_rows, seed=seed, update_ratio=update_ratio, validation_ratio=validation_ratio)
    _write_splits(output_dir, splits)
    summary = _summary(
        input_path=input_path,
        bird_root=bird_root,
        output_dir=output_dir,
        seed=seed,
        rows=validated_rows,
        splits=splits,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def _make_transfer_row(source: dict[str, Any]) -> dict[str, Any]:
    category = classify_example(source) or _fallback_category(source)
    source_id = str(source["id"])
    question = str(source["question"])
    return {
        "id": f"generated_transfer_{source_id}",
        "source_id": source_id,
        "source_question": question,
        "question": f"{QUESTION_PREFIXES[category]}{question}",
        "gold_sql": source["gold_sql"],
        "db_id": source.get("db_id"),
        "db_path": source.get("db_path"),
        "evidence": source.get("evidence"),
        "difficulty": source.get("difficulty"),
        "category": category,
        "skill_target": SKILL_TARGETS[category],
        "generation_method": "deterministic_category_transfer_prompt",
        "tags": [
            "bird",
            "self_update",
            "generated_transfer",
            category,
            source.get("difficulty") or "unknown",
        ],
    }


def _fallback_category(source: dict[str, Any]) -> str:
    question = str(source.get("question") or "").lower()
    sql = str(source.get("gold_sql") or "").lower()
    evidence = str(source.get("evidence") or "").lower()
    combined = f"{question} {evidence}"

    if any(token in combined for token in ("where", "whose", "with ", "without ", "between", "older than", "younger than")):
        return "filtering"
    if " join " in sql or " inner join " in sql or " left join " in sql:
        return "schema_linking"
    if any(token in combined for token in (" named ", " called ", " code ", " id ", " country ", "state ", "city ")):
        return "value_grounding"
    return "semantic_mismatch"


def _validate_row(row: dict[str, Any]) -> dict[str, Any]:
    result = execute_sql(Path(str(row["db_path"])), str(row["gold_sql"]))
    checked = dict(row)
    checked["validated"] = result.ok
    checked["validation_error"] = result.error
    checked["gold_row_count"] = len(result.rows)
    checked["gold_column_count"] = len(result.rows[0]) if result.rows else 0
    return checked


def _stratified_split(
    rows: list[dict[str, Any]],
    *,
    seed: int,
    update_ratio: float,
    validation_ratio: float,
) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(seed)
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_category[str(row["category"])].append(row)

    splits: dict[str, list[dict[str, Any]]] = {"update": [], "validation": [], "holdout": []}
    for category_rows in by_category.values():
        shuffled = list(category_rows)
        rng.shuffle(shuffled)
        update_end = round(len(shuffled) * update_ratio)
        validation_end = update_end + round(len(shuffled) * validation_ratio)
        splits["update"].extend(shuffled[:update_end])
        splits["validation"].extend(shuffled[update_end:validation_end])
        splits["holdout"].extend(shuffled[validation_end:])

    for split_rows in splits.values():
        split_rows.sort(key=lambda item: _stable_source_sort_key(str(item["source_id"])))
    return splits


def _stable_source_sort_key(source_id: str) -> tuple[int, int | str]:
    return (0, int(source_id)) if source_id.isdigit() else (1, source_id)


def _write_splits(output_dir: Path, splits: dict[str, list[dict[str, Any]]]) -> None:
    for split, rows in splits.items():
        _write_jsonl(output_dir / "combined" / f"{split}.jsonl", rows)
        category_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            category_rows[str(row["category"])].append(row)
        for category, bucket in category_rows.items():
            _write_jsonl(output_dir / category / f"{split}.jsonl", bucket)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _summary(
    *,
    input_path: Path,
    bird_root: Path,
    output_dir: Path,
    seed: int,
    rows: list[dict[str, Any]],
    splits: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    split_counts = {split: len(split_rows) for split, split_rows in splits.items()}
    category_counts = Counter(str(row["category"]) for row in rows)
    category_split_counts = {
        category: {
            split: sum(1 for row in split_rows if row["category"] == category)
            for split, split_rows in splits.items()
        }
        for category in sorted(category_counts)
    }
    validated_count = sum(1 for row in rows if row["validated"])
    return {
        "name": "generated_transfer_500",
        "source": str(input_path),
        "bird_root": str(bird_root),
        "output_dir": str(output_dir),
        "seed": seed,
        "total": len(rows),
        "validated": validated_count,
        "invalid": len(rows) - validated_count,
        "split_counts": split_counts,
        "category_counts": dict(category_counts),
        "category_split_counts": category_split_counts,
        "generation_method": "deterministic category-conditioned transfer prompts over BIRD MiniDev gold SQL",
        "purpose": (
            "Evaluate whether a reskilled query-writing policy transfers to category-targeted, "
            "held-out Text-to-SQL challenges instead of only repairing the original update failures."
        ),
        "metrics_to_report": [
            "old_skill_accuracy",
            "new_skill_accuracy",
            "transfer_gain",
            "target_category_reduction",
            "regression_count",
            "generated_task_validation_rate",
        ],
    }


def _print_summary(summary: dict[str, Any]) -> None:
    table = Table(title="Generated Transfer Benchmark")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("output", summary["output_dir"])
    table.add_row("total", str(summary["total"]))
    table.add_row("validated", f"{summary['validated']}/{summary['total']}")
    table.add_row("splits", json.dumps(summary["split_counts"], ensure_ascii=False))
    table.add_row("categories", json.dumps(summary["category_counts"], ensure_ascii=False))
    console.print(table)


if __name__ == "__main__":
    main()
