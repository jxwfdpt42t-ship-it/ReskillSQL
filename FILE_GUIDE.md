# File Guide

## Root Files

- `agent.py`  
  DeepAgents baseline entrypoint. It creates the Text-to-SQL agent, connects to the SQLite database, loads `AGENTS.md` and `skills/`, and exposes the `text2sql-agent` CLI.

- `AGENTS.md`  
  Always-loaded agent instructions: identity, safety rules, SQL behavior, and general operating constraints.

- `README.md`  
  GitHub-facing project explanation: what the project is, how to run it, architecture, BIRD layout, and roadmap.

- `PROJECT_PLAN.md`  
  Resume/project roadmap. Tracks milestones from Chinook smoke test to BIRD benchmark and validation/rollback.

- `docs/EVOLVER_DESIGN.md`  
  Design note for the evolver innovation: SQL-specialized operations, why they fit SQL, and how they differ from generic reflection.

- `docs/EVOLVER_DESIGN.zh.md`  
  `EVOLVER_DESIGN.md` 的中文版本，方便先理解设计。

- `docs/SYSTEM_WALKTHROUGH.md`  
  Full code-level walkthrough from CLI to reports.

- `docs/SYSTEM_WALKTHROUGH.zh.md`  
  `SYSTEM_WALKTHROUGH.md` 的中文版本，方便按代码理解系统脉络。

- `docs/DISCUSSION_POINTS.md`  
  List of project decisions to discuss before final GitHub polish.

- `FILE_GUIDE.md`  
  This file. Quick map of each file and folder.

- `TODO.md`  
  Working notes from the initial project planning phase.

- `pyproject.toml`  
  Python package metadata, dependencies, optional dev dependencies, and CLI commands:
  `text2sql-agent`, `text2sql-evolve`, `text2sql-prepare-bird`, `text2sql-make-splits`.

- `uv.lock`  
  Locked dependency versions for reproducible installs.

- `.env.example`  
  Safe template for environment variables. Real keys belong in `.env`, which is gitignored.

- `.gitignore`  
  Keeps secrets, local reports, virtualenvs, benchmark data, and cache files out of Git.

- `chinook.db`  
  Local demo SQLite database used for the small smoke-test benchmark. It is gitignored because databases can be large.

- `text-to-sql-langsmith-trace.png`  
  Original DeepAgents trace image from the baseline example.

## `skills/`

- `skills/query-writing/SKILL.md`  
  Modular SQL-writing skill. This is the main target of the evolver: repeated validation failures become learned rules here.

- `skills/schema-exploration/SKILL.md`  
  Modular schema-discovery skill. It tells the agent how to inspect tables, columns, samples, primary keys, and foreign-key paths.

## `text2sql_evolver/`

- `__init__.py`  
  Package marker and version.

- `core/`  
  Outer evolution state and orchestration. `orchestrator.py` wires together runner, judge, analyzer, patch generator, acceptance policy, skill editor, and reporters. `state.py` defines reportable run objects.

- `runners/`  
  Inner Text-to-SQL execution backends. `llm_runner.py` calls the current Gemini/OpenAI-compatible model; `cached_runner.py` reuses stored predictions and falls back to the LLM runner.

- `evaluators/`  
  SQL judging and metrics. `execution_judge.py` wraps the safe execution judge; `metrics.py` computes accuracy and failure counts.

- `analyzers/`  
  SQL-specialized failure diagnosis. `sql_specialized.py` is the default analyzer slot; stronger detectors for result shape, ratio handling, value grounding, and evidence usage should be added here.

- `memory/`  
  Stores failure and evolution history. This is where long-term trajectory memory belongs.

- `editors/`  
  Converts failures into skill patches and applies them to skill files.

- `validators/`  
  Acceptance and rollback layer. Supports dry-run/manual apply and validation-set rollback when a patch hurts held-out accuracy.

- `benchmarks/`  
  Benchmark adapters and split utilities. BIRD support and self-update split generation are routed here.

- `reports/`  
  JSON and markdown report writers for each evolution round.

- `utils/`  
  Shared path and IO helpers.

- `config.py`  
  Loads environment variables and default paths. It supports Gemini through Google's OpenAI-compatible endpoint and OpenAI/Azure-style endpoints.

- `dataset.py`  
  Loads JSONL benchmark examples. Supports both single-database Chinook examples and BIRD-style per-example `db_path`.

- `schema.py`  
  SQLite schema introspection utilities used to put database structure into the model prompt.

- `llm.py`  
  Minimal OpenAI-compatible client wrapper and SQL extraction helper.

- `inner_runner.py`  
  The inner Text-to-SQL runner. It builds the prompt from schema, optional BIRD evidence, and the current skill, then asks the model for SQL.

- `judge.py`  
  Safe execution-based evaluator. It blocks write/admin SQL, executes predicted and gold SQL, normalizes rows, and compares execution results.

- `sql_analyzer.py`  
  Failure attribution layer. It maps wrong predictions to categories like schema linking, join path, filtering, aggregation, ordering/limit, projection, and runtime errors.

- `failure_store.py`  
  Stores failure rows, groups failures by category, and writes JSON reports.

- `skill_manager.py`  
  Converts failure categories into learned skill rules. It can write those rules into `skills/query-writing/SKILL.md` after creating a timestamped backup.

- `specialized_ops.py`  
  Registry of the SQL-specialized evolver operations. Reports include this registry so the project documents which SQL-aware diagnostics exist and which are planned.

- `run_round.py`  
  Main evolver command. Runs examples, generates SQL, judges predictions, analyzes failures, writes reports, and optionally applies a skill patch.

- `bird_adapter.py`  
  Converts official BIRD `dev.json/train.json` into this project's JSONL format. It also has a fallback mode that extracts BIRD metadata from old ShapleyRoute result logs.

## `data/`

- `data/chinook_eval.jsonl`  
  Small local smoke-test benchmark with 10 executable Chinook questions.

- `data/bird/README.md`  
  Placeholder that documents where official BIRD files should be placed. The real BIRD data is intentionally gitignored.

## `tests/`

- `tests/test_judge.py`  
  Unit tests for the SQL judge: execution equivalence, wrong-result rejection, and write-SQL blocking.

## Runtime Output

- `reports/round-*`  
  Generated by `text2sql-evolve`. Contains `summary.json`, `examples.json`, `failures.json`, and `skill_patch.md`. Gitignored by default.
