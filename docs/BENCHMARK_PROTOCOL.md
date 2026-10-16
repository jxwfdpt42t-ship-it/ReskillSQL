# Benchmark Protocol

ReskillSQL separates two evaluation goals:

1. Text-to-SQL execution accuracy.
2. Whether skill updates transfer to future SQL tasks without excessive regressions.

## Self-Update Lifecycle

The split boundaries reflect the order of a self-update, rather than only a conventional train/test split:

| Split | Purpose | Allowed use |
|---|---|---|
| `update` | Expose recurring errors and provide evidence for a candidate skill patch. | Failure attribution and patch generation. |
| `validation` | Test whether the candidate improves the target behavior without unacceptable regressions. | SQL-aware gate and promotion decision. |
| `holdout` | Measure whether the accepted behavior transfers to unseen tasks. | Final transfer reporting only. |

The holdout split should not be used to write, tune, or select a skill patch. Keeping it out of the update and gate decisions is what makes it useful as a transfer check.

When experience memory is enabled, the same boundary applies to memory state. Update and validation examples may create entries and utility feedback. Holdout evaluation must use `memory_mode=read`, exclude the current task and its stable source ancestry from retrieval, and leave both the store and Q values unchanged.

## Live vs Replay

These modes answer different questions:

- **Live evaluation** asks the model to reread the old or new skill and regenerate SQL from scratch. It is the stronger evidence that the skill text changes model behavior.
- **Replay evaluation** reuses stored execution trajectories and applies deterministic skill/tool policies to them. It is cheaper and useful for debugging or scanning broader historical slices, but it does not measure a fresh model generation.

Replay is therefore a diagnostic signal, while live evaluation is the primary check for behavior changes caused by a skill update. The two modes should be reported separately rather than treated as interchangeable scores.

## Core Metrics

- Accuracy before and after reskilling.
- Target category improvement.
- Regression count.
- Failure Avoidance Rate.
- Skill length and patch budget.
- Estimated model calls and token cost.

Memory experiments should additionally report retrieval coverage, injected-memory count, utility-selection policy, memory size, and the incremental model/embedding cost. Skill-only, memory-only, and combined results must use isolated state directories rather than sharing a mutable Skill file or memory database.
