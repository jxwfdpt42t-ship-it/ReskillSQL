from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rich.console import Console


console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare BIRD JSONL files for the evolver.")
    parser.add_argument(
        "--bird-root",
        type=Path,
        default=Path("data/bird"),
        help="Directory containing official BIRD files, e.g. dev.json and database/.",
    )
    parser.add_argument("--split", default="dev", help="BIRD split name, usually dev or train.")
    parser.add_argument("--input", type=Path, default=None, help="Override input JSON path.")
    parser.add_argument("--output", type=Path, default=None, help="Output JSONL path.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--from-result-log",
        type=Path,
        default=None,
        help="Optional old ShapleyRoute result JSON; extracts question/gold/db_path metadata from logs.",
    )
    args = parser.parse_args()

    if args.from_result_log:
        examples = from_result_log(args.from_result_log, limit=args.limit)
        output = args.output or Path("data/bird_cached_eval.jsonl")
    else:
        input_path = args.input or args.bird_root / f"{args.split}.json"
        examples = from_official_bird(input_path, args.bird_root, split=args.split, limit=args.limit)
        output = args.output or Path("data") / f"bird_{args.split}.jsonl"

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for example in examples:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")

    console.print(f"[green]Wrote {len(examples)} BIRD examples to {output}[/green]")


def from_official_bird(input_path: Path, bird_root: Path, split: str, limit: int | None = None) -> list[dict[str, Any]]:
    rows = json.loads(input_path.read_text(encoding="utf-8"))
    examples = []
    for index, row in enumerate(rows):
        db_id = row.get("db_id") or row.get("db_name") or row.get("database_id")
        if not db_id:
            raise ValueError(f"Missing db_id in row {index}")
        gold_sql = row.get("SQL") or row.get("sql") or row.get("query")
        if not gold_sql:
            raise ValueError(f"Missing SQL/gold query in row {index}")

        db_path = _resolve_bird_sqlite_path(input_path, bird_root, db_id)
        examples.append(
            {
                "id": row.get("question_id") or row.get("id") or f"bird_{split}_{index}",
                "question": row["question"],
                "gold_sql": gold_sql,
                "db_id": db_id,
                "db_path": str(db_path),
                "evidence": row.get("evidence"),
                "difficulty": row.get("difficulty"),
                "tags": ["bird", row.get("difficulty") or "unknown"],
            }
        )
        if limit and len(examples) >= limit:
            break
    return examples


def _resolve_bird_sqlite_path(input_path: Path, bird_root: Path, db_id: str) -> Path:
    candidates = [
        bird_root / "database" / db_id / f"{db_id}.sqlite",
        bird_root / "dev_databases" / db_id / f"{db_id}.sqlite",
        input_path.parent / "database" / db_id / f"{db_id}.sqlite",
        input_path.parent / "dev_databases" / db_id / f"{db_id}.sqlite",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def from_result_log(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    logs = data.get("logs") or []
    examples = []
    for index, log in enumerate(logs):
        context = ((log.get("runtime_payload") or {}).get("context") or {})
        gold_sql = context.get("ground_truth") or context.get("sql")
        db_path = context.get("db_path")
        if not gold_sql or not db_path:
            continue
        db_id = Path(db_path).stem
        examples.append(
            {
                "id": log.get("query_id") or context.get("query_id") or f"bird_cached_{index}",
                "question": log.get("question") or context.get("question"),
                "gold_sql": gold_sql,
                "db_id": db_id,
                "db_path": db_path,
                "evidence": context.get("evidence"),
                "difficulty": context.get("difficulty"),
                "tags": ["bird", "cached", context.get("difficulty") or "unknown"],
            }
        )
        if limit and len(examples) >= limit:
            break
    return examples


if __name__ == "__main__":
    main()
