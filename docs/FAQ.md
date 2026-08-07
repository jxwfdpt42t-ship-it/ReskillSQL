# FAQ

## Does ReskillSQL fine-tune the model?

No. It updates external skills and tool-use policies. The base LLM is unchanged.

## Why not update after every failure?

A single failure can be noise. The evolver prefers recurring, fixable patterns and validates candidate skill updates before accepting them.

## Why use validation and holdout splits?

Validation decides whether a candidate skill should be accepted. Holdout estimates whether the accepted skill transfers to unseen tasks.

## Is replay evaluation enough?

No. Replay is useful for cheap diagnostics. Live evaluation is stronger because the LLM reads the skill and regenerates SQL from scratch.

## What makes this SQL-aware?

The evolver uses SQL-specific failure categories, execution feedback, clause-level signals, value lookup policies, schema context policies, and regression protection.
