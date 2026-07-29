# Metrics

## Execution Accuracy

The percentage of examples whose predicted SQL execution result matches the gold SQL execution result.

## Delta

The difference between after-skill accuracy and before-skill accuracy.

```text
delta = after_accuracy - before_accuracy
```

## Regression

A regression is an example where the old skill was correct but the new skill became wrong.

## Failure Avoidance Rate

Failure Avoidance Rate measures how many old failures become correct after reskilling.

```text
FAR = old_wrong_new_correct / old_wrong_total
```

## Category Transfer Gain

Category transfer gain reports whether a skill update improves examples in the same SQL failure category on validation or holdout splits.

## Skill Length

Skill length is tracked so the query-writing skill does not grow without bound.
