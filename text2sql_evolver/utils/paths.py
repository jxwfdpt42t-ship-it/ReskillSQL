from __future__ import annotations

from pathlib import Path


def resolve_dataset_path(default_path: Path, raw_path: str | None) -> Path:
    if raw_path is None:
        return default_path
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path.resolve()

    project_candidate = (default_path.parents[1] / path).resolve()
    if project_candidate.exists():
        return project_candidate
    return (default_path.parent / path).resolve()


def resolve_database_path(example_db_path: str | None, default_database: Path) -> Path:
    if example_db_path:
        return Path(example_db_path).expanduser().resolve()
    return default_database
