# Known Limitations

- Live evaluation is currently reported on selected BIRD MiniDev slices, not the full official benchmark.
- Replay diagnostics are useful for debugging but should not be treated as the same evidence as live generation.
- Legacy regression records are diagnostic artifacts and are not automatically imported into the new experience-memory store or wired into every promotion gate.
- Multi-model validation is not included in the public 0.1.0 release.
- Token and cost fields are estimated unless a provider billing export is attached.
- The current self-update benchmark focuses on skill transfer and update behavior, not leaderboard-style Text-to-SQL ranking.
- Existing three-round reports compare a fixed old/new Skill pair on three data slices; they do not demonstrate sequential Skill evolution.
- The experience-memory implementation has behavior tests but no provider-backed accuracy result yet.
- Memory Q feedback is shared by all memories injected into one task and does not establish causal attribution for an individual memory.
- Retrieval is limited to the same database path and schema hash; cross-database memory transfer is not implemented.
