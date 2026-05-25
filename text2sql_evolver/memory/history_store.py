from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any


@dataclass
class EvolutionHistory:
    events: list[dict[str, Any]] = field(default_factory=list)

    def add_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "event_type": event_type,
                "payload": payload,
            }
        )

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.events, indent=2, ensure_ascii=False), encoding="utf-8")
