from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from rich.console import Console

from text2sql_evolver.bird_adapter import from_official_bird


console = Console()

CATEGORIES = ("ordering_limit", "ratio_numeric", "aggregation_projection")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SQL-skill self-update benchmark splits from BIRD.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/bird/raw/minidev/minidev/MINIDEV/mini_dev_sqlite.json"),
        help="BIRD SQLite JSON file.",
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
        default=Path("data/self_update/sql_skill_benchmark"),
        help="Directory where benchmark splits are written.",
    )
    parser.add_argument("--per-split", type=int, default=8, help="Examples per category per split.")
    parser.add_argument("--seed", type=int, default=20260702)
    parser.add_argument(
        "--categories",
        nargs="+",
        default=list(CATEGORIES),
        choices=list(CATEGORIES),
        help="Categories to include.",
    )
    parser.add_argument(
        "--from-report",
        type=Path,
        action="append",
        default=[],
        help="Optional evolver report directory. When set, build buckets from actual failed examples in reports.",
    )
    args = parser.parse_args()

    examples = (
        examples_from_failure_reports(args.from_report)
        if args.from_report
        else from_official_bird(args.input, args.bird_root, split="minidev")
    )
    categories = tuple(args.categories)
    buckets = build_buckets(examples, categories=categories)
    splits = split_buckets(buckets, per_split=args.per_split, seed=args.seed, categories=categories)
    write_benchmark(args.output_dir, splits)
    write_manifest(args.output_dir, args, splits)

    console.print(f"[green]Wrote SQL-skill self-update benchmark to {args.output_dir}[/green]")
    for category in categories:
        counts = {split: len(rows) for split, rows in splits[category].items()}
        console.print(f"  {category}: {counts}")
    combined_counts = {split: sum(len(splits[category][split]) for category in categories) for split in ("update", "validation", "holdout")}
    console.print(f"  combined: {combined_counts}")


def build_buckets(examples: list[dict[str, Any]], *, categories: tuple[str, ...] = CATEGORIES) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for example in examples:
        category = classify_example(example)
        if not category or category not in categories:
            continue
        row = dict(example)
        row["id"] = str(row["id"])
        row["tags"] = list(dict.fromkeys([*row.get("tags", []), "self_update", category]))
        buckets[category].append(row)
    return {category: buckets.get(category, []) for category in categories}


def classify_example(example: dict[str, Any]) -> str | None:
    actual_category = _map_actual_failure_category(str(example.get("category") or ""))
    if actual_category:
        return actual_category

    question = str(example.get("question") or "")
    evidence = str(example.get("evidence") or "")
    sql = str(example.get("gold_sql") or "")
    text = f"{question} {evidence}".lower()
    sql_l = sql.lower()

    if _is_ratio_numeric(text, sql_l):
        return "ratio_numeric"
    if _is_ordering_limit(text, sql_l):
        return "ordering_limit"
    if _is_aggregation_projection(text, sql_l):
        return "aggregation_projection"
    return None


def examples_from_failure_reports(report_dirs: list[Path]) -> list[dict[str, Any]]:
    examples = []
    seen = set()
    for report_dir in report_dirs:
        for name in ("examples.json", "validation_before.json"):
            path = report_dir / name
            if not path.exists():
                continue
            rows = json.loads(path.read_text(encoding="utf-8"))
            for row in rows:
                mapped = _map_actual_failure_category(str(row.get("category") or ""))
                if row.get("correct") or not mapped:
                    continue
                example_id = str(row["id"])
                if example_id in seen:
                    continue
                seen.add(example_id)
                examples.append(
                    {
                        "id": example_id,
                        "question": row["question"],
                        "gold_sql": row["gold_sql"],
                        "db_id": row.get("db_id"),
                        "db_path": row.get("db_path"),
                        "evidence": row.get("evidence"),
                        "difficulty": row.get("difficulty"),
                        "predicted_sql": row.get("predicted_sql"),
                        "category": mapped,
                        "tags": ["bird", "self_update", "actual_failure", mapped],
                    }
                )
    return examples


def _map_actual_failure_category(category: str) -> str | None:
    if category in {"ordering_limit", "ratio_numeric"}:
        return category
    if category in {"aggregation", "projection", "result_shape"}:
        return "aggregation_projection"
    return None


def split_buckets(
    buckets: dict[str, list[dict[str, Any]]],
    *,
    per_split: int,
    seed: int,
    categories: tuple[str, ...] = CATEGORIES,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    required = per_split * 3
    rng = random.Random(seed)
    splits: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for category in categories:
        rows = list(buckets.get(category, []))
        if len(rows) < required:
            raise ValueError(f"Not enough {category} examples: need {required}, found {len(rows)}")
        rng.shuffle(rows)
        chosen = rows[:required]
        splits[category] = {
            "update": chosen[:per_split],
            "validation": chosen[per_split : per_split * 2],
            "holdout": chosen[per_split * 2 : per_split * 3],
        }
    return splits


def write_benchmark(output_dir: Path, splits: dict[str, dict[str, list[dict[str, Any]]]]) -> None:
    combined: dict[str, list[dict[str, Any]]] = {"update": [], "validation": [], "holdout": []}
    for category, category_splits in splits.items():
        for split, rows in category_splits.items():
            write_jsonl(output_dir / category / f"{split}.jsonl", rows)
            write_predictions_jsonl(output_dir / category / f"{split}_predictions.jsonl", rows)
            combined[split].extend(rows)
    for split, rows in combined.items():
        write_jsonl(output_dir / "combined" / f"{split}.jsonl", rows)
        write_predictions_jsonl(output_dir / "combined" / f"{split}_predictions.jsonl", rows)


def write_manifest(
    output_dir: Path,
    args: argparse.Namespace,
    splits: dict[str, dict[str, list[dict[str, Any]]]],
) -> None:
    manifest = {
        "source": str(args.input),
        "bird_root": str(args.bird_root),
        "per_split": args.per_split,
        "seed": args.seed,
        "categories": {
            category: {
                split: [row["id"] for row in rows]
                for split, rows in category_splits.items()
            }
            for category, category_splits in splits.items()
        },
        "included_categories": list(splits.keys()),
        "purpose": {
            "ordering_limit": "Tests whether learned rules improve ranking, ORDER BY direction, LIMIT, and tie-break behavior.",
            "ratio_numeric": "Tests whether learned rules improve percentages, ratios, denominator handling, and numeric formulas.",
            "aggregation_projection": "Tests whether learned rules improve aggregate choice, GROUP BY, and selected output columns.",
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_predictions_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    prediction_rows = [
        {"id": row["id"], "predicted_sql": row["predicted_sql"]}
        for row in rows
        if row.get("predicted_sql")
    ]
    if not prediction_rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in prediction_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _is_ratio_numeric(text: str, sql: str) -> bool:
    if re.search(r"\b(ratio|percentage|percent|rate|per\s+cent|how many percent)\b", text):
        return True
    if "/" in sql and re.search(r"\b(sum|count|avg|cast|round|iif|case)\b", sql):
        return True
    return False


def _is_ordering_limit(text: str, sql: str) -> bool:
    ranking_words = r"\b(top|bottom|highest|lowest|most|least|maximum|minimum|first|last|latest|earliest|oldest|youngest)\b"
    if re.search(ranking_words, text) and "order by" in sql and "limit" in sql:
        return True
    return "order by" in sql and "limit" in sql


def _is_aggregation_projection(text: str, sql: str) -> bool:
    aggregate_words = r"\b(count|how many|average|avg|sum|total|number of|difference|more than|less than)\b"
    has_aggregate_sql = bool(re.search(r"\b(count|sum|avg|min|max)\s*\(", sql))
    has_group_by = "group by" in sql
    return has_group_by or has_aggregate_sql or bool(re.search(aggregate_words, text))


if __name__ == "__main__":
    main()
