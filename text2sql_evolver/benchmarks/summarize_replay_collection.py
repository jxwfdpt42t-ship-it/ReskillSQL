from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table


console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize multiple compiled skill replay result JSON files.")
    parser.add_argument(
        "--result",
        action="append",
        required=True,
        help="Replay result in label=path form. Can be passed more than once.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Optional collection summary JSON.")
    args = parser.parse_args()

    labeled_results = [_parse_result_arg(value) for value in args.result]
    summary = summarize_collection([(label, _read(path)) for label, path in labeled_results])
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _print_summary(summary, args.output)


def summarize_collection(results: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    splits: list[dict[str, Any]] = []
    category_counter: Counter[str] = Counter()
    total = 0
    before_correct = 0
    after_correct = 0
    improvements: list[str] = []
    regressions: list[str] = []
    changed_count = 0

    for label, result in results:
        compact = _compact(label, result)
        splits.append(compact)
        total += int(compact["total"])
        before_correct += int(compact["before_correct"])
        after_correct += int(compact["after_correct"])
        improvements.extend(compact["improvements"])
        regressions.extend(compact["regressions"])
        changed_count += int(compact["changed_count"])
        category_counter.update(compact["improvements_by_category"])

    before_accuracy = before_correct / total if total else 0.0
    after_accuracy = after_correct / total if total else 0.0
    return {
        "total": total,
        "before_correct": before_correct,
        "after_correct": after_correct,
        "before_accuracy": before_accuracy,
        "after_accuracy": after_accuracy,
        "accuracy_delta": after_accuracy - before_accuracy,
        "improvement_total": len(improvements),
        "regression_total": len(regressions),
        "changed_count": changed_count,
        "improvements": improvements,
        "regressions": regressions,
        "improvements_by_category": dict(category_counter),
        "passes_positive_delta_check": after_correct > before_correct,
        "passes_low_regression_check": len(regressions) <= max(1, len(improvements) // 3),
        "splits": splits,
    }


def _compact(label: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "dataset": result.get("dataset"),
        "total": result.get("total", 0),
        "before_correct": result.get("before_correct", 0),
        "after_correct": result.get("after_correct", 0),
        "before_accuracy": result.get("before_accuracy", 0.0),
        "after_accuracy": result.get("after_accuracy", 0.0),
        "accuracy_delta": result.get("accuracy_delta", 0.0),
        "improvements": result.get("improvements", []),
        "regressions": result.get("regressions", []),
        "improvements_by_category": result.get("improvements_by_category", {}),
        "changed_count": result.get("changed_count", 0),
    }


def _parse_result_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ValueError("--result must use label=path form")
    label, path = value.split("=", 1)
    if not label.strip():
        raise ValueError("--result label cannot be empty")
    return label.strip(), Path(path)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _print_summary(summary: dict[str, Any], output: Path | None) -> None:
    table = Table(title="Compiled Skill Replay Collection")
    table.add_column("Split")
    table.add_column("Before")
    table.add_column("After")
    table.add_column("Delta")
    table.add_column("Improvements")
    table.add_column("Regressions")

    for split in summary["splits"]:
        total = int(split["total"])
        table.add_row(
            split["label"],
            f"{split['before_correct']}/{total} ({split['before_accuracy']:.2%})",
            f"{split['after_correct']}/{total} ({split['after_accuracy']:.2%})",
            f"{split['accuracy_delta']:+.2%}",
            str(len(split["improvements"])),
            str(len(split["regressions"])),
        )

    table.add_row(
        "total",
        f"{summary['before_correct']}/{summary['total']} ({summary['before_accuracy']:.2%})",
        f"{summary['after_correct']}/{summary['total']} ({summary['after_accuracy']:.2%})",
        f"{summary['accuracy_delta']:+.2%}",
        str(summary["improvement_total"]),
        str(summary["regression_total"]),
    )
    table.add_row(
        "checks",
        "-",
        "-",
        "-",
        f"positive_delta={summary['passes_positive_delta_check']}",
        f"low_regression={summary['passes_low_regression_check']}",
    )
    if output:
        table.add_row("output", str(output), "", "", "", "")
    console.print(table)


if __name__ == "__main__":
    main()
