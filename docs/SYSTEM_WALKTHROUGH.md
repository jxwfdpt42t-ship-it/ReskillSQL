# System Walkthrough

This file explains the current system from code to runtime flow.

## Runtime Flow

```text
CLI: text2sql-evolve
  -> run_round.py parses args
  -> load_settings() reads model/db/report config
  -> load_jsonl() reads benchmark examples
  -> EvolutionOrchestrator.run()
      -> runner.generate()
      -> execution judge compares predicted/gold execution results
      -> SQL-specialized analyzer diagnoses wrong cases
      -> patch generator drafts learned skill rules
      -> optional validation split tests the patch
      -> acceptance policy accepts or rejects
      -> rollback restores backup when validation regresses
      -> reporters write JSON/markdown artifacts
```

## Files And Responsibilities

### Root

- `agent.py`: DeepAgents baseline Text-to-SQL CLI.
- `AGENTS.md`: always-loaded agent-level instructions.
- `skills/query-writing/SKILL.md`: SQL-writing skill that the evolver edits.
- `skills/schema-exploration/SKILL.md`: schema exploration skill.
- `pyproject.toml`: package metadata, dependencies, CLI commands.
- `.env.example`: safe env template.
- `.gitignore`: excludes secrets, reports, local benchmark data, and caches.
- `README.md`: public project entry.
- `PROJECT_PLAN.md`: milestone and resume framing.
- `FILE_GUIDE.md`: quick file map.

### Data

- `data/chinook_eval.jsonl`: local smoke-test benchmark.
- `data/bird/README.md`: placeholder explaining where official BIRD data belongs.

### Config And Data Loading

- `text2sql_evolver/config.py`: model/backend/path settings; supports Gemini and OpenAI-compatible endpoints.
- `text2sql_evolver/dataset.py`: JSONL example loader; supports per-example `db_path`, `db_id`, `evidence`, and `difficulty`.
- `text2sql_evolver/schema.py`: SQLite schema introspection for prompting.

### Core

- `text2sql_evolver/core/orchestrator.py`: the main outer evolver. It wires runner, judge, analyzer, editor, validator, rollback, and reporters.
- `text2sql_evolver/core/state.py`: reportable state objects for one example and one evolution round.

### Runners

- `text2sql_evolver/runners/base.py`: runner interface.
- `text2sql_evolver/runners/llm_runner.py`: calls Gemini/OpenAI-compatible model to generate SQL.
- `text2sql_evolver/runners/cached_runner.py`: uses cached predictions when provided; falls back to LLM runner.
- `text2sql_evolver/inner_runner.py`: prompt construction and SQL generation function used by the LLM runner.
- `text2sql_evolver/llm.py`: OpenAI-compatible client and SQL extraction.

### Evaluators

- `text2sql_evolver/judge.py`: read-only SQL safety guard, SQL execution, execution-result comparison.
- `text2sql_evolver/evaluators/execution_judge.py`: object wrapper around `judge_sql`.
- `text2sql_evolver/evaluators/metrics.py`: accuracy and failure-count metrics.

### Analyzers

- `text2sql_evolver/analyzers/base.py`: analyzer interface.
- `text2sql_evolver/analyzers/sql_specialized.py`: default SQL-aware analyzer.
- `text2sql_evolver/sql_analyzer.py`: detector logic for clause mismatch, schema/table mismatch, joins, aggregation, filtering, ordering, result shape, ratio/numeric warnings, value grounding, and evidence usage.
- `text2sql_evolver/specialized_ops.py`: registry of SQL-specialized evolver operations and implementation status.

### Memory

- `text2sql_evolver/failure_store.py`: in-memory failure grouping and JSON writer.
- `text2sql_evolver/memory/failure_store.py`: memory-layer alias for failure storage.
- `text2sql_evolver/memory/history_store.py`: event history for example runs, patch decisions, and rollbacks.

### Editors

- `text2sql_evolver/skill_manager.py`: rule templates and skill-file patch application.
- `text2sql_evolver/editors/patch_generator.py`: converts failures into patch text, optionally via LLM.
- `text2sql_evolver/editors/skill_editor.py`: applies patch to `SKILL.md` with backup.

### Validators

- `text2sql_evolver/validators/acceptance.py`: accepts/rejects patch based on manual apply or validation accuracy delta.
- `text2sql_evolver/validators/validation_runner.py`: reruns a validation split and scores execution accuracy.
- `text2sql_evolver/validators/rollback.py`: restores a skill backup if validation fails.

### Benchmarks

- `text2sql_evolver/bird_adapter.py`: converts official BIRD JSON or old ShapleyRoute logs to project JSONL.
- `text2sql_evolver/benchmarks/bird.py`: benchmark-layer exports for BIRD conversion.
- `text2sql_evolver/benchmarks/splits.py`: deterministic update/validation/holdout split utilities.
- `text2sql_evolver/benchmarks/make_self_update_splits.py`: CLI to create self-update benchmark splits.

### Reports

- `text2sql_evolver/reports/json_reporter.py`: writes `summary.json`, `examples.json`, `failures.json`, and `skill_patch.md`.
- `text2sql_evolver/reports/markdown_reporter.py`: writes `report.md`.

### Utilities

- `text2sql_evolver/utils/paths.py`: dataset and database path resolution.
- `text2sql_evolver/utils/io.py`: prediction JSONL loading and shared writers.

## Report Outputs

Each `text2sql-evolve` run writes:

- `summary.json`: model, accuracy, failure counts, patch decision, specialized operation registry.
- `examples.json`: per-example SQL, correctness, rows, and analyzer details.
- `failures.json`: wrong cases with detector evidence.
- `skill_patch.md`: proposed learned rules.
- `report.md`: human-readable summary.
- `history.json`: event trace for example runs and patch decisions.
