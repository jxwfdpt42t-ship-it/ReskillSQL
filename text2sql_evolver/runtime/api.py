"""Authenticated single-tenant API. Learning and release administration stay on CLI."""
from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .service import Runtime
from .store import Conflict, QueueFull


class Query(BaseModel):
    model_config = ConfigDict(extra="forbid")
    database: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1, max_length=16000)
    evidence: str | None = Field(default=None, max_length=16000)


def create_app(root=None, token=None):
    root = Path(root or os.environ["TEXT2SQL_RUNTIME_ROOT"])
    token = token or os.getenv("TEXT2SQL_SERVE_TOKEN", "")
    if len(token) < 32:
        raise ValueError("Set a random TEXT2SQL_SERVE_TOKEN of at least 32 characters")
    if not (root / "config.json").is_file():
        raise ValueError("Initialize the runtime before starting the API")
    runtime = Runtime(root)
    runtime.releases.verify(runtime.store.release(runtime.store.current()["release_id"]))
    app = FastAPI(title="ReskillSQL Runtime", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def authenticate_and_bound(request: Request, call_next):
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied.encode(), ("Bearer " + token).encode()):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        # Bound chunked bodies too; do not rely only on a caller-controlled Content-Length.
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 128 * 1024:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
            chunks.append(chunk)
        request._body = b"".join(chunks)
        return await call_next(request)

    @app.get("/health")
    def health():
        return {"status": "ok", **runtime.store.current()}

    @app.post("/v1/queries", status_code=202)
    def query(body: Query, idempotency_key: str = Header(min_length=1, max_length=200)):
        try:
            job = runtime.submit_query(body.database, body.question, body.evidence, idempotency_key)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except QueueFull as exc:
            raise HTTPException(429, str(exc), headers={"Retry-After": "5"}) from exc
        return {"job_id": job["id"], "state": job["state"], "release_id": job["payload"]["release_id"]}

    @app.get("/v1/jobs/{job_id}")
    def status(job_id: str):
        try:
            job = runtime.store.get(job_id)
        except KeyError as exc:
            raise HTTPException(404, "Job not found") from exc
        if job["kind"] != "query":
            raise HTTPException(404, "Job not found")
        return {key: job[key] for key in ("id", "state", "attempts", "result", "error", "created", "updated")}

    return app
