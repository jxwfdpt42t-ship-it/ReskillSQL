from __future__ import annotations

from text2sql_evolver.core.state import EvolutionRound
from text2sql_evolver.utils.io import write_text


class MarkdownReporter:
    def write(self, round_result: EvolutionRound) -> None:
        lines = [
            "# Evolution Round Report",
            "",
            f"- Model: `{round_result.summary.get('model')}`",
            f"- Examples: `{round_result.summary.get('num_examples')}`",
            f"- Accuracy: `{round_result.summary.get('accuracy'):.2%}`",
            f"- Failure counts: `{round_result.summary.get('failure_counts')}`",
            f"- Patch decision: `{round_result.summary.get('patch_decision')}`",
            f"- Auto apply: `{round_result.summary.get('auto_apply')}`",
            f"- Patch budget: `{round_result.summary.get('patch_budget')}`",
            f"- Failure routing: `{round_result.summary.get('failure_routing')}`",
            f"- Weighted support: `{round_result.summary.get('weighted_support')}`",
        ]
        gate_metrics = round_result.summary.get("sql_aware_gate_metrics")
        if gate_metrics:
            lines.append(f"- SQL-aware gate: `{gate_metrics}`")
        candidate_paths = round_result.summary.get("candidate_paths") or {}
        if candidate_paths:
            lines.append(f"- Candidate skill: `{candidate_paths.get('candidate_skill')}`")
            lines.append(f"- Candidate diff: `{candidate_paths.get('candidate_diff')}`")
        if round_result.summary.get("skill_version"):
            lines.append(f"- Skill version: `{round_result.summary.get('skill_version')}`")
        if round_result.summary.get("best_skill_path"):
            lines.append(f"- Best skill: `{round_result.summary.get('best_skill_path')}`")
        if round_result.skill_backup:
            lines.append(f"- Skill backup: `{round_result.skill_backup}`")
        write_text(round_result.run_dir / "report.md", "\n".join(lines) + "\n")
