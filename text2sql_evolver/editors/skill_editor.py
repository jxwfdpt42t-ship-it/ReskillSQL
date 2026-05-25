from __future__ import annotations

from pathlib import Path

from text2sql_evolver.skill_manager import apply_skill_patch
from text2sql_evolver.skill_manager import render_skill_with_patch


class SkillEditor:
    def render_candidate(self, skill_path: Path, patch_text: str) -> str:
        return render_skill_with_patch(skill_path.read_text(encoding="utf-8"), patch_text)

    def write(self, skill_path: Path, skill_text: str) -> None:
        skill_path.write_text(skill_text, encoding="utf-8")

    def apply(self, skill_path: Path, patch_text: str) -> Path:
        return apply_skill_patch(skill_path, patch_text)
