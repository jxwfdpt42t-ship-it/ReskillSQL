from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import difflib
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SkillVersionRecord:
    version: int
    action: str
    skill_path: Path
    score: float | None
    metadata: dict[str, Any]


class SkillVersionManager:
    """Persist candidate/current/best skill artifacts for reproducible evolution."""

    def __init__(self, skill_path: Path, versions_dir: Path | None = None) -> None:
        self.skill_path = skill_path
        self.versions_dir = versions_dir or skill_path.parent / "versions"
        self.index_path = self.versions_dir / "index.json"

    def read_current(self) -> str:
        return self.skill_path.read_text(encoding="utf-8")

    def write_current(self, text: str) -> None:
        self.skill_path.parent.mkdir(parents=True, exist_ok=True)
        self.skill_path.write_text(text, encoding="utf-8")

    def stage_candidate(self, run_dir: Path, text: str, base_text: str) -> dict[str, str]:
        run_dir.mkdir(parents=True, exist_ok=True)
        candidate_path = run_dir / "candidate_skill.md"
        diff_path = run_dir / "candidate_skill.diff"
        candidate_path.write_text(text, encoding="utf-8")
        diff = "".join(
            difflib.unified_diff(
                base_text.splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile="current_skill",
                tofile="candidate_skill",
            )
        )
        diff_path.write_text(diff, encoding="utf-8")
        return {"candidate_skill": str(candidate_path), "candidate_diff": str(diff_path)}

    def save_version(
        self,
        *,
        skill_text: str,
        action: str,
        score: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SkillVersionRecord:
        index = self._load_index()
        version = len(index) + 1
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        skill_path = self.versions_dir / f"query-writing-v{version:04d}.md"
        skill_path.write_text(skill_text, encoding="utf-8")
        row = {
            "version": version,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "action": action,
            "skill_path": str(skill_path),
            "score": score,
            "metadata": metadata or {},
        }
        index.append(row)
        self.index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
        return SkillVersionRecord(version, action, skill_path, score, metadata or {})

    def promote_best(self, skill_text: str, metadata: dict[str, Any] | None = None) -> Path:
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        best_path = self.versions_dir / "best_skill.md"
        best_path.write_text(skill_text, encoding="utf-8")
        if metadata is not None:
            (self.versions_dir / "best_skill.json").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        return best_path

    def _load_index(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        return json.loads(self.index_path.read_text(encoding="utf-8"))
