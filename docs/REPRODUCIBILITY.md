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

Experience-memory experiments additionally require a real embedding model and an isolated SQLite store per experimental arm and seed. Never run concurrent writers against the same Skill file or memory store. Use `memory_mode=learn` only for update/validation data and `memory_mode=read` for final holdout evaluation. See [MEMORY.md](MEMORY.md).

## BIRD Artifacts

The official BIRD files are not committed. Place BIRD MiniDev locally under `data/bird/` and use `text2sql-prepare-bird` to generate JSONL files.

## Expected Smoke Test

The public repository includes deterministic tests that exercise the judge, replay benchmark utilities, skill versioning, SQL-aware gate, and tool policies.

Memory tests use deterministic fake embeddings and temporary databases. They verify implementation behavior but do not reproduce a provider-backed accuracy result. The historical scores in the README predate the memory integration and must be re-baselined on the current runtime before a memory comparison.
