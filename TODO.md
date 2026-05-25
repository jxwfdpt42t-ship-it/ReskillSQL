# Text-to-SQL Skill Evolution TODO

## Current Status

- DeepAgents text-to-sql baseline has been copied into this project.
- `chinook.db` has been downloaded for the first local smoke test.
- `.env` has been copied from `/Users/houhoushufan/Desktop/emnlp-test/.env`.
- `agent.py` now uses `langchain-openai` and the Azure OpenAI-compatible env variables.
- Dependencies install with `uv sync`.

Current blocker:

- The Azure endpoint can list model IDs, but chat/responses calls return `DeploymentNotFound`.
- This usually means the model name is not the actual Azure deployment name.
- The Azure deployment name must be confirmed before the baseline agent can run through the API.

## What Codex Can Do

1. Set up the project folder and copy the DeepAgents baseline.
2. Convert the baseline from Anthropic/Claude to OpenAI/Azure-compatible GPT.
3. Download and wire the Chinook demo database.
4. Create batch-running scripts for multiple questions.
5. Build the SQL execution judge.
6. Build a small sample dataset format for Chinook/BIRD-style examples.
7. Add `sqlglot`-based SQL clause analysis.
8. Split skills into clause-aware skill files.
9. Build failure logging and round artifacts.
10. Build the LLM diagnoser prompt.
11. Build the skill editor prompt and patch application.
12. Build skill backup, validation, and rollback.
13. Run local smoke tests and report exact failures.
14. Produce benchmark tables and round-by-round result summaries once the API/data are available.

## What You Need To Confirm Or Watch

1. Confirm the real Azure deployment name for the endpoint in `.env`.
   - The visible model IDs include names like `gpt-4.1` and `gpt-5.2`, but Azure chat calls currently return `DeploymentNotFound`.
   - We need the deployment name used for chat completions, not just the model SKU.
2. Confirm which API quota/key to spend.
   - Key2/prod endpoint connects.
   - Key3/dev endpoint currently gives a connection error from this machine.
3. Decide the final benchmark scope.
   - MVP: Chinook smoke test first, then a small BIRD subset.
   - Full version: larger BIRD split with final held-out test.
4. Provide or confirm BIRD local path and data format.
   - Need question, db path/db id, and gold SQL.
5. Keep an eye on experiment cost.
   - Each evolution round reruns train/validation/regression examples.
   - We should start with 30-50 examples before scaling.
6. Judge project positioning for interviews.
   - The claim should be: clause-aware skill evolution with validation/rollback.
   - Do not claim the clause-level diagnosis idea itself is fully novel.

## Immediate Next Steps

1. Fix Azure deployment name and run:

   ```bash
   uv run python agent.py "How many customers are from Canada?"
   ```

2. Once the smoke test works, add `run_batch.py`.
3. Add `judge.py` for execution-result comparison.
4. Add clause-aware skill files.
5. Build the first one-round evolution loop.
