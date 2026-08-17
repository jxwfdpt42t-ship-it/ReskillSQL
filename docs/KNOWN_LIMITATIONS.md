# Known Limitations

- Live evaluation is currently reported on selected BIRD MiniDev slices, not the full official benchmark.
- Replay diagnostics are useful for debugging but should not be treated as the same evidence as live generation.
- Regression memory reduces repeated harmful updates, but it does not guarantee zero regressions.
- Multi-model validation is not included in the public 0.1.0 release.
- Token and cost fields are estimated unless a provider billing export is attached.
- The current self-update benchmark focuses on skill transfer and update behavior, not leaderboard-style Text-to-SQL ranking.
