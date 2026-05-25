from __future__ import annotations

from collections import defaultdict
import json
import random
from pathlib import Path
from typing import Iterable

from text2sql_evolver.dataset import Example


def group_by_tag(examples: Iterable[Example]) -> dict[str, list[Example]]:
    groups: dict[str, list[Example]] = defaultdict(list)
    for example in examples:
        for tag in example.tags:
            groups[tag].append(example)
    return dict(groups)


def deterministic_split(
    examples: list[Example],
    update_ratio: float = 0.4,
    validation_ratio: float = 0.3,
    seed: int = 42,
) -> tuple[list[Example], list[Example], list[Example]]:
    shuffled = list(examples)
    rng = random.Random(seed)
    rng.shuffle(shuffled)
    update_end = int(len(shuffled) * update_ratio)
    validation_end = update_end + int(len(shuffled) * validation_ratio)
    return shuffled[:update_end], shuffled[update_end:validation_end], shuffled[validation_end:]


def write_split_jsonl(path: Path, examples: list[Example]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for example in examples:
            f.write(json.dumps(example.__dict__, ensure_ascii=False) + "\n")
