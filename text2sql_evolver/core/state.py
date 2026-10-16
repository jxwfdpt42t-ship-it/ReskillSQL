from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from text2sql_evolver.dataset import Example
from text2sql_evolver.judge import JudgeResult
from text2sql_evolver.sql_analyzer import FailureAnalysis


@dataclass(frozen=True)
class ExampleRun:
    example: Example
    database_path: Path
    predicted_sql: str
    judge: JudgeResult
    analysis: FailureAnalysis | None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    retrieved_memories: list[dict[str, Any]] = field(default_factory=list)

    @property
    def outcome(self) -> str:
        if not self.correct:
            return "failed"
        final_index = max((i for i, a in enumerate(self.attempts) if a["sql"] == self.predicted_sql), default=-1)
        if any(a.get("correct") is False for a in self.attempts[:final_index + 1]):
            return "repaired_success"
        return "direct_success" if self.attempts else "success_trace_unavailable"

    @property
    def correct(self) -> bool:
        return self.judge.correct

    def to_report_row(self) -> dict[str, Any]:
        return {
            "id": self.example.id,
            "source_id": self.example.source_id,
            "question": self.example.question,
            "gold_sql": self.example.gold_sql,
            "predicted_sql": self.predicted_sql,
            "db_path": str(self.database_path),
            "db_id": self.example.db_id,
            "difficulty": self.example.difficulty,
            "correct": self.judge.correct,
            "reason": self.judge.reason,
            "category": self.analysis.category if self.analysis else None,
            "analysis_evidence": self.analysis.evidence if self.analysis else None,
            "analysis_details": self.analysis.details if self.analysis else None,
            "predicted_rows": self.judge.predicted.rows[:10],
            "gold_rows": self.judge.gold.rows[:10],
            "attempts": self.attempts,
            "outcome": self.outcome,
            "retrieved_memories": self.retrieved_memories,
        }

    def to_failure_row(self) -> dict[str, Any] | None:
        if self.analysis is None:
            return None
        return {
            "id": self.example.id,
            "question": self.example.question,
            "gold_sql": self.example.gold_sql,
            "predicted_sql": self.predicted_sql,
            "db_path": str(self.database_path),
            "db_id": self.example.db_id,
            "difficulty": self.example.difficulty,
            "evidence_hint": self.example.evidence,
            "judge_reason": self.judge.reason,
            "category": self.analysis.category,
            "evidence": self.analysis.evidence,
            "details": self.analysis.details,
        }


@dataclass(frozen=True)
class EvolutionRound:
    run_dir: Path
    examples: list[ExampleRun]
    summary: dict[str, Any]
    patch_text: str = ""
    patch_metadata: list[dict[str, Any]] | None = None
    candidate_patches: list[dict[str, Any]] | None = None
    aggregated_patches: list[dict[str, Any]] | None = None
    behavior_signals: list[dict[str, Any]] | None = None
    trajectory_cards: list[dict[str, Any]] | None = None
    category_summaries: list[dict[str, Any]] | None = None
    route_diagnosis: dict[str, Any] | None = None
    weighted_support: dict[str, Any] | None = None
    contrast: dict[str, Any] | None = None
    optimizer_evidence_packet: dict[str, Any] | None = None
    validation_before: list[dict[str, Any]] | None = None
    validation_after: list[dict[str, Any]] | None = None
    skill_backup: Path | None = None
