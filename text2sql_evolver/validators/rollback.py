from __future__ import annotations

from pathlib import Path


class RollbackManager:
    def rollback(self, skill_path: Path, backup_path: Path) -> None:
        skill_path.write_text(backup_path.read_text(encoding="utf-8"), encoding="utf-8")
