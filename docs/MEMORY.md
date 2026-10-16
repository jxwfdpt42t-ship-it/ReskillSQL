# Experience Memory

ReskillSQL includes an optional experience-memory layer for the Text-to-SQL evolver. It preserves task episodes and Skill-validation evidence across runs, retrieves relevant experience before SQL generation or Skill optimization, and learns a utility estimate from subsequent outcomes. The base model remains frozen.

Memory is disabled by default. The existing historical accuracy tables predate this integration and are not evidence of a memory gain.

## Design

Each persisted entry contains:

- the source intent used for embedding and recall;
- a reusable text representation built from the episode;
- the complete structured evidence and outcome in metadata;
- database/schema scope and embedding-space identity;
- stable source keys used to prevent same-source leakage;
- separate utility records for the consumer, model, and Skill context.

Task episodes distinguish direct success, repaired success, final failure, and success with unavailable trace. Candidate-Skill validation records local improvements, local regressions, and the whole candidate outcome. A rejected candidate is explicitly marked as rejected evidence and is never represented as a proven rule.

Retrieval has two stages. Cosine similarity filters a schema-compatible candidate pool, then the vendored MemRL `ValueAwareSelector` prioritizes learned utility and uses similarity as the tie-break. Only memory IDs actually injected into the prompt are eligible for feedback. The default utility update is:

```text
Q_new = Q_old + alpha * (reward - Q_old)
```

The current adapter uses `alpha=0.1`, `gamma=0`, and deterministic selection (`epsilon=0`). Successful and failed origins do not determine utility: a historical failure can receive positive value when reusing its lesson helps a later task.

## Upstream provenance

The repository vendors a small subset of [MemTensor/MemRL](https://github.com/MemTensor/MemRL) at commit `c1b322ca43de36ddf64c6712f89d0095bfc35ce0`:

- memory builders and build strategies;
- embedding-provider abstractions;
- `RLConfig`, `ValueAwareSelector`, and `QValueUpdater`.

The original MIT license, source checksums, and the one import-only modification are recorded under `text2sql_evolver/_vendor/memrl/`. The Text-to-SQL persistence, provenance, filtering, context budgeting, and evaluation-isolation logic lives under `text2sql_evolver/memory/`.

This is not an exact reproduction of the paper's full system. It does not vendor MemOS or the upstream benchmark environments, and it uses the upstream Q-first selector after cosine recall rather than the paper's normalized similarity/Q mixture.

## Configuration

Set the regular generation-model variables as described in `.env.example`, then configure an OpenAI-compatible embedding service:

```bash
TEXT2SQL_MEMORY_MODE=learn
TEXT2SQL_MEMORY_PATH=data/memrl/experiences.sqlite
TEXT2SQL_MEMORY_EMBEDDING_MODEL=<embedding-model>
TEXT2SQL_MEMORY_EMBEDDING_BASE_URL=<embedding-endpoint>
TEXT2SQL_MEMORY_EMBEDDING_API_KEY=<embedding-key>
TEXT2SQL_MEMORY_BUILD=proceduralization
TEXT2SQL_MEMORY_INFERENCE=1
```

`TEXT2SQL_MEMORY_BUILD` accepts `trajectory`, `script`, or `proceduralization`. `trajectory` avoids an additional summarization call. `--memory-optimizer-only` disables inference-time injection while retaining optimizer retrieval.

Learn from development data:

```bash
uv run text2sql-evolve \
  --dataset data/update.jsonl \
  --validation-dataset data/validation.jsonl \
  --dataset-role update \
  --memory-mode learn \
  --memory-build proceduralization
```

Evaluate a frozen store:

```bash
uv run text2sql-live-skill-compare \
  --dataset data/final_holdout.jsonl \
  --before-skill skills/query-writing/versions/query-writing-v0002.md \
  --after-skill skills/query-writing/SKILL.md \
  --memory-mode read \
  --memory-path data/memrl/experiences.sqlite \
  --memory-embedding-model <embedding-model>
```

Cached prediction replay cannot measure memory-conditioned generation and is rejected when memory is enabled.

## Evaluation isolation

- Only data labeled `update` or `validation` may write memory or utility feedback.
- Common `holdout` and `test` path names are rejected during learning.
- Current evaluation questions and stable source IDs are excluded from retrieval.
- Source ancestry propagates through derived memories to prevent indirect same-source recall.
- Retrieval is restricted to the same resolved database path and schema hash.
- `read` mode never modifies the memory database or Q values.
- Final holdout results must not be used to tune thresholds, summaries, prompts, or Skill candidates.

The dataset must preserve stable `source_id` values across paraphrases and derived tasks. No runtime mechanism can detect leakage if a derived task is deliberately assigned an unrelated source identity.

## Current limitations

- Multiple memories injected together share task-level feedback, so Q updates are not causal credit assignments.
- Utility is scoped by consumer, model, and Skill content. Frequent Skill changes can reduce reuse of learned utility.
- Retrieval is schema-local; cross-database transfer is not implemented.
- Memories already absorbed into a promoted Skill are not automatically consolidated or down-ranked.
- Summaries are bounded text rather than a fully enforced structured experience-card schema.
- The independent DeepAgents entry point in `agent.py` is not connected to this memory adapter.
- The existing SQL gate's weak-pass policy is unchanged by this integration.

## Verification

```bash
uv sync --extra dev
uv run pytest -q
```

Tests use temporary SQLite stores, deterministic fake embeddings, and mocked model completions. They cover persistence, source exclusion, schema invalidation, repaired trajectories, rejected-candidate evidence, idempotent feedback, read-only evaluation, and rollback after validation failure. These tests verify behavior; they do not establish an accuracy improvement.
