# Contributing

Thanks for considering a contribution.

## Development Setup

```bash
uv sync --extra dev
uv run pytest -q
```

## Useful Commands

```bash
uv run text2sql-demo
uv run text2sql-render-report
uv run text2sql-replay-ablation --help
uv run text2sql-live-skill-compare --help
```

## Contribution Areas

- Add new SQL failure detectors.
- Improve conservative tool policies.
- Add benchmark adapters for Spider or other Text-to-SQL datasets.
- Add stronger live benchmark suites.
- Improve reports and case studies.

## Reporting Results

Please separate:

- **live generation accuracy**: the model regenerates SQL from a skill
- **replay execution accuracy**: historical SQL is replayed through current checks

Do not report replay scores as official benchmark leaderboard scores.

