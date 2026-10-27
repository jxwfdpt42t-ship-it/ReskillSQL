# Serving and background evolution

This runtime supports **one trusted tenant on one Linux host with a local disk**. It adds an authenticated asynchronous query API, persistent job queues, supervised workers, and atomic publication of a Skill/Memory pair. It does not claim a deployed public service, multi-host HA, tenant isolation, or measured production throughput. macOS is supported for development; systemd units target Linux.

## Execution and publication

```text
POST query + Idempotency-Key
  -> persist job with current release ID -> return 202
  -> query worker claims lease -> child pins immutable Skill + read-only Memory
  -> generate/repair SQL against registered read-only database snapshot
  -> persist SQL + up to 100 rows -> client polls job

Administrator submits verified development datasets
  -> freeze input -> enqueue evolution with parent release ID + revision
  -> independent job/attempt directory: copied Skill + copied Memory
  -> existing evolution loop with strict no-regression Skill gate
  -> finish round; learn Memory only in this private workspace
  -> compare FINAL bundle against parent on separate release-check data
  -> write checksummed immutable release files
  -> one transaction: check lease + parent revision, switch pointer, finish job
```

Online queries do not supply gold SQL, generate rewards, or write memories. Background learning requires an administrator-provided, verified reference dataset. SQL execution success is not a correctness label. `release_checks` is additional **development promotion data**, not final holdout. Final holdout must never select a deployed version or enter memory. The runtime rejects explicit test/holdout filenames and row roles, but cannot detect deliberately relabeled data or unreliable source IDs.

### Concurrency guarantees

- SQLite WAL transactions serialize claims; query and evolution queues have separate capacities (1,000 and 20 pending/running jobs). Separate workers prevent long learning jobs occupying all query executors.
- Claims receive unique fencing tokens and renewable leases. Expired attempts cannot acknowledge a job or publish; another worker may retry up to the configured attempt budget (default 2). Failures use bounded backoff; exhausted jobs remain inspectable as `failed`.
- Every attempt runs in a separate process and directory. Parent workers enforce wall-clock deadlines and kill the process group on timeout/shutdown/lease loss. Linux service units additionally bound memory and process counts.
- Delivery is **at least once**, not exactly once. A crash can cause repeated provider calls and additional charges. Only fenced completion/publication and Memory feedback events are idempotent. An idempotency key reused with different content returns 409.
- Queries pin the release at submission, including when queued across a release change. A retry with the same idempotency key returns the original job/version.
- Releases contain Skill, a SQLite Memory snapshot, and a checksummed manifest including the generation/retrieval profile. SQLite backup captures committed WAL data. Files are fsynced before registration; partially staged or unregistered releases are never served.
- Active release changes and job acknowledgement share one SQLite transaction. Concurrent evolution based on the same parent can produce only one winner. A loser ends as `stale`, retaining its local reports; it is not automatically rebased or merged. Submit a new job/key against the current version if still needed.
- Rollback switches the entire Skill/Memory pair and increments a monotonic revision. An old worker cannot publish after an A→B→A rollback (ABA protection). Already queued/in-flight requests keep their pinned versions; rollback affects new submissions.

The original `text2sql-evolve` and `agent.py` remain research/interactive entry points. They do not acquire runtime leases. Do not point those commands at runtime release files. Concurrent runtime jobs write only their own workspaces.

## Local setup

```bash
uv sync --frozen --extra serve --extra dev

# Configure your existing model credentials through the environment.
export GEMINI_API_KEY='<provider-key>'
export MODEL_NAME='gemini-2.5-flash'
export TEXT2SQL_RUNTIME_ROOT="$PWD/var/runtime"
export TEXT2SQL_SERVE_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

# This copies a SQLite snapshot; no public API can supply arbitrary file paths.
uv run --extra serve text2sql-runtime init --database shop=/absolute/path/shop.sqlite

# Separate terminals/processes:
uv run --extra serve text2sql-runtime serve
uv run --extra serve text2sql-runtime worker --kind query
uv run --extra serve text2sql-runtime worker --kind evolve
```

To enable Memory, configure `TEXT2SQL_MEMORY_EMBEDDING_MODEL`, optionally its base URL/API key, and pass `--memory` to **init**. Runtime starts with an empty library, rather than importing unreviewed historical test evidence. Model/retrieval settings are pinned in the release manifest; changing environment model names later does not silently change a published version. Credentials remain in the environment. Use a fresh runtime and revalidate when changing the model/embedding profile or database snapshot; automatic profile/data migrations are not implemented.

```bash
curl --fail http://127.0.0.1:8000/v1/queries \
  -H "Authorization: Bearer $TEXT2SQL_SERVE_TOKEN" \
  -H 'Idempotency-Key: request-001' \
  -H 'Content-Type: application/json' \
  -d '{"database":"shop","question":"How many customers are there?"}'

curl --fail http://127.0.0.1:8000/v1/jobs/<job-id> \
  -H "Authorization: Bearer $TEXT2SQL_SERVE_TOKEN"
```

`queued/running/succeeded/failed` are query lifecycle states. A succeeded job can contain `execution_ok=false`: processing completed but SQL failed; it is not a semantically correct answer. Result rows are capped at 100, with `rows_truncated`; blobs use `{ "hex": "..." }` and non-finite floats use `{ "float": "..." }`. Oversized final results fail with `result_too_large`. Automatic SQL repair and other provider calls count toward the worker deadline. Research generation/judging can still materialize larger intermediate results; use the supplied process memory limits for bounded deployment.

HTTP requires a bearer token of at least 32 characters, limits request size (including chunked bodies), rejects unexpected fields, and returns only query-job public fields. Job IDs are not authorization boundaries: all holders of this single-tenant token share access. For external access, terminate TLS and enforce connection/request rate limits at an authenticated reverse proxy. Do not expose plain HTTP directly to the Internet. Evolution, release publication, and rollback are deliberately CLI-only, under the deployment OS account.

## Submit a background learning round

Prepare three non-overlapping **development** JSONL files: `update.jsonl`, `validation.jsonl`, and `release_checks.jsonl`. Each row uses the existing format plus a mandatory registered `db_id` and stable `source_id`:

```json
{"id":"task-1","source_id":"original-1","db_id":"shop","question":"How many customers are there?","gold_sql":"SELECT COUNT(*) FROM customers","evidence":null,"tags":["aggregation"]}
```

`source_family` may group derived examples. The runtime currently requires unique source families and normalized questions throughout a submitted round, verifies executable references, overrides caller-supplied `db_path` with the registered database snapshot, and freezes JSONL inputs with checksums. The administrator must separately verify reference semantics; executability is insufficient.

```bash
uv run --extra serve text2sql-runtime submit-evolve \
  --update /data/reviewed/update.jsonl \
  --validation /data/reviewed/validation.jsonl \
  --release-checks /data/reviewed/release_checks.jsonl \
  --key reviewed-round-001

uv run --extra serve text2sql-runtime status <job-id>
uv run --extra serve text2sql-runtime status
```

Runtime Skill selection rejects weak passes; the research CLI retains its previous default. The post-learning bundle check requires no old-correct/new-wrong cases and nondecreasing total correct answers. Equality is allowed so a Memory-only release can retain newly learned evidence; this is a finite-set guard, **not proof of future zero regression**. Rejected bundles keep all attempt-local Skill/Memory evidence and reports but publish nothing. Those unapproved memories are not merged into the serving release.

This path requires verified development tasks, not a queue of unlabelled production failures. New queries persist their question, result and release references; automatic human-feedback ingestion, label review UI and reward estimation are not implemented.

## Linux service installation

Install the checkout and locked environment at `/opt/reskill`. Create a dedicated `reskill` account and private `/var/lib/reskill` directory owned by it. Place credentials, `MODEL_NAME`, the serving token, and `TEXT2SQL_RUNTIME_ROOT=/var/lib/reskill` in `/etc/reskill/runtime.env` (owner root, mode 0600). Initialize the runtime as the service account with the same environment before starting services. The account must be able to read the source databases during initialization; serving uses its private copies afterward.

Copy the three files from [`deploy/systemd`](../deploy/systemd/) into `/etc/systemd/system/`, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now reskill-api reskill-query@1 reskill-evolve
# Optional additional query worker, subject to provider limits and host capacity:
sudo systemctl enable --now reskill-query@2
```

These units bind the API to loopback, limit writable paths, run without root, restart on failure, and bound memory. Adjust `/opt/reskill`, account names and budgets to your host. They are deployment templates; installing them requires a Linux host and operational verification. Do not share the SQLite runtime directory over NFS or across hosts. For multi-host deployment replace the control database/queue and lease implementation with an appropriate transactional service rather than mounting this directory remotely.

## Rollback, operations and recovery

```bash
uv run --extra serve text2sql-runtime status
uv run --extra serve text2sql-runtime rollback <known-release-id> --expected-revision <current-revision>
```

Rollback verifies the stored bundle and uses compare-and-swap; an outdated expected revision fails. It does not cancel existing requests. In an emergency requiring removal from in-flight use, stop query workers and the API first; do not delete referenced releases.

Private runtime contents:

```text
control.sqlite + WAL/SHM       jobs, leases, current revision, release registry, audit events
config.json                   approved database aliases and hashes
databases/                    read-only database snapshots
inputs/<content-hash>/        frozen development JSONL
jobs/<job-id>/<lease-token>/  isolated attempts, logs, reports, candidate Skill/Memory
releases/<release-id>/        immutable Skill, Memory, manifest
```

Monitor pending/running/failed/stale jobs, oldest queue age, failed/expired leases, worker logs, provider errors, disk usage, and release-check rejection counts. `/health` confirms API/control availability and active version; it does not prove worker availability or model-provider health. `control.sqlite`'s `events` table records publication and rollback history. No external monitoring backend or automated retention is installed.

For a consistent backup, stop API and workers, then copy the **entire runtime directory**, including SQLite WAL/SHM if present. Restore at the same absolute path: Memory scope includes database paths. Expired running jobs are recovered on the next matching worker claim. Keep credentials outside the backup policy for task data. Never delete releases referenced by current, queued or retained audit jobs. Stale/orphaned attempts may be reviewed and removed during maintenance after confirming no active lease; automated garbage collection is intentionally absent.

The lockfile and CI cover reproducible code checks. Validate TLS/proxy configuration, backup restore, actual model credentials, machine resource limits and expected workload on the target host before exposing traffic. No live deployment or paid accuracy/load experiment is implied by the repository tests.

## Tests

```bash
uv run --frozen --extra dev --extra serve pytest -q
```

Tests include multi-process claim contention, lease fencing and retry exhaustion, idempotency across releases, transaction rollback between publish/ack, stale publication and rollback ABA, independent workspaces, WAL-aware snapshots, final bundle rejection, API authentication/body bounds, and real child-process query/evolution runs against a local mock model and embedding endpoint. They do not use live provider calls or establish SQL accuracy gains.

References: [SQLite WAL deployment constraints](https://www.sqlite.org/wal.html), [FastAPI process deployment](https://fastapi.tiangolo.com/deployment/server-workers/).
