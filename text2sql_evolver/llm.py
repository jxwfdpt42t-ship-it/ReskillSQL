from __future__ import annotations

import re

from openai import OpenAI

from .config import Settings


def create_client(settings: Settings) -> OpenAI:
    if not settings.api_key:
        raise RuntimeError(
            "Missing model API key. Set OPENAI_API_KEY or GEMINI_API_KEY in your shell/.env."
        )
    kwargs = {"api_key": settings.api_key}
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    return OpenAI(**kwargs)


def complete_text(settings: Settings, system: str, user: str, max_tokens: int = 700) -> str:
    client = create_client(settings)
    response = client.chat.completions.create(
        model=settings.model_name,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0,
        max_tokens=max_tokens,
    )
    return (response.choices[0].message.content or "").strip()


def extract_sql(text: str) -> str:
    fenced = re.search(r"```[a-zA-Z0-9_-]*\s*(.*?)```", text, re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1).strip().rstrip(";") + ";"

    select_match = re.search(r"((?:WITH|SELECT)\b.*)", text, re.IGNORECASE | re.DOTALL)
    if select_match:
        sql = select_match.group(1).strip()
        sql = re.split(r"\n\s*(?:Explanation|Answer|Result)\s*:", sql, flags=re.IGNORECASE)[0].strip()
        return sql.rstrip(";") + ";"

    return text.strip()
