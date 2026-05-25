from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Any

from rich.console import Console

from text2sql_evolver.bird_adapter import from_official_bird
from text2sql_evolver.inner_runner import _apply_projection_check
from text2sql_evolver.judge import judge_sql


console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a controlled projection replay benchmark from BIRD.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/bird/raw/minidev/minidev/MINIDEV/mini_dev_sqlite.json"),
    )
    parser.add_argument(
        "--bird-root",
        type=Path,
        default=Path("data/bird/raw/minidev/minidev/MINIDEV"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/self_update/projection_replay_benchmark"),
    )
    parser.add_argument("--per-split", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260707)
    args = parser.parse_args()

    examples = from_official_bird(args.input, args.bird_root, split="minidev")
    candidates = build_projection_replay_examples(examples)
    required = args.per_split * 3
    if len(candidates) < required:
        raise ValueError(f"Need {required} projection replay examples, found {len(candidates)}")

    rng = random.Random(args.seed)
    rng.shuffle(candidates)
    chosen = candidates[:required]
    splits = {
        "update": chosen[: args.per_split],
        "validation": chosen[args.per_split : args.per_split * 2],
        "holdout": chosen[args.per_split * 2 : args.per_split * 3],
    }
    write_splits(args.output_dir, splits)
    manifest = {
        "source": str(args.input),
        "seed": args.seed,
        "per_split": args.per_split,
        "counts": {name: len(rows) for name, rows in splits.items()},
        "ids": {name: [row["id"] for row in rows] for name, rows in splits.items()},
        "purpose": "Controlled projection replay benchmark: cached predicted SQL includes a condition/helper column in SELECT; compiled Projection Check should remove it.",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[green]Wrote projection replay benchmark to {args.output_dir}[/green]")
    console.print(json.dumps(manifest["counts"], ensure_ascii=False))


def build_projection_replay_examples(examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for example in examples:
        gold_sql = str(example.get("gold_sql") or "")
        condition_column = _condition_column(gold_sql)
        if not condition_column or _question_mentions_condition_column(str(example.get("question") or ""), condition_column):
            continue
        predicted_sql = _add_projection_column(gold_sql, condition_column)
        if not predicted_sql:
            continue
        after_sql = _apply_projection_check(predicted_sql, str(example.get("question") or ""))
        if after_sql == predicted_sql:
            continue
        before = judge_sql(Path(example["db_path"]), predicted_sql, gold_sql)
        after = judge_sql(Path(example["db_path"]), after_sql, gold_sql)
        if before.correct or not after.correct:
            continue
        row = dict(example)
        row["id"] = f"projection_replay_{row['id']}"
        row["predicted_sql"] = predicted_sql
        row["projection_replay"] = {
            "condition_column": condition_column,
            "compiled_after_sql": after_sql,
            "before_reason": before.reason,
            "after_reason": after.reason,
        }
        row["tags"] = list(dict.fromkeys([*row.get("tags", []), "self_update", "projection", "projection_replay"]))
        rows.append(row)
    return rows


def write_splits(output_dir: Path, splits: dict[str, list[dict[str, Any]]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_predictions = []
    for split, rows in splits.items():
        write_jsonl(output_dir / f"{split}.jsonl", rows)
        predictions = [{"id": row["id"], "predicted_sql": row["predicted_sql"]} for row in rows]
        write_jsonl(output_dir / f"{split}_predictions.jsonl", predictions)
        all_predictions.extend(predictions)
    write_jsonl(output_dir / "all_predictions.jsonl", all_predictions)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _condition_column(sql: str) -> str | None:
    if _select_item_count(sql) != 1:
        return None
    where = _clause(sql, "where")
    if not where:
        return None
    match = re.search(r"\b(\w+\.\w+)\b\s*(=|IN\b|LIKE\b|IS\b)", where, re.IGNORECASE)
    return match.group(1) if match else None


def _add_projection_column(sql: str, condition_column: str) -> str | None:
    match = re.search(r"\bSELECT\b(.*?)\bFROM\b", sql, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    select_clause = match.group(1).strip()
    if re.search(r"\bDISTINCT\b", select_clause, re.IGNORECASE):
        return None
    if condition_column.lower() in select_clause.lower():
        return None
    new_select = f" {select_clause}, {condition_column} "
    return sql[: match.start(1)] + new_select + sql[match.end(1) :]


def _select_item_count(sql: str) -> int:
    match = re.search(r"\bSELECT\b(.*?)\bFROM\b", sql, re.IGNORECASE | re.DOTALL)
    if not match:
        return 0
    clause = match.group(1)
    depth = 0
    count = 1 if clause.strip() else 0
    for char in clause:
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            count += 1
    return count


def _clause(sql: str, clause: str) -> str:
    next_clause = r"\b(GROUP\s+BY|ORDER\s+BY|LIMIT|HAVING|UNION|EXCEPT|INTERSECT)\b"
    pattern = r"\b" + re.escape(clause) + r"\b(.*?)(?:" + next_clause + r"|$)"
    match = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def _question_mentions_condition_column(question: str, condition_column: str) -> bool:
    name = condition_column.split(".")[-1].lower()
    return bool(re.search(r"\b" + re.escape(name) + r"\b", question.lower()))


if __name__ == "__main__":
    main()
