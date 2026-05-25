from __future__ import annotations

import argparse
import json

from rich.console import Console
from rich.table import Table

from .analyzers.sql_specialized import SQLSpecializedAnalyzer
from .config import load_settings
from .core.orchestrator import EvolutionOrchestrator
from .dataset import load_jsonl
from .editors.patch_budget import PatchBudget
from .editors.patch_generator import SkillPatchGenerator
from .runners.cached_runner import CachedRunner
from .runners.llm_runner import LLMRunner
from .utils.io import load_prediction_jsonl
from .utils.paths import resolve_dataset_path


console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one Text-to-SQL evolver validation round.")
    parser.add_argument("--limit", type=int, default=10, help="Number of examples to run.")
    parser.add_argument("--dataset", type=str, default=None, help="JSONL dataset path.")
    parser.add_argument("--predictions", type=str, default=None, help="Optional JSONL with id and predicted_sql.")
    parser.add_argument("--apply-skill-patch", action="store_true", help="Write learned rules into skills/query-writing/SKILL.md.")
    parser.add_argument("--auto-apply", action="store_true", help="Automatically promote a candidate skill only after validation gate passes.")
    parser.add_argument("--max-skill-edits", type=int, default=3, help="Maximum learned-rule bullets accepted in one round.")
    parser.add_argument("--validation-dataset", type=str, default=None, help="Optional holdout JSONL used to validate and auto-rollback skill patches.")
    parser.add_argument("--validation-limit", type=int, default=None, help="Number of validation examples to run.")
    parser.add_argument("--validation-min-delta", type=float, default=0.0, help="Minimum validation accuracy delta required to keep a patch.")
    parser.add_argument("--gate-min-score", type=int, default=4, help="Minimum SQL-aware scorecard points required to accept a candidate skill.")
    parser.add_argument("--require-target-improvement", action="store_true", help="Require target SQL error category count to decrease on validation.")
    args = parser.parse_args()

    settings = load_settings()
    dataset_path = resolve_dataset_path(settings.dataset_path, args.dataset)
    examples = load_jsonl(dataset_path, limit=args.limit)
    validation_path = resolve_dataset_path(settings.dataset_path, args.validation_dataset) if args.validation_dataset else None
    validation_examples = load_jsonl(validation_path, limit=args.validation_limit) if validation_path else None
    llm_runner = LLMRunner(settings)
    runner = CachedRunner(load_prediction_jsonl(args.predictions), fallback=llm_runner)
    orchestrator = EvolutionOrchestrator(
        settings=settings,
        runner=runner,
        analyzer=SQLSpecializedAnalyzer(),
        patch_generator=SkillPatchGenerator(settings),
        patch_budget=PatchBudget(args.max_skill_edits),
        console=console,
    )
    round_result = orchestrator.run(
        examples,
        dataset_path=str(dataset_path),
        apply_skill_patch=args.apply_skill_patch,
        auto_apply=args.auto_apply,
        validation_examples=validation_examples,
        validation_dataset_path=str(validation_path) if validation_path else None,
        validation_min_delta=args.validation_min_delta,
        gate_min_score=args.gate_min_score,
        require_target_improvement=args.require_target_improvement,
    )
    _print_summary(round_result.summary, round_result.run_dir, bool(args.apply_skill_patch), round_result.skill_backup)


def _print_summary(summary: dict, run_dir, applied: bool, backup_path) -> None:
    table = Table(title="Text-to-SQL Evolver Round")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Model", str(summary["model"]))
    table.add_row("Examples", str(summary["num_examples"]))
    table.add_row("Accuracy", f"{summary['accuracy']:.2%}")
    table.add_row("Failures", json.dumps(summary["failure_counts"], ensure_ascii=False))
    table.add_row("Report", str(run_dir))
    if applied:
        table.add_row("Skill backup", str(backup_path))
    console.print(table)


if __name__ == "__main__":
    main()
