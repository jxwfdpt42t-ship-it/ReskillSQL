# Security Policy

## Secrets

Do not commit `.env`, API keys, provider tokens, database credentials, or private benchmark artifacts. Use `.env.example` as the public template.

## SQL Execution

The project is designed for evaluation and research workflows. SQL execution should stay read-only and timeout-bound when running model-generated queries.

## Reporting Issues

If you find a security-sensitive issue, open a private report or contact the maintainer before publishing exploit details.
