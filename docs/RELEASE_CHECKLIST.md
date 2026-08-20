# Release Checklist

Before publishing a release:

- Run `uv run pytest -q`.
- Confirm `.env` and provider keys are ignored.
- Confirm BIRD raw files are not committed.
- Update `CHANGELOG.md`.
- Check that `README.md` shows the latest public metrics.
- Regenerate the showcase report if needed.
- Create a GitHub release tag such as `v0.1.0`.

Optional checks:

- Re-run a small live comparison.
- Re-run replay ablation.
- Review regression memory for sensitive examples.
