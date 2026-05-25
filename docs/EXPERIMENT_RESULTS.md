# Experiment Results

## Live BIRD Skill Comparison

This is the primary closed-loop check. The inner runner reads the old skill and regenerates SQL, then reads the new live-safe skill and regenerates SQL again on the same 100 BIRD MiniDev examples.

```text
Dataset: data/bird_minidev_full_001_100.jsonl
Before skill: skills/query-writing/versions/query-writing-v0002.md
After skill:  skills/query-writing/SKILL.md
Model: gemini-2.5-flash

Before live accuracy: 58/100 (58.00%)
After live accuracy:  67/100 (67.00%)
Delta: +9 percentage points
Improved examples: 1472, 1484, 1498, 1506, 1525, 1350, 1376, 1392, 1435, 1156, 1185, 1187
Regressions: 1473, 1533, 1171
Improved categories: ordering_limit, value_grounding, aggregation, projection, schema_linking
```

Reproduction command:

```bash
uv run text2sql-live-skill-compare \
  --dataset data/bird_minidev_full_001_100.jsonl \
  --before-skill skills/query-writing/versions/query-writing-v0002.md \
  --after-skill skills/query-writing/SKILL.md \
  --limit 100 \
  --output reports/live_skill_compare_bird100_v0002_vs_v0010_live_safe_20260712.json
```

This differs from replay: the SQL is generated live in both conditions. Replay remains useful for cheaper debugging over larger historical trajectories.

## Lightweight Replay Ablation

This ablation reuses the historical 100-example replay slice and toggles compiled skill policies without extra LLM calls.

| Variant | Before | After | Delta | Improvements | Regressions |
|---|---:|---:|---:|---:|---:|
| no_reskill | 53/100 | 53/100 | +0.00% | 0 | 0 |
| query_skill_checks_only | 53/100 | 58/100 | +5.00% | 5 | 0 |
| value_lookup_only | 53/100 | 54/100 | +1.00% | 1 | 0 |
| full_system | 53/100 | 59/100 | +6.00% | 6 | 0 |

Reproduction command:

```bash
uv run text2sql-replay-ablation \
  --dataset data/bird_minidev_full_001_100.jsonl \
  --examples reports/round-20260707-223959-413805/examples.json \
  --skill skills/query-writing/SKILL.md \
  --output reports/replay_ablation_bird100_20260712.json
```

## Natural BIRD Replay: SQL-Aware + Tool-Aware Skill Checks

This experiment replays historical BIRD MiniDev predictions through the current query-writing skill checks.

The historical predictions were produced by the inner Text-to-SQL runner on 100 BIRD MiniDev examples. The replay keeps the original predicted SQL fixed, then applies the current query-writing skill checks and tool-use policies from `skills/query-writing/SKILL.md` before execution judging.

```text
Dataset: BIRD MiniDev examples 1-100
Before skill checks: 53/100 execution accuracy
After skill checks:  59/100 execution accuracy
Delta: +6 percentage points
Improved examples: 1498, 1506, 1350, 1422, 1435, 1155
Regressions: 0
Improved categories: projection / result shape, aggregation, value grounding
```

Reproduction command:

```bash
uv run text2sql-evaluate-skill-replay \
  --dataset data/bird_minidev_full_001_100.jsonl \
  --examples reports/round-20260707-223959-413805/examples.json \
  --skill skills/query-writing/SKILL.md \
  --output reports/natural_replay_tool_aware_20260707_update_v3.json
```

Because official BIRD data and generated reports are not committed, this command requires local BIRD files and the historical report artifacts.

## Interpretation

The improvement comes from reusable output-shape behavior rather than one-off answer fitting:

- list/category/name queries can require `DISTINCT` when joins introduce duplicate answer rows
- projection checks remove helper columns that are only used for filtering
- ratio/percentage checks keep intermediate numerator and denominator counts out of the final projection unless requested
- monthly ranking aggregation checks distinguish maximum single rows from highest monthly totals
- value lookup policy normalizes high-confidence literal formats against stored database values, such as `2019-8-20` to `2019-08-20`

This result supports the first self-evolution loop: execution traces can expose a repeated query-writing behavior problem, the outer evolver can turn it into a stricter skill plan, and the compiled skill checks can improve replayed natural failures without creating regressions on the tested slice.

## Holdout Replay: Unseen BIRD Slice

This experiment uses a separate BIRD MiniDev slice that did not participate in the update replay above. The baseline predictions were generated with an older query-writing skill, then replayed through the current compiled skill checks.

```text
Dataset: BIRD MiniDev examples 101-150
Before skill checks: 20/50 execution accuracy
After skill checks:  22/50 execution accuracy
Delta: +4 percentage points
Improved examples: 1035, 1079
Regressions: 0
Improved category: projection
```

Reproduction command:

```bash
uv run text2sql-evaluate-skill-replay \
  --dataset data/bird_minidev_full_101_150.jsonl \
  --examples reports/round-20260707-232414-683610/examples.json \
  --skill skills/query-writing/SKILL.md \
  --output reports/natural_replay_tool_aware_20260707_holdout_v4.json
```

The holdout effect is smaller than the update replay effect, but it is important because it checks whether the learned behavior transfers to a new slice instead of only fixing the examples used to design the skill update.

## Suite Summary

```bash
uv run text2sql-summarize-replay-suite \
  --update reports/natural_replay_tool_aware_20260707_update_v3.json \
  --holdout reports/natural_replay_tool_aware_20260707_holdout_v4.json \
  --output reports/self_update_replay_suite_20260707.json
```

```text
update:  53/100 -> 59/100  (+6.00%), regressions=0
holdout: 20/50  -> 22/50   (+4.00%), regressions=0
```

## 500-Example Replay Collection

The broader collection replays six BIRD MiniDev slices. It keeps the original baseline predictions from the older skill, then applies the current reskilled query-writing skill and tool policies.

| Split | Before | After | Delta | Improvements | Regressions |
|---|---:|---:|---:|---:|---:|
| update_001_100 | 53/100 | 59/100 | +6.00% | 6 | 0 |
| holdout_101_150 | 20/50 | 22/50 | +4.00% | 2 | 0 |
| bird_151_250 | 48/100 | 54/100 | +6.00% | 7 | 1 |
| bird_251_300 | 39/50 | 37/50 | -4.00% | 2 | 4 |
| bird_301_400 | 43/100 | 48/100 | +5.00% | 5 | 0 |
| bird_401_500 | 29/100 | 37/100 | +8.00% | 9 | 1 |
| total | 232/500 | 257/500 | +5.00% | 31 | 6 |

Improved categories across the 500 examples:

```text
projection: 16
value_grounding: 7
schema_linking: 3
ratio_numeric: 2
aggregation: 2
join_path: 1
```

Reproduction command:

```bash
uv run text2sql-summarize-replay-collection \
  --result update_001_100=reports/natural_replay_tool_aware_20260707_update_v3.json \
  --result holdout_101_150=reports/natural_replay_tool_aware_20260707_holdout_v4.json \
  --result bird_151_250=reports/natural_replay_tool_aware_20260709_151_250.json \
  --result bird_251_300=reports/natural_replay_tool_aware_20260709_251_300.json \
  --result bird_301_400=reports/natural_replay_tool_aware_20260709_301_400.json \
  --result bird_401_500=reports/natural_replay_tool_aware_20260709_401_500.json \
  --output reports/self_update_replay_collection_500_20260709.json
```

The 500-example result is more realistic than the first update/holdout pair: it shows positive transfer overall, but it also exposes that one high-baseline slice regressed from 78% to 74%. That slice is the main next target for stricter tool-policy gating.

## Generated Transfer Benchmark 500

This is the stronger self-update benchmark asset. Instead of only replaying historical predictions, it turns BIRD MiniDev into category-conditioned transfer challenges that can be used for old-skill vs new-skill live evaluation after a reskill round.

```text
Source: data/bird/raw/minidev/minidev/MINIDEV/mini_dev_sqlite.json
Output: data/self_update/generated_transfer_500
Total: 500
Gold SQL validated: 498/500
Splits: update=200, validation=150, holdout=150
```

Category coverage:

```text
aggregation_projection: 157
ratio_numeric: 109
schema_linking: 88
ordering_limit: 82
filtering: 50
semantic_mismatch: 11
value_grounding: 3
```

Reproduction command:

```bash
uv run text2sql-make-generated-transfer-benchmark \
  --limit 500 \
  --output-dir data/self_update/generated_transfer_500
```

The generated files are intended for transfer checks:

```text
update.jsonl      -> failures used to trigger/reskill
validation.jsonl -> gate set for accepting candidate skill
holdout.jsonl    -> unseen transfer set after acceptance
```

The benchmark records `source_id`, `source_question`, `category`, `skill_target`, `generation_method`, and gold-SQL validation metadata for every item. Two BIRD gold SQL queries exceed the default SQLite timeout and are marked `validated=false`; they are kept in the 500-item manifest so users can choose either full-size or validated-only evaluation.

Live old-skill vs new-skill transfer results on validated-only splits:

| Split | Before | After | Delta | Improvements | Regressions |
|---|---:|---:|---:|---:|---:|
| validation | 78/149 | 81/149 | +2.01% | 12 | 9 |
| holdout | 75/150 | 82/150 | +4.67% | 14 | 7 |

Validation improved categories:

```text
filtering: 1
projection: 5
value_grounding: 4
schema_linking: 2
```

Holdout improved categories:

```text
value_grounding: 7
aggregation: 2
projection: 5
```

Live transfer reproduction commands:

```bash
uv run text2sql-live-skill-compare \
  --dataset data/self_update/generated_transfer_500/validated_only/validation.jsonl \
  --before-skill skills/query-writing/versions/query-writing-v0002.md \
  --after-skill skills/query-writing/SKILL.md \
  --output reports/live_generated_transfer_validation_149_v0002_vs_v0010_20260715.json

uv run text2sql-live-skill-compare \
  --dataset data/self_update/generated_transfer_500/validated_only/holdout.jsonl \
  --before-skill skills/query-writing/versions/query-writing-v0002.md \
  --after-skill skills/query-writing/SKILL.md \
  --output reports/live_generated_transfer_holdout_150_v0002_vs_v0010_20260715.json
```

Interpretation: the generated transfer benchmark shows positive but modest transfer. The result is stronger evidence than replay because SQL is regenerated live under each skill, but the validation split also shows non-trivial regressions. This supports the self-update direction while making the next engineering target clear: stricter promotion gates for high-risk patch effects.

Regression memory:

```text
data/regression_memory.jsonl
validation regressions stored: 9
holdout regressions stored: 7
total protection examples: 16
```

Each memory row stores the question, category, old SQL, new SQL, gold SQL, and suspected cause. Future gates can evaluate candidate skills against these protection cases and reject updates that turn previously correct behavior into new failures.

## Multi-Round Self-Update Benchmark

This extends the 500-question generated transfer benchmark from a one-shot before/after evaluation into a three-round self-update benchmark. The goal is to evaluate whether skill evolution improves over time, avoids repeated failures, and transfers across SQL ability categories.

```text
Source: data/self_update/generated_transfer_500
Output: data/self_update/generated_transfer_500_multiround
Total: 500
Validated: 498/500
Rounds: 3
```

Round splits:

| Round | Total | Update | Validation | Holdout | Validated |
|---|---:|---:|---:|---:|---:|
| round_1 | 170 | 68 | 50 | 52 | 170 |
| round_2 | 166 | 67 | 50 | 49 | 164 |
| round_3 | 164 | 65 | 50 | 49 | 164 |

Each round is designed to follow the self-update loop:

```text
update split
  -> generate/select candidate skill patch
validation split
  -> gate candidate skill
holdout split
  -> final transfer test
```

The multi-round summarizer reports:

```text
accuracy
regression count
failure avoidance rate
category transfer gain
skill length
estimated model calls / prompt tokens
```

Full three-round live evaluation:

| Round | Validation | Holdout | Failure Avoidance Rate |
|---|---:|---:|---:|
| round_1 | 32/50 -> 33/50 (+2.00%) | 30/52 -> 31/52 (+1.92%) | gate 27.78%, final 18.18% |
| round_2 | 26/50 -> 28/50 (+4.00%) | 27/49 -> 28/49 (+2.04%) | gate 20.83%, final 18.18% |
| round_3 | 28/50 -> 25/50 (-6.00%) | 31/49 -> 35/49 (+8.16%) | gate 9.09%, final 22.22% |
| aggregate | - | 174/300 -> 180/300 (+2.00%) | 19.05% |

Across all validation/holdout splits, the full live run evaluates 300 examples with 600 LLM generations. The holdout split improves in all three rounds, while round_3 validation regresses. This is useful evidence for the benchmark: the update direction transfers on final held-out tasks, but the gate should become stricter before automatic multi-round promotion.

Reproduction commands:

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

Comparison to recent self-update benchmark work:

| Recent benchmark idea | What it measures | This project |
|---|---|---|
| held-out validation gate | whether updates improve examples not used for writing the patch | validation split per round |
| ability / category transfer | whether learned behavior transfers by skill category | category transfer gain over SQL categories |
| failure avoidance | whether past failure patterns are avoided later | failure avoidance rate and regression memory |
| sequential evolution | whether the system improves over multiple updates | three category-balanced rounds over the same 500 examples |
| snapshot / cost tracking | whether versions and update cost are auditable | skill length and estimated model-call/token metrics |

## Engineering Robustness Fixes

The holdout run exposed two benchmark-infrastructure issues that are now fixed:

- SQLite execution timeout: generated SQL can create very expensive joins, so the judge interrupts slow queries instead of hanging the whole benchmark.
- Optimizer failure isolation: if the optimizer LLM returns an unusable patch, the evolver still writes the run report and keeps the benchmark trajectory.
- Live comparison checkpointing and retry: long live transfer runs now write partial JSON after each example and continue through transient model/API connection failures.
