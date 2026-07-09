# Data

This directory only commits small public examples and metadata needed for smoke tests.

Large benchmark artifacts are intentionally ignored:

- `data/bird/raw/`
- `data/bird_minidev_*.jsonl`
- `data/self_update/`

To reproduce BIRD experiments, download BIRD MiniDev locally and follow the preparation command in `README.md`.

Committed files:

- `chinook_eval.jsonl`: small SQLite smoke-test dataset.
- `regression_memory.jsonl`: example protection memory for old-correct/new-wrong cases.
- `rejected_patches.jsonl`: example rejected-patch memory used by the evolver.
