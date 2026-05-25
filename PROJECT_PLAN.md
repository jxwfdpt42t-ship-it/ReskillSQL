# Project Plan

This project is intended to be a resume-grade open-source Agent project, not only a local experiment.

## Core Claim

Text-to-SQL agents can improve through executable feedback by localizing failures to SQL behavior modules and updating modular skills under validation.

## Milestones

### M0: Runnable Smoke Test

- Gemini/OpenAI-compatible model backend
- Chinook SQLite validation set
- execution-based judge
- failure attribution
- report generation
- skill patch proposal and backup-backed application

Status: done.

### M1: Benchmark Adapter

- add Spider/BIRD JSON adapter
- support per-example database paths
- support train/dev/holdout split files
- cache predictions to avoid repeated model calls

Status: BIRD adapter and per-example database paths implemented; official BIRD sqlite files still need to be placed under `data/bird/database/`.

### M2: Real Evolver

- LLM-written skill patch with structured diff
- validation rerun after patch
- rollback when holdout accuracy drops
- compare before/after across failure categories

Status: outer architecture implemented. `core/`, `runners/`, `evaluators/`, `analyzers/`, `memory/`, `editors/`, `validators/`, `benchmarks/`, `reports/`, and `utils/` now exist and the CLI routes through the orchestrator. Validation-set scoring and rollback are implemented; next target is final holdout reporting for self-update benchmark claims.

### M3: GitHub Polish

- demo GIF or terminal screenshot
- architecture diagram
- benchmark table
- issue templates
- example reports committed under `examples/reports/`

## What To Put On Resume

Self-Evolving Text-to-SQL Agent

- Built a DeepAgents-style Text-to-SQL system with an outer evolver loop: SQL generation, execution-based judging, clause-level failure attribution, skill patch generation, and validation reports.
- Implemented safe SQLite evaluation that blocks write/admin SQL and compares execution results instead of string equality; categorized failures into schema linking, join path, filtering, aggregation, ordering/limit, projection, and runtime errors.
- Added Gemini/OpenAI-compatible backend, modular skill files, Chinook smoke-test set, and backup-backed skill updates; current smoke test reaches 80% execution accuracy with remaining errors localized to deterministic tie-breakers.
