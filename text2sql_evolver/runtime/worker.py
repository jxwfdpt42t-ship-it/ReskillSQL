"""Supervise each job in a killable child process; never mutate an active release."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from .artifacts import write_json
from .service import Runtime
from .store import LeaseLost


def stop_child(child):
    if child.poll() is None:
        os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()


def run_once(runtime, kind, *, lease_seconds=60, timeout=3600, stopping=lambda: False, command=None):
    job = runtime.store.claim(kind, lease_seconds)
    if job is None:
        return False
    token = job["lease_token"]
    work = runtime.root / "jobs" / job["id"] / token
    args = command or [sys.executable, "-m", "text2sql_evolver.runtime.worker", str(runtime.root), job["id"], token]
    child = None
    started = time.monotonic()
    next_heartbeat = started
    try:
        work.mkdir(parents=True, mode=0o700)
        with (work / "worker.log").open("wb") as log:
            child = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            while child.poll() is None:
                if stopping():
                    raise InterruptedError("worker_shutdown")
                if time.monotonic() - started > timeout:
                    raise TimeoutError("job_timeout")
                if time.monotonic() >= next_heartbeat:
                    runtime.store.heartbeat(job["id"], token, lease_seconds)
                    next_heartbeat = time.monotonic() + lease_seconds / 3
                time.sleep(min(0.2, lease_seconds / 6))
        # Renew before checksumming potentially large release files.
        runtime.store.heartbeat(job["id"], token, lease_seconds)
        outcome = json.loads((work / "outcome.json").read_text())
        if child.returncode != 0 or "error" in outcome:
            runtime.store.fail(job["id"], token, outcome.get("error", "child_failed"), retry=outcome.get("retry", True))
        else:
            if len(json.dumps(outcome["result"]).encode()) > 1024 * 1024:
                runtime.store.fail(job["id"], token, "result_too_large", retry=False)
                return True
            manifest = outcome.get("manifest")
            if manifest:
                runtime.releases.verify(manifest)
            runtime.store.finish(job["id"], token, outcome["result"], manifest=manifest)
    except LeaseLost:
        # A later attempt owns the job. This process must neither ack nor publish.
        pass
    except Exception as exc:
        try:
            runtime.store.fail(job["id"], token, type(exc).__name__, retry=True)
        except LeaseLost:
            pass
    finally:
        if child is not None:
            stop_child(child)
    return True


def serve_worker(root, kind, *, once=False, lease_seconds=60, timeout=None):
    if lease_seconds < 6:
        raise ValueError("Worker lease must be at least 6 seconds")
    if timeout is not None and timeout <= 0:
        raise ValueError("Worker timeout must be positive")
    runtime = Runtime(root)
    stopped = False

    def stop(signum, frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopped:
        found = run_once(runtime, kind, lease_seconds=lease_seconds,
                         timeout=timeout or (180 if kind == "query" else 3600), stopping=lambda: stopped)
        if once:
            return
        if not found:
            time.sleep(0.5)


def child_main(root, job_id, token):
    runtime = Runtime(root)
    job = runtime.store.get(job_id)
    if job["lease_token"] != token or job["state"] != "running":
        raise LeaseLost(job_id)
    work = runtime.root / "jobs" / job_id / token
    try:
        from text2sql_evolver.config import load_settings
        outcome = runtime.execute(job, work, load_settings())
    except Exception as exc:
        # Do not persist provider exception bodies: they can contain credentials or request data.
        outcome = {"error": type(exc).__name__, "retry": not isinstance(exc, (ValueError, KeyError, FileNotFoundError))}
    write_json(work / "outcome.json", outcome)


if __name__ == "__main__":
    child_main(*sys.argv[1:])
