# Reproducibility

## API-Free Checks

These commands should run without provider credentials:

```bash
uv sync --extra dev
uv run pytest -q
uv run text2sql-demo
uv run text2sql-render-report
```

## API-Backed Checks

Live Text-to-SQL evaluation requires model credentials in `.env` or the shell. Use `.env.example` as the template.

## BIRD Artifacts

The official BIRD files are not committed. Place BIRD MiniDev locally under `data/bird/` and use `text2sql-prepare-bird` to generate JSONL files.

## Expected Smoke Test

The public repository includes deterministic tests that exercise the judge, replay benchmark utilities, skill versioning, SQL-aware gate, and tool policies.
