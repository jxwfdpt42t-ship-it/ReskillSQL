from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from text2sql_evolver.benchmarks.splits import deterministic_split, write_split_jsonl
from text2sql_evolver.config import load_settings
from text2sql_evolver.dataset import load_jsonl
from text2sql_evolver.utils.paths import resolve_dataset_path


console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create update/validation/holdout splits for self-update experiments.")
    parser.add_argument("--dataset", required=True, help="Input JSONL dataset.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/self_update"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--update-ratio", type=float, default=0.4)
    parser.add_argument("--validation-ratio", type=float, default=0.3)
    args = parser.parse_args()

    settings = load_settings()
    dataset_path = resolve_dataset_path(settings.dataset_path, args.dataset)
    examples = load_jsonl(dataset_path)
    update, validation, holdout = deterministic_split(
        examples,
        update_ratio=args.update_ratio,
        validation_ratio=args.validation_ratio,
        seed=args.seed,
    )
    write_split_jsonl(args.output_dir / "update.jsonl", update)
    write_split_jsonl(args.output_dir / "validation.jsonl", validation)
    write_split_jsonl(args.output_dir / "holdout.jsonl", holdout)
    console.print(
        f"[green]Wrote self-update splits to {args.output_dir}: "
        f"update={len(update)} validation={len(validation)} holdout={len(holdout)}[/green]"
    )


if __name__ == "__main__":
    main()
