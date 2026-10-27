from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import multiprocessing
from pathlib import Path
import sqlite3
import sys
import threading
from types import SimpleNamespace

import pytest

from text2sql_evolver.config import Settings
from text2sql_evolver.memory.experience_store import ExperienceStore
from text2sql_evolver.runtime.artifacts import checksum, snapshot_sqlite
from text2sql_evolver.runtime.service import Runtime
from text2sql_evolver.runtime.store import Conflict, ControlStore, LeaseLost, QueueFull
from text2sql_evolver.runtime.worker import run_once
from text2sql_evolver.validators.sql_aware_gate import SQLAwareGate


@pytest.fixture
def setup(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("runtime")
    source = tmp_path / "source.sqlite"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE items(id INTEGER)")
        db.executemany("INSERT INTO items VALUES (?)", [(1,), (2,), (3,)])
    skill = tmp_path / "original.md"
    skill.write_text("Return only requested columns.\n")
    settings = Settings(tmp_path, source, tmp_path / "data.jsonl", tmp_path / "reports",
                        "test-model", "test-key", "http://unused", skill)
    runtime = Runtime(tmp_path / "runtime")
    runtime.initialize(settings, {"demo": source})
    return runtime, settings


def publish_fixture(runtime):
    active = runtime.store.current()
    parent = runtime.store.release(active["release_id"])
    folder = runtime.releases.verify(parent)
    new = runtime.releases.build(folder / "SKILL.md", folder / "memory.sqlite", profile=parent["profile"],
                                 parent_revision=active["revision"])
    job = runtime.store.enqueue("evolve", {"release_id": active["release_id"], "parent_revision": active["revision"]}, new["id"])
    claim = runtime.store.claim("evolve")
    runtime.store.finish(job["id"], claim["lease_token"], {}, manifest=new)
    return new


def claim_process(root):
    job = ControlStore(Path(root)).claim("query")
    return job["id"] if job else None


def test_multiprocess_claims_are_exclusive(tmp_path):
    store = ControlStore(tmp_path)
    for i in range(12):
        store.enqueue("query", {"i": i}, str(i))
    with ProcessPoolExecutor(4, mp_context=multiprocessing.get_context("spawn")) as pool:
        ids = list(pool.map(claim_process, [str(tmp_path)] * 16))
    ids = [i for i in ids if i]
    assert len(ids) == len(set(ids)) == 12


def test_expired_worker_cannot_finish_or_publish(setup):
    runtime, _ = setup
    active = runtime.store.current()
    job = runtime.store.enqueue("evolve", {"release_id": active["release_id"], "parent_revision": active["revision"]}, "first")
    old = runtime.store.claim("evolve")
    with runtime.store.connect(write=True) as db:
        db.execute("UPDATE jobs SET lease_until=0 WHERE id=?", (job["id"],))
    new = runtime.store.claim("evolve")
    with pytest.raises(LeaseLost):
        runtime.store.finish(job["id"], old["lease_token"], {})
    with pytest.raises(LeaseLost):
        runtime.store.heartbeat(job["id"], old["lease_token"])
    runtime.store.finish(job["id"], new["lease_token"], {"ok": True})
    assert runtime.store.get(job["id"])["attempts"] == 2
    assert runtime.store.current() == active


def test_exhausted_crash_is_terminal(tmp_path):
    store = ControlStore(tmp_path)
    job = store.enqueue("query", {}, "once", max_attempts=1)
    store.claim("query")
    with store.connect(write=True) as db:
        db.execute("UPDATE jobs SET lease_until=0")
    assert store.claim("query") is None
    assert store.get(job["id"])["state"] == "failed"


def test_idempotency_pins_original_release(setup):
    runtime, _ = setup
    first = runtime.submit_query("demo", "count items", None, "request-1")
    publish_fixture(runtime)
    same = runtime.submit_query("demo", "count items", None, "request-1")
    assert same["id"] == first["id"]
    assert same["payload"]["release_id"] == first["payload"]["release_id"]
    with pytest.raises(Conflict):
        runtime.submit_query("demo", "different question", None, "request-1")


def test_capacity_is_separate_for_learning(tmp_path):
    store = ControlStore(tmp_path)
    store.enqueue("query", {}, "a", capacity=1)
    with pytest.raises(QueueFull):
        store.enqueue("query", {}, "b", capacity=1)
    assert store.enqueue("evolve", {}, "c", capacity=1)


def test_cas_rejects_late_release_and_rollback_aba(setup):
    runtime, _ = setup
    original = runtime.store.current()
    parent = runtime.store.release(original["release_id"])
    path = runtime.releases.verify(parent)
    pending = runtime.store.enqueue("evolve", {"release_id": parent["id"], "parent_revision": 1}, "pending")
    claim = runtime.store.claim("evolve")
    new = publish_fixture(runtime)
    runtime.store.rollback(parent["id"], 2)
    assert runtime.store.current()["revision"] == 3
    late = runtime.releases.build(path / "SKILL.md", path / "memory.sqlite", profile=parent["profile"], parent_revision=1)
    runtime.store.finish(pending["id"], claim["lease_token"], {}, manifest=late)
    assert runtime.store.get(pending["id"])["state"] == "stale"
    assert runtime.store.current() == {"release_id": parent["id"], "revision": 3}
    with pytest.raises(Conflict):
        runtime.store.rollback(new["id"], 1)


def test_atomic_publish_and_ack_are_rolled_back_together(setup):
    runtime, _ = setup
    active = runtime.store.current()
    parent = runtime.store.release(active["release_id"])
    path = runtime.releases.verify(parent)
    proposed = runtime.releases.build(path / "SKILL.md", path / "memory.sqlite", profile=parent["profile"], parent_revision=1)
    job = runtime.store.enqueue("evolve", {"release_id": parent["id"], "parent_revision": 1}, "failure")
    claim = runtime.store.claim("evolve")
    with runtime.store.connect(write=True) as db:
        db.execute("""CREATE TRIGGER abort_finish BEFORE UPDATE OF state ON jobs
                      WHEN NEW.state='succeeded' BEGIN SELECT RAISE(ABORT,'simulated disk failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        runtime.store.finish(job["id"], claim["lease_token"], {}, manifest=proposed)
    assert runtime.store.current() == active
    assert runtime.store.get(job["id"])["state"] == "running"
    with pytest.raises(KeyError):
        runtime.store.release(proposed["id"])


def test_workspace_isolation_and_artifact_integrity(setup, tmp_path):
    runtime, settings = setup
    manifest = runtime.store.release(runtime.store.current()["release_id"])
    a = runtime.settings_for(settings, manifest, tmp_path / "a", learning=True)
    b = runtime.settings_for(settings, manifest, tmp_path / "b", learning=True)
    a.query_skill_path.write_text("candidate")
    ExperienceStore(a.memory_path).add("new", "intent", "content", [1.0], {})
    assert b.query_skill_path.read_text() != "candidate"
    assert ExperienceStore(b.memory_path).rows() == []
    release = runtime.releases.verify(manifest)
    assert ExperienceStore(release / "memory.sqlite", readonly=True).rows() == []
    (release / "SKILL.md").chmod(0o600)
    (release / "SKILL.md").write_text("corruption")
    with pytest.raises(ValueError, match="checksum"):
        runtime.releases.verify(manifest)


def test_sqlite_snapshot_includes_wal(tmp_path):
    source, target = tmp_path / "wal.sqlite", tmp_path / "snapshot.sqlite"
    with sqlite3.connect(source) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE x(v)")
        db.execute("INSERT INTO x VALUES (42)")
        db.commit()
        snapshot_sqlite(source, target)
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT v FROM x").fetchone()[0] == 42


def write_datasets(tmp_path):
    paths = []
    for role in ("update", "validation", "release_checks"):
        path = tmp_path / (role + ".jsonl")
        path.write_text(json.dumps({"id": role, "source_id": role, "db_id": "demo",
                                    "question": role + " count items", "gold_sql": "SELECT count(*) FROM items",
                                    "db_path": "/untrusted/arbitrary.sqlite"}) + "\n")
        paths.append(path)
    return paths


def test_submission_freezes_inputs_and_rejects_overlap(setup, tmp_path):
    runtime, _ = setup
    paths = write_datasets(runtime.root.parent)
    job = runtime.submit_evolution(*paths, "round-1")
    frozen = Path(job["payload"]["datasets"]["update"]["path"])
    row = json.loads(frozen.read_text())
    assert row["db_path"] == runtime.databases()["demo"]["path"]
    paths[0].write_text("modified original")
    assert json.loads(frozen.read_text())["id"] == "update"
    paths = write_datasets(runtime.root.parent)
    row = json.loads(paths[1].read_text())
    row["source_id"] = "update"
    paths[1].write_text(json.dumps(row))
    with pytest.raises(ValueError, match="overlapping"):
        runtime.submit_evolution(*paths, "bad-round")


@pytest.mark.parametrize("after, published", [(True, True), (False, False)])
def test_final_bundle_gate_and_no_active_mutation(setup, tmp_path, monkeypatch, after, published):
    runtime, settings = setup
    paths = write_datasets(runtime.root.parent)
    job = runtime.submit_evolution(*paths, "round")
    original = runtime.store.current()
    seen = []

    class FakeOrchestrator:
        def __init__(self, settings, *args, **kwargs):
            assert kwargs["gate"].allow_weak_pass is False
            self.settings = settings

        def run(self, *args, **kwargs):
            self.settings.query_skill_path.write_text("candidate rule")
            ExperienceStore(self.settings.memory_path).add("experience", "intent", "text", [1.0], {})
            return SimpleNamespace(run_dir=tmp_path / "report")

    def evaluate(cfg, examples):
        seen.append(cfg)
        assert cfg.memory_mode != "learn"
        return {"release_checks": True if len(seen) == 1 else after}

    monkeypatch.setattr("text2sql_evolver.core.orchestrator.EvolutionOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(runtime, "evaluate", evaluate)
    outcome = runtime.execute(job, tmp_path / "work", settings)
    assert ("manifest" in outcome) == published
    assert runtime.store.current() == original
    if published:
        path = runtime.releases.verify(outcome["manifest"])
        assert (path / "SKILL.md").read_text() == "candidate rule"
        assert ExperienceStore(path / "memory.sqlite", readonly=True).has("experience")


def test_strict_gate_aligns_ids_and_rejects_regression():
    gate = SQLAwareGate(allow_weak_pass=False, min_score=0)
    before = [{"id": "a", "correct": True}, {"id": "b", "correct": False}, {"id": "c", "correct": False}]
    after = [{"id": "c", "correct": True}, {"id": "b", "correct": True}, {"id": "a", "correct": False}]
    result = gate.decide(before_rows=before, after_rows=after, patch_metadata=[])
    assert not result.accepted
    assert result.metrics["regressions"] == ["a"]
    with pytest.raises(ValueError, match="matching"):
        gate.decide(before_rows=before, after_rows=after[:2], patch_metadata=[])


def test_worker_timeout_is_bounded_and_preserves_release(setup):
    runtime, _ = setup
    original = runtime.store.current()
    job = runtime.submit_query("demo", "count items", None, "timeout")
    run_once(runtime, "query", timeout=0.05,
             command=[sys.executable, "-c", "import time; time.sleep(60)"])
    assert runtime.store.get(job["id"])["state"] == "queued"
    assert runtime.store.get(job["id"])["error"] == "TimeoutError"
    assert runtime.store.current() == original


def test_api_auth_validation_and_idempotency(setup):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from text2sql_evolver.runtime.api import create_app
    runtime, _ = setup
    client = TestClient(create_app(runtime.root, "t" * 32))
    headers = {"Authorization": "Bearer " + "t" * 32, "Idempotency-Key": "one"}
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers=headers).status_code == 200
    body = {"database": "demo", "question": "count items"}
    first = client.post("/v1/queries", headers=headers, json=body)
    assert first.status_code == 202
    assert client.post("/v1/queries", headers=headers, json=body).json() == first.json()
    assert client.post("/v1/queries", headers=headers, json={**body, "question": "other"}).status_code == 409
    assert client.post("/v1/queries", headers=headers, json={**body, "db_path": "/tmp/x"}).status_code == 422
    assert client.post("/v1/queries", headers=headers, content=b"x" * 131073).status_code == 413
    job = client.get("/v1/jobs/" + first.json()["job_id"], headers=headers).json()
    assert "lease_token" not in job and "payload" not in job


@pytest.mark.parametrize("kind", ["query", "evolve"])
def test_real_child_process_with_local_provider(setup, monkeypatch, kind):
    runtime, settings = setup

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            response = {"id": "test", "object": "chat.completion", "created": 0, "model": "test-model",
                        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "SELECT count(*) FROM items;"}}]}
            if self.path.endswith("/embeddings"):
                inputs = request["input"]
                inputs = inputs if isinstance(inputs, list) else [inputs]
                response = {"object": "list", "model": "test-embedding", "usage": {"prompt_tokens": 1, "total_tokens": 1},
                            "data": [{"object": "embedding", "index": i, "embedding": [1.0, 0.0, 0.0]}
                                     for i in range(len(inputs))]}
            elif "Summarize a SQL experience" in request["messages"][0]["content"]:
                response["choices"][0]["message"]["content"] = "- Use COUNT for a total.\n- Do not infer correctness from execution alone."
            data = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        local = Runtime(runtime.root.parent / "local-provider")
        settings = replace(settings, base_url=f"http://127.0.0.1:{server.server_port}/v1", memory_embedding_model="test-embedding")
        local.initialize(settings, {"demo": settings.database_path}, memory=kind == "evolve")
        monkeypatch.setenv("OPENAI_API_KEY", "local-test-key")
        if kind == "query":
            job = local.submit_query("demo", "count items", None, "query")
        else:
            job = local.submit_evolution(*write_datasets(runtime.root.parent), "round")
        assert run_once(local, kind, timeout=30)
        completed = local.store.get(job["id"])
        assert completed["state"] == "succeeded", completed
        if kind == "query":
            assert completed["result"]["rows"] == [[3]]
            assert completed["result"]["release_id"] == job["payload"]["release_id"]
        else:
            assert completed["result"]["published"]
            assert local.store.current()["revision"] == 2
            path = local.releases.verify(local.store.release(local.store.current()["release_id"]))
            rows = ExperienceStore(path / "memory.sqlite", readonly=True).rows()
            assert rows and all(row["metadata"]["role"] == "update" for row in rows)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
