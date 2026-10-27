"""Durable jobs, fenced leases and release CAS in one SQLite transaction domain."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid


class Conflict(RuntimeError):
    pass


class QueueFull(RuntimeError):
    pass


class LeaseLost(RuntimeError):
    pass


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


class ControlStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "control.sqlite"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS releases (
                    id TEXT PRIMARY KEY, manifest TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS active (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    release_id TEXT NOT NULL, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, idem TEXT NOT NULL UNIQUE,
                    fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
                    state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL, available REAL NOT NULL,
                    lease_until REAL, lease_token TEXT, created REAL NOT NULL,
                    updated REAL NOT NULL, result TEXT, error TEXT);
                CREATE INDEX IF NOT EXISTS runnable ON jobs(kind, state, available, created);
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL,
                    kind TEXT NOT NULL, details TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self, *, write=False):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                if write:
                    db.execute("BEGIN IMMEDIATE")
                yield db
        finally:
            db.close()

    @staticmethod
    def event(db, kind, details):
        db.execute("INSERT INTO events(timestamp,kind,details) VALUES (?,?,?)",
                   (time.time(), kind, encode(details)))

    def initialize(self, manifest):
        with self.connect(write=True) as db:
            if db.execute("SELECT 1 FROM active").fetchone():
                raise Conflict("Runtime is already initialized")
            db.execute("INSERT INTO releases VALUES (?,?,?)", (manifest["id"], encode(manifest), time.time()))
            db.execute("INSERT INTO active VALUES (1,?,1)", (manifest["id"],))
            self.event(db, "initialize", {"release_id": manifest["id"], "revision": 1})

    def current(self):
        with self.connect() as db:
            row = db.execute("SELECT release_id,revision FROM active").fetchone()
            if row is None:
                raise RuntimeError("Initialize the runtime first")
            return dict(row)

    def release(self, release_id):
        with self.connect() as db:
            row = db.execute("SELECT manifest FROM releases WHERE id=?", (release_id,)).fetchone()
            if row is None:
                raise KeyError(release_id)
            return json.loads(row["manifest"])

    def enqueue(self, kind, payload, key, *, fingerprint=None, max_attempts=2, capacity=1000):
        if kind not in {"query", "evolve"} or not key or len(key) > 200 or not 1 <= max_attempts <= 5:
            raise ValueError("Invalid job type, idempotency key or retry budget")
        fingerprint = fingerprint or hashlib.sha256(encode(payload).encode()).hexdigest()
        idem = kind + ":" + key
        now = time.time()
        with self.connect(write=True) as db:
            old = db.execute("SELECT * FROM jobs WHERE idem=?", (idem,)).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise Conflict("Idempotency key was used for a different request")
                return self.decode(old)
            # Separate capacities keep long-running learning from filling the query queue.
            count = db.execute("SELECT count(*) FROM jobs WHERE kind=? AND state IN ('queued','running')", (kind,)).fetchone()[0]
            if count >= capacity:
                raise QueueFull("Queue capacity reached")
            job_id = uuid.uuid4().hex
            db.execute("""INSERT INTO jobs(id,kind,idem,fingerprint,payload,state,max_attempts,available,created,updated)
                          VALUES (?,?,?,?,?,'queued',?,?,?,?)""",
                       (job_id, kind, idem, fingerprint, encode(payload), max_attempts, now, now, now))
            self.event(db, "enqueued", {"job_id": job_id, "kind": kind})
            return self.decode(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    @staticmethod
    def decode(row):
        value = dict(row)
        value["payload"] = json.loads(value["payload"])
        value["result"] = json.loads(value["result"]) if value["result"] else None
        return value

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            return self.decode(row)

    def claim(self, kind, lease_seconds=60):
        if lease_seconds < 1:
            raise ValueError("Lease must be positive")
        with self.connect(write=True) as db:
            now = time.time()
            expired = db.execute("SELECT * FROM jobs WHERE kind=? AND state='running' AND lease_until<=?", (kind, now)).fetchall()
            for row in expired:
                state = "failed" if row["attempts"] >= row["max_attempts"] else "queued"
                db.execute("UPDATE jobs SET state=?,lease_token=NULL,lease_until=NULL,error='lease_expired',updated=? WHERE id=?",
                           (state, now, row["id"]))
                self.event(db, "lease_expired", {"job_id": row["id"], "state": state})
            row = db.execute("SELECT * FROM jobs WHERE kind=? AND state='queued' AND available<=? ORDER BY created,id LIMIT 1",
                             (kind, now)).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            db.execute("UPDATE jobs SET state='running',attempts=attempts+1,lease_token=?,lease_until=?,updated=? WHERE id=?",
                       (token, now + lease_seconds, now, row["id"]))
            self.event(db, "claimed", {"job_id": row["id"], "token": token})
            return self.decode(db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())

    def heartbeat(self, job_id, token, lease_seconds=60):
        with self.connect(write=True) as db:
            now = time.time()
            changed = db.execute("""UPDATE jobs SET lease_until=?,updated=? WHERE id=? AND state='running'
                                    AND lease_token=? AND lease_until>?""",
                                 (now + lease_seconds, now, job_id, token, now)).rowcount
            if not changed:
                raise LeaseLost(job_id)

    @staticmethod
    def owned(db, job_id, token):
        row = db.execute("SELECT * FROM jobs WHERE id=? AND state='running' AND lease_token=? AND lease_until>?",
                         (job_id, token, time.time())).fetchone()
        if row is None:
            raise LeaseLost(job_id)
        return row

    def finish(self, job_id, token, result, *, manifest=None):
        """Publication and job acknowledgement commit together; expired workers cannot publish."""
        with self.connect(write=True) as db:
            row = self.owned(db, job_id, token)
            state = "succeeded"
            if manifest is not None:
                payload = json.loads(row["payload"])
                if row["kind"] != "evolve" or manifest["parent_revision"] != payload["parent_revision"]:
                    raise ValueError("Invalid release lineage")
                active = dict(db.execute("SELECT release_id,revision FROM active").fetchone())
                if active != {"release_id": payload["release_id"], "revision": payload["parent_revision"]}:
                    state = "stale"
                    result = {**result, "published": False, "reason": "parent_version_changed"}
                else:
                    db.execute("INSERT INTO releases VALUES (?,?,?)", (manifest["id"], encode(manifest), time.time()))
                    db.execute("UPDATE active SET release_id=?,revision=revision+1 WHERE singleton=1", (manifest["id"],))
                    result = {**result, "published": True, "release_id": manifest["id"], "revision": active["revision"] + 1}
                    self.event(db, "published", {"job_id": job_id, **result})
            db.execute("UPDATE jobs SET state=?,result=?,error=NULL,lease_token=NULL,lease_until=NULL,updated=? WHERE id=?",
                       (state, encode(result), time.time(), job_id))
            self.event(db, "finished", {"job_id": job_id, "state": state})

    def fail(self, job_id, token, error_code, *, retry=True):
        with self.connect(write=True) as db:
            row = self.owned(db, job_id, token)
            state = "queued" if retry and row["attempts"] < row["max_attempts"] else "failed"
            db.execute("""UPDATE jobs SET state=?,error=?,available=?,updated=?,lease_token=NULL,lease_until=NULL WHERE id=?""",
                       (state, error_code, time.time() + min(60, 2 ** row["attempts"]), time.time(), job_id))
            self.event(db, "attempt_failed", {"job_id": job_id, "state": state, "code": error_code})

    def rollback(self, release_id, expected_revision):
        with self.connect(write=True) as db:
            if not db.execute("SELECT 1 FROM releases WHERE id=?", (release_id,)).fetchone():
                raise KeyError(release_id)
            changed = db.execute("UPDATE active SET release_id=?,revision=revision+1 WHERE singleton=1 AND revision=?",
                                 (release_id, expected_revision)).rowcount
            if not changed:
                raise Conflict("Active revision changed; inspect before retrying rollback")
            self.event(db, "rollback", {"release_id": release_id, "revision": expected_revision + 1})
