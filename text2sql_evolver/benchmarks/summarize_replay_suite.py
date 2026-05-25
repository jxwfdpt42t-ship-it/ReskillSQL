from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table


console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize update/holdout replay benchmark results.")
    parser.add_argument("--update", required=True, type=Path, help="Update replay result JSON.")
    parser.add_argument("--holdout", required=True, type=Path, help="Holdout replay result JSON.")
    parser.add_argument("--output", type=Path, default=None, help="Optional suite summary JSON.")
    args = parser.parse_args()

    summary = summarize_suite(_read(args.update), _read(args.holdout))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _print_summary(summary, args.output)


def summarize_suite(update: dict[str, Any], holdout: dict[str, Any]) -> dict[str, Any]:
    return {
        "update": _compact(update),
        "holdout": _compact(holdout),
        "regression_total": len(update.get("regressions", [])) + len(holdout.get("regressions", [])),
        "improvement_total": len(update.get("improvements", [])) + len(holdout.get("improvements", [])),
        "categories_improved": sorted(
            set(update.get("improvements_by_category", {})) | set(holdout.get("improvements_by_category", {}))
        ),
        "passes_no_regression_check": not update.get("regressions") and not holdout.get("regressions"),
        "passes_holdout_positive_check": float(holdout.get("accuracy_delta", 0.0)) > 0,
    }


def _compact(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset": result.get("dataset"),
        "total": result.get("total"),
        "before_correct": result.get("before_correct"),
        "after_correct": result.get("after_correct"),
        "before_accuracy": result.get("before_accuracy"),
        "after_accuracy": result.get("after_accuracy"),
        "accuracy_delta": result.get("accuracy_delta"),
        "improvements": result.get("improvements", []),
        "regressions": result.get("regressions", []),
        "improvements_by_category": result.get("improvements_by_category", {}),
    }


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _print_summary(summary: dict[str, Any], output: Path | None) -> None:
    table = Table(title="Self-Update Replay Suite")
    table.add_column("Split")
    table.add_column("Before")
    table.add_column("After")
    table.add_column("Delta")
    table.add_column("Improvements")
    table.add_column("Regressions")
    for split in ("update", "holdout"):
        row = summary[split]
        total = row["total"]
        table.add_row(
            split,
            f"{row['before_correct']}/{total} ({row['before_accuracy']:.2%})",
            f"{row['after_correct']}/{total} ({row['after_accuracy']:.2%})",
            f"{row['accuracy_delta']:+.2%}",
            json.dumps(row["improvements"], ensure_ascii=False),
            json.dumps(row["regressions"], ensure_ascii=False),
        )
    table.add_row("checks", "-", "-", "-", f"no_regression={summary['passes_no_regression_check']}", f"holdout_positive={summary['passes_holdout_positive_check']}")
    if output:
        table.add_row("output", str(output), "", "", "", "")
    console.print(table)


if __name__ == "__main__":
    main()
