from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any


@dataclass
class RejectedPatchStore:
    rows: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "RejectedPatchStore":
        if not path.exists():
            return cls()
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append(json.loads(line))
        return cls(rows)

    def add(
        self,
        *,
        run_id: str,
        patch_text: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "run_id": run_id,
            "reason": reason,
            "patch_text": patch_text,
            "metadata": metadata or {},
        }
        self.rows.append(row)
        return row

    def write_jsonl(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "\n".join(json.dumps(row, ensure_ascii=False) for row in self.rows)
        path.write_text(text + ("\n" if text else ""), encoding="utf-8")

    def write_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.rows, indent=2, ensure_ascii=False), encoding="utf-8")
