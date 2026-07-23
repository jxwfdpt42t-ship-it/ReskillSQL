# Benchmark Protocol

ReskillSQL separates two evaluation goals:

1. Text-to-SQL execution accuracy.
2. Whether skill updates transfer to future SQL tasks without excessive regressions.

## Splits

- `update`: examples used to expose recurring failure patterns and generate candidate skill updates.
- `validation`: examples used by the gate to decide whether the candidate skill should be accepted.
- `holdout`: unseen examples used only for final transfer reporting.

The holdout split should not be used to write or select a skill patch.

## Live Evaluation

Live evaluation asks the model to reread the old or new skill and regenerate SQL from scratch. This is the strongest evidence that the skill text changes behavior.

## Replay Evaluation

Replay evaluation reuses stored trajectories and checks whether deterministic skill/tool policies would avoid known failures. It is cheaper and useful for debugging, but weaker than live evaluation.

## Core Metrics

- Accuracy before and after reskilling.
- Target category improvement.
- Regression count.
- Failure Avoidance Rate.
- Skill length and patch budget.
- Estimated model calls and token cost.
