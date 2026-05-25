from __future__ import annotations

from pathlib import Path

from text2sql_evolver.core.state import EvolutionRound
from text2sql_evolver.utils.io import write_json, write_text


class JSONReporter:
    def write(self, round_result: EvolutionRound) -> None:
        write_json(round_result.run_dir / "summary.json", round_result.summary)
        write_json(
            round_result.run_dir / "examples.json",
            [example.to_report_row() for example in round_result.examples],
        )
        failures = [
            failure
            for example in round_result.examples
            for failure in [example.to_failure_row()]
            if failure is not None
        ]
        if failures:
            write_json(round_result.run_dir / "failures.json", failures)
        if round_result.patch_text:
            write_text(round_result.run_dir / "skill_patch.md", round_result.patch_text)
        if round_result.patch_metadata:
            write_json(round_result.run_dir / "skill_patch_metadata.json", round_result.patch_metadata)
        if round_result.candidate_patches:
            write_json(round_result.run_dir / "candidate_patches.json", round_result.candidate_patches)
        if round_result.aggregated_patches:
            write_json(round_result.run_dir / "aggregated_patches.json", round_result.aggregated_patches)
        if round_result.behavior_signals:
            write_json(round_result.run_dir / "behavior_signals.json", round_result.behavior_signals)
        if round_result.trajectory_cards:
            write_json(round_result.run_dir / "trajectory_cards.json", round_result.trajectory_cards)
        if round_result.category_summaries:
            write_json(round_result.run_dir / "category_summaries.json", round_result.category_summaries)
        if round_result.route_diagnosis:
            write_json(round_result.run_dir / "route_diagnosis.json", round_result.route_diagnosis)
        if round_result.weighted_support:
            write_json(round_result.run_dir / "weighted_support.json", round_result.weighted_support)
        if round_result.contrast:
            write_json(round_result.run_dir / "success_failure_contrast.json", round_result.contrast)
        if round_result.optimizer_evidence_packet:
            write_json(round_result.run_dir / "optimizer_evidence_packet.json", round_result.optimizer_evidence_packet)
        if round_result.validation_before is not None:
            write_json(round_result.run_dir / "validation_before.json", round_result.validation_before)
        if round_result.validation_after is not None:
            write_json(round_result.run_dir / "validation_after.json", round_result.validation_after)
