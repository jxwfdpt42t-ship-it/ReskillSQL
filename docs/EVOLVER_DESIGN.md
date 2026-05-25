# Evolver Design

The evolver is the outer learning loop around the Text-to-SQL agent. It does not update model weights. It updates the agent's external skill memory after observing execution traces.

```text
generate SQL -> execute/judge -> diagnose SQL-specific failure -> propose skill patch -> validate -> accept or roll back
```

## Core Claim

SQL is a strong domain for self-evolving agents because it provides:

- executable feedback
- explicit schema constraints
- decomposable clause structure
- repeatable validation on held-out questions

Unlike open-ended natural-language generation, SQL failures can often be localized to schema linking, joins, filtering, aggregation, ordering, projection, value grounding, or runtime errors. This makes targeted skill updates possible.

## SQL-Specialized Operations

| Operation | Purpose | Why It Fits SQL |
|---|---|---|
| Clause-level analysis | Decompose SQL into `SELECT / FROM / JOIN / WHERE / GROUP BY / ORDER BY / LIMIT` and localize the failing clause. | SQL is structured, so failures usually map to explicit clauses instead of vague free-form behavior. |
| Schema linking check | Check whether predicted tables and columns exist and whether they match the question intent. | Text-to-SQL often fails by choosing the wrong table or business-specific column, especially on BIRD. |
| Join path analysis | Detect missing joins, extra joins, disconnected join paths, and suspicious join conditions. | Multi-table SQL depends on schema graph connectivity and foreign-key paths, which can be inspected directly. |
| Value grounding check | Map entities in the question to actual database values and catch value mismatches. | Many SQL errors are value errors rather than syntax errors, such as `Alameda County` vs `Alameda`. |
| Execution error classification | Classify runtime errors such as no such table, no such column, ambiguous column, syntax error, and timeout. | SQL execution errors are strong feedback, and each error class has a natural repair strategy. |
| Result-shape comparison | Compare row count, column count, single-row aggregation shape, top-k shape, and returned value types. | A SQL query can execute but still return the wrong shape, revealing missing aggregation, projection, or `LIMIT`. |
| Aggregation reasoning check | Check `COUNT/SUM/AVG/MIN/MAX`, `GROUP BY`, and non-aggregate selected columns. | SQL aggregation has explicit rules and common failure modes that are easy to inspect structurally. |
| Ratio / percentage handling | Handle rates, percentages, averages, differences, `REAL` casts, `NULLIF` denominators, and ordering by computed metrics. | BIRD often uses evidence-defined formulas, and numeric SQL is vulnerable to integer division and divide-by-zero issues. |
| Order / limit / tie-break check | Check top/bottom/latest/highest/lowest ranking semantics, `ORDER BY` direction, `LIMIT`, and stable tie-breakers. | Ranking questions are common, and execution-equivalent intent can fail because of missing `LIMIT` or unstable ordering. |
| Evidence usage check | Check whether BIRD evidence formulas, business definitions, and filters are reflected in SQL. | BIRD provides evidence fields, making domain-grounded diagnosis possible instead of generic reflection. |
| SQL safety guard | Block `INSERT/UPDATE/DELETE/DROP/ALTER/PRAGMA` and other non-read-only statements. | A public benchmark runner must safely execute model-generated SQL against local databases. |
| Skill patch validation | Validate skill edits on held-out examples and accept or roll back based on measured behavior. | Execution accuracy gives a concrete acceptance signal, preventing prompt edits from becoming unchecked reflection. |

## Why This Is More Than Reflection

A generic reflection system asks an LLM to summarize what went wrong. This evolver first uses SQL structure to produce a grounded diagnosis. The LLM is used after the system has already collected evidence:

```text
wrong query
gold query
execution error or mismatch
schema
clause-level diff
failure category
BIRD evidence
validation result
```

That design makes skill patches easier to audit, easier to validate, and less likely to overfit one example.

## Implementation Path

1. Keep the current smoke-test loop working.
2. Implement one specialized detector at a time.
3. Write each detector result into `failures.json`.
4. Make `skill_manager.py` generate patches from detector evidence, not just category names.
5. Add validation/rollback before accepting skill edits. This is now implemented for optional validation splits; final holdout reporting is the next step.

## Outer Architecture

The outer evolver is organized as explicit layers so each research idea has a stable place to live.

```text
text2sql_evolver/
├── core/          # state and orchestration
├── runners/       # inner Text-to-SQL execution backends
├── evaluators/    # execution judge and metrics
├── analyzers/     # SQL-specialized failure diagnosis
├── memory/        # failure stores and evolution history
├── editors/       # skill patch generation and editing
├── validators/    # acceptance, rollback, future holdout validation
├── benchmarks/    # BIRD/Spider/self-update benchmark adapters
├── reports/       # JSON and markdown report writers
└── utils/         # path, JSONL, and shared helpers
```

The current `text2sql-evolve` command now goes through `core.orchestrator.EvolutionOrchestrator`:

```text
load examples
-> runner.generate()
-> execution_judge.evaluate()
-> sql_specialized_analyzer.analyze()
-> patch_generator.generate()
-> acceptance_policy.decide()
-> skill_editor.apply() when accepted
-> json/markdown reporters
```

This is deliberately more structured than a single script. It lets us replace a weak component without changing the rest of the loop. For example, `analyzers/sql_specialized.py` can start as heuristics and later become a multi-detector SQL diagnosis engine.
