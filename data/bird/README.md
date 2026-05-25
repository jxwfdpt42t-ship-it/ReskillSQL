# BIRD Data Placeholder

Put the official BIRD benchmark files here when running the real benchmark.

Expected layout:

```text
data/bird/
├── dev.json
└── database/
    └── <db_id>/
        └── <db_id>.sqlite
```

Then prepare the evolver JSONL:

```bash
uv run text2sql-prepare-bird --bird-root data/bird --split dev --output data/bird_dev.jsonl
```

Run a smoke benchmark:

```bash
uv run text2sql-evolve --dataset data/bird_dev.jsonl --limit 20
```
