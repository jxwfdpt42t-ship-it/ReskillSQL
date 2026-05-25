# Discussion Points

These are the parts we should discuss before polishing the project for GitHub/resume.

## 1. Core Claim

Paths: `README.md`, `docs/EVOLVER_DESIGN.md`, `PROJECT_PLAN.md`

Decision: should the project claim be broad, `Self-evolving Text-to-SQL agent`, or sharper, `SQL-aware skill evolution benchmark and agent`?

My recommendation: use the sharper version once the self-update benchmark is ready.

## 2. Which Skill Files Can Be Edited

Paths: `skills/query-writing/SKILL.md`, `skills/schema-exploration/SKILL.md`, `text2sql_evolver/editors/`

Decision: should evolver only edit `query-writing`, or can it also edit schema exploration?

My recommendation: start with `query-writing` only, because it makes validation and rollback easier to explain.

## 3. Analyzer Strength vs Simplicity

Paths: `text2sql_evolver/sql_analyzer.py`, `text2sql_evolver/analyzers/sql_specialized.py`, `text2sql_evolver/specialized_ops.py`

Decision: keep deterministic detectors as primary evidence, or add LLM-based diagnosis?

My recommendation: deterministic detectors first, LLM only for writing human-readable skill patches.

## 4. Validation Policy

Paths: `text2sql_evolver/validators/acceptance.py`, `text2sql_evolver/validators/validation_runner.py`, `text2sql_evolver/validators/rollback.py`

Decision: accept patches when validation is non-decreasing, or require a positive delta?

My recommendation: non-decreasing for early experiments, positive delta on larger BIRD/Spider splits.

## 5. Self-Update Benchmark Split

Paths: `text2sql_evolver/benchmarks/make_self_update_splits.py`, `text2sql_evolver/benchmarks/splits.py`

Decision: how do we define update/validation/holdout?

My recommendation:

```text
update: failures used to generate patch
validation: decides accept/rollback
holdout: final reported generalization
```

## 6. BIRD Role

Paths: `data/bird/README.md`, `text2sql_evolver/bird_adapter.py`, `text2sql_evolver/benchmarks/bird.py`

Decision: is BIRD the main benchmark or raw material for the self-update benchmark?

My recommendation: BIRD is the credibility anchor and raw material. The self-update split is the actual innovation benchmark.

## 7. Runner Choice

Paths: `text2sql_evolver/runners/`, `text2sql_evolver/inner_runner.py`, `agent.py`

Decision: should benchmark runs use direct LLM prompting or the full DeepAgents baseline?

My recommendation: keep direct LLM runner for controlled benchmark loops, then add DeepAgent runner as a separate comparison.

## 8. What To Remove Before GitHub

Paths: `TODO.md`, `text-to-sql-langsmith-trace.png`, `chinook.db`, `reports/`

Decision: which local artifacts should stay?

My recommendation: keep `chinook.db` only if license/size is acceptable; otherwise add a download script. Remove or rewrite `TODO.md` before public release.
