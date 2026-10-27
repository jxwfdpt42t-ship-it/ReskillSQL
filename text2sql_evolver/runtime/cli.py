from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .service import Runtime


def main():
    # Private tasks, SQL and local reports must not be world-readable by default.
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Single-host ReskillSQL deployment runtime")
    parser.add_argument("--root", type=Path, default=Path(os.getenv("TEXT2SQL_RUNTIME_ROOT", "var/runtime")))
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--database", action="append", required=True, metavar="ALIAS=SQLITE_PATH")
    init.add_argument("--skill", type=Path)
    init.add_argument("--memory", action="store_true")
    worker = commands.add_parser("worker")
    worker.add_argument("--kind", choices=["query", "evolve"], required=True)
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--lease-seconds", type=int, default=60)
    worker.add_argument("--timeout", type=int)
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    submit = commands.add_parser("submit-evolve")
    for name in ("update", "validation", "release-checks"):
        submit.add_argument("--" + name, type=Path, required=True)
    submit.add_argument("--key", required=True)
    status = commands.add_parser("status")
    status.add_argument("job_id", nargs="?")
    rollback = commands.add_parser("rollback")
    rollback.add_argument("release_id")
    rollback.add_argument("--expected-revision", type=int, required=True)
    args = parser.parse_args()
    runtime = Runtime(args.root)
    if args.command == "init":
        from dataclasses import replace
        from text2sql_evolver.config import load_settings
        settings = load_settings()
        if args.skill:
            settings = replace(settings, query_skill_path=args.skill)
        databases = dict(item.split("=", 1) for item in args.database)
        result = runtime.initialize(settings, databases, memory=args.memory)
    elif args.command == "worker":
        from .worker import serve_worker
        serve_worker(args.root, args.kind, once=args.once, lease_seconds=args.lease_seconds, timeout=args.timeout)
        return
    elif args.command == "serve":
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(args.root), host=args.host, port=args.port, limit_concurrency=100,
                    timeout_keep_alive=5, access_log=False)
        return
    elif args.command == "submit-evolve":
        result = runtime.submit_evolution(args.update, args.validation, args.release_checks, args.key)
    elif args.command == "status":
        result = runtime.store.get(args.job_id) if args.job_id else runtime.store.current()
    else:
        manifest = runtime.store.release(args.release_id)
        runtime.releases.verify(manifest)
        runtime.store.rollback(args.release_id, args.expected_revision)
        result = runtime.store.current()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
