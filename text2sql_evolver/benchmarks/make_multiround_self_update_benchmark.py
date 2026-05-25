from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table


console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="Split a 500-item self-update benchmark into multi-round updates.")
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path("data/self_update/generated_transfer_500"),
        help="Generated transfer benchmark directory containing combined/*.jsonl.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/self_update/generated_transfer_500_multiround"),
        help="Output directory for round_1/round_2/round_3 splits.",
    )
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260719)
    parser.add_argument("--update-ratio", type=float, default=0.4)
    parser.add_argument("--validation-ratio", type=float, default=0.3)
    args = parser.parse_args()

    summary = build_multiround_benchmark(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        rounds=args.rounds,
        seed=args.seed,
        update_ratio=args.update_ratio,
        validation_ratio=args.validation_ratio,
    )
    _print_summary(summary)


def build_multiround_benchmark(
    *,
    source_dir: Path,
    output_dir: Path,
    rounds: int = 3,
    seed: int = 20260719,
    update_ratio: float = 0.4,
    validation_ratio: float = 0.3,
) -> dict[str, Any]:
    rows = _load_source_rows(source_dir)
    by_round = _assign_rounds(rows, rounds=rounds, seed=seed)
    round_splits = {
        round_name: _split_round(rows, seed=seed + index, update_ratio=update_ratio, validation_ratio=validation_ratio)
        for index, (round_name, rows) in enumerate(sorted(by_round.items()), start=1)
    }
    _write_rounds(output_dir, round_splits)
    summary = _summary(
        source_dir=source_dir,
        output_dir=output_dir,
        rounds=rounds,
        seed=seed,
        rows=rows,
        round_splits=round_splits,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def _load_source_rows(source_dir: Path) -> list[dict[str, Any]]:
    combined = source_dir / "combined"
    rows: list[dict[str, Any]] = []
    seen: Counter[str] = Counter()
    for split in ("update", "validation", "holdout"):
        path = combined / f"{split}.jsonl"
        for row in _read_jsonl(path):
            copied = dict(row)
            original_id = str(copied["id"])
            seen[original_id] += 1
            if seen[original_id] > 1:
                copied["original_id"] = original_id
                copied["id"] = f"{original_id}__dup{seen[original_id]}"
            rows.append(copied)
    return sorted(rows, key=lambda row: _source_sort_key(str(row.get("source_id") or row["id"])))


def _assign_rounds(rows: list[dict[str, Any]], *, rounds: int, seed: int) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(seed)
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get("category") or "unknown")].append(row)

    by_round = {f"round_{index}": [] for index in range(1, rounds + 1)}
    for category_rows in buckets.values():
        shuffled = list(category_rows)
        rng.shuffle(shuffled)
        for index, row in enumerate(shuffled):
            by_round[f"round_{(index % rounds) + 1}"].append(row)

    for round_rows in by_round.values():
        round_rows.sort(key=lambda row: _source_sort_key(str(row.get("source_id") or row["id"])))
    return by_round


def _split_round(
    rows: list[dict[str, Any]],
    *,
    seed: int,
    update_ratio: float,
    validation_ratio: float,
) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(seed)
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_category[str(row.get("category") or "unknown")].append(row)

    splits = {"update": [], "validation": [], "holdout": []}
    for category_rows in by_category.values():
        shuffled = list(category_rows)
        rng.shuffle(shuffled)
        update_end = round(len(shuffled) * update_ratio)
        validation_end = update_end + round(len(shuffled) * validation_ratio)
        splits["update"].extend(shuffled[:update_end])
        splits["validation"].extend(shuffled[update_end:validation_end])
        splits["holdout"].extend(shuffled[validation_end:])

    for rows_in_split in splits.values():
        rows_in_split.sort(key=lambda row: _source_sort_key(str(row.get("source_id") or row["id"])))
    return splits


def _write_rounds(output_dir: Path, round_splits: dict[str, dict[str, list[dict[str, Any]]]]) -> None:
    for round_name, splits in round_splits.items():
        for split, rows in splits.items():
            _write_jsonl(output_dir / round_name / f"{split}.jsonl", rows)
            validated_rows = [row for row in rows if row.get("validated", True)]
            _write_jsonl(output_dir / round_name / "validated_only" / f"{split}.jsonl", validated_rows)
            by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                by_category[str(row.get("category") or "unknown")].append(row)
            for category, category_rows in by_category.items():
                _write_jsonl(output_dir / round_name / category / f"{split}.jsonl", category_rows)


def _summary(
    *,
    source_dir: Path,
    output_dir: Path,
    rounds: int,
    seed: int,
    rows: list[dict[str, Any]],
    round_splits: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    round_summaries = {}
    for round_name, splits in round_splits.items():
        all_round_rows = [row for split_rows in splits.values() for row in split_rows]
        round_summaries[round_name] = {
            "total": len(all_round_rows),
            "validated": sum(1 for row in all_round_rows if row.get("validated", True)),
            "split_counts": {split: len(split_rows) for split, split_rows in splits.items()},
            "validated_split_counts": {
                split: sum(1 for row in split_rows if row.get("validated", True))
                for split, split_rows in splits.items()
            },
            "category_counts": dict(Counter(str(row.get("category") or "unknown") for row in all_round_rows)),
        }
    return {
        "name": "generated_transfer_500_multiround",
        "source_dir": str(source_dir),
        "output_dir": str(output_dir),
        "rounds": rounds,
        "seed": seed,
        "total": len(rows),
        "validated": sum(1 for row in rows if row.get("validated", True)),
        "category_counts": dict(Counter(str(row.get("category") or "unknown") for row in rows)),
        "round_summaries": round_summaries,
        "purpose": (
            "Evaluate multi-round self-update behavior: each round has update, validation, and holdout splits "
            "so the benchmark measures skill evolution over time instead of one-shot final SQL accuracy."
        ),
        "metrics_to_report": [
            "accuracy_delta",
            "regression_count",
            "failure_avoidance_rate",
            "category_transfer_gain",
            "skill_length_words",
            "estimated_model_calls",
            "estimated_tokens",
        ],
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _source_sort_key(source_id: str) -> tuple[int, int | str]:
    return (0, int(source_id)) if source_id.isdigit() else (1, source_id)


def _print_summary(summary: dict[str, Any]) -> None:
    table = Table(title="Multi-Round Self-Update Benchmark")
    table.add_column("Round")
    table.add_column("Total")
    table.add_column("Validated")
    table.add_column("Splits")
    for round_name, row in summary["round_summaries"].items():
        table.add_row(
            round_name,
            str(row["total"]),
            str(row["validated"]),
            json.dumps(row["split_counts"], ensure_ascii=False),
        )
    console.print(table)
    console.print(f"[green]Wrote {summary['total']} examples to {summary['output_dir']}[/green]")


if __name__ == "__main__":
    main()
