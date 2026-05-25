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
    parser = argparse.ArgumentParser(description="Summarize a self-update evolver report.")
    parser.add_argument("run_dir", type=Path, help="Report directory, e.g. reports/round-...")
    args = parser.parse_args()

    summary = _read_json(args.run_dir / "summary.json")
    table = Table(title=f"Self-Update Summary: {args.run_dir.name}")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("update accuracy", _pct(summary.get("accuracy")))
    table.add_row("update failures", json.dumps(summary.get("failure_counts", {}), ensure_ascii=False))
    table.add_row("fix routes", json.dumps(summary.get("fix_route_counts", {}), ensure_ascii=False))
    table.add_row("supported categories", json.dumps((summary.get("weighted_support") or {}).get("supported_categories", []), ensure_ascii=False))
    table.add_row("patch decision", str(summary.get("patch_decision")))
    table.add_row("candidate patch count", str(summary.get("candidate_patch_count")))
    console.print(table)

    patch_path = args.run_dir / "skill_patch.md"
    if patch_path.exists():
        console.print("\n[bold]Patch[/bold]")
        console.print(patch_path.read_text(encoding="utf-8").strip())

    before_path = args.run_dir / "validation_before.json"
    after_path = args.run_dir / "validation_after.json"
    if before_path.exists() and after_path.exists():
        before = _read_json(before_path)
        after = _read_json(after_path)
        _print_validation_delta(before, after)


def _print_validation_delta(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> None:
    before_acc = _accuracy(before)
    after_acc = _accuracy(after)
    before_failures = _failure_counts(before)
    after_failures = _failure_counts(after)
    before_by_id = {str(row["id"]): row for row in before}
    improvements = []
    regressions = []
    for row in after:
        previous = before_by_id[str(row["id"])]
        if not previous["correct"] and row["correct"]:
            improvements.append(row)
        elif previous["correct"] and not row["correct"]:
            regressions.append(row)

    table = Table(title="Validation Before/After")
    table.add_column("Metric")
    table.add_column("Before")
    table.add_column("After")
    table.add_column("Delta")
    table.add_row("accuracy", _pct(before_acc), _pct(after_acc), _signed_pct(after_acc - before_acc))
    table.add_row("failures", json.dumps(before_failures, ensure_ascii=False), json.dumps(after_failures, ensure_ascii=False), "")
    table.add_row("improved examples", "-", str(len(improvements)), "")
    table.add_row("regressed examples", "-", str(len(regressions)), "")
    console.print(table)

    if improvements:
        console.print("[green]Improvements[/green]")
        for row in improvements[:8]:
            previous = before_by_id[str(row["id"])]
            console.print(f"  + {row['id']}: {previous.get('category')} -> correct | {row['question'][:100]}")
    if regressions:
        console.print("[red]Regressions[/red]")
        for row in regressions[:8]:
            console.print(f"  - {row['id']}: correct -> {row.get('category')} | {row['question'][:100]}")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _accuracy(rows: list[dict[str, Any]]) -> float:
    return sum(1 for row in rows if row.get("correct")) / len(rows) if rows else 0.0


def _failure_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(str(row.get("category") or "unknown") for row in rows if not row.get("correct")))


def _pct(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.2%}"


def _signed_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2%}"


if __name__ == "__main__":
    main()
