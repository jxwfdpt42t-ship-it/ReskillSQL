from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    project_root: Path
    database_path: Path
    dataset_path: Path
    reports_dir: Path
    model_name: str
    api_key: str
    base_url: str
    query_skill_path: Path


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    api_key = (os.getenv("OPENAI_API_KEY") or gemini_key or os.getenv("OPENAI_API_KEY_2") or "").strip()
    base_url = (os.getenv("OPENAI_BASE_URL") or "").strip()
    model_name = os.getenv("MODEL_NAME", "").strip()

    using_gemini = bool(gemini_key) and api_key == gemini_key
    if using_gemini:
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        if not model_name or not model_name.startswith("gemini-"):
            model_name = "gemini-2.5-flash"
    elif not base_url:
        base_url = (os.getenv("OPENAI_BASE_URL_2") or "").strip()
    if using_gemini and not model_name:
        model_name = "gemini-2.5-flash"
    if not model_name:
        model_name = "gpt-4.1"

    return Settings(
        project_root=PROJECT_ROOT,
        database_path=Path(os.getenv("TEXT2SQL_DB", PROJECT_ROOT / "chinook.db")).resolve(),
        dataset_path=Path(
            os.getenv("TEXT2SQL_DATASET", PROJECT_ROOT / "data" / "chinook_eval.jsonl")
        ).resolve(),
        reports_dir=Path(os.getenv("TEXT2SQL_REPORTS", PROJECT_ROOT / "reports")).resolve(),
        model_name=model_name,
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        query_skill_path=PROJECT_ROOT / "skills" / "query-writing" / "SKILL.md",
    )
