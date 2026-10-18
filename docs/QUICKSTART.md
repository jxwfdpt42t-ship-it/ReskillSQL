# Quickstart

## Install

```bash
uv sync --extra dev
```

## Run the API-Free Demo

```bash
uv run text2sql-demo
```

This command does not call an LLM API. It demonstrates reusable SQL rewrites without publishing benchmark claims.

## Render the Showcase Report

```bash
uv run text2sql-render-report
open reports/showcase/index.html
```

## Run a Live Skill Comparison

This command calls the configured model API.

```bash
uv run text2sql-live-skill-compare \
  --dataset data/bird_minidev_full_001_100.jsonl \
  --before-skill skills/query-writing/versions/query-writing-v0002.md \
  --after-skill skills/query-writing/SKILL.md \
  --limit 100 \
  --output reports/live_skill_compare.json
```

## Run a Local Replay Ablation

```bash
uv run text2sql-replay-ablation \
  --dataset data/bird_minidev_full_001_100.jsonl \
  --examples reports/round-20260707-223959-413805/examples.json \
  --skill skills/query-writing/SKILL.md \
  --output reports/replay_ablation_bird100_20260712.json
```

## Build the 500-Question Transfer Benchmark

```bash
uv run text2sql-make-generated-transfer-benchmark \
  --limit 500 \
  --output-dir data/self_update/generated_transfer_500
```

The command writes category-conditioned `update`, `validation`, and `holdout` JSONL files for self-update transfer evaluation.

## Build the 3-Round Self-Update Benchmark

```bash
uv run text2sql-make-multiround-self-update-benchmark \
  --source-dir data/self_update/generated_transfer_500 \
  --output-dir data/self_update/generated_transfer_500_multiround

uv run text2sql-summarize-multiround-self-update \
  --benchmark-dir data/self_update/generated_transfer_500_multiround \
  --report reports/live_multiround_round_1_validation_v0002_vs_v0010_20260719.json \
  --report reports/live_multiround_round_1_holdout_v0002_vs_v0010_20260719.json \
  --report reports/live_multiround_round_2_validation_v0002_vs_v0010_20260719.json \
  --report reports/live_multiround_round_2_holdout_v0002_vs_v0010_20260719.json \
  --report reports/live_multiround_round_3_validation_v0002_vs_v0010_20260719.json \
  --report reports/live_multiround_round_3_holdout_v0002_vs_v0010_20260719.json \
  --skill skills/query-writing/SKILL.md \
  --output reports/multiround_self_update_full_live_summary_20260719.json
```

This evaluates multi-round skill evolution metrics: accuracy, regressions, failure avoidance rate, category transfer gain, skill length, and estimated model-call/token cost.

## Run Tests

```bash
uv run pytest -q
```
