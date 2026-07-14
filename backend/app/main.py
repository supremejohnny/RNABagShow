from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .catalog import TASKS, public_task_catalog
from .inference import (
    InferenceRuntimeError,
    InputValidationError,
    runtime_asset_summary,
    run_checkpoint_inference,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAX_UPLOAD_BYTES = int(os.getenv("RNABAG_MAX_UPLOAD_BYTES", str(2 * 1024**3)))
QUEUE_CAPACITY = int(os.getenv("RNABAG_QUEUE_CAPACITY", "10"))
RESULT_TTL = timedelta(seconds=int(os.getenv("RNABAG_RESULT_TTL_SECONDS", "3600")))
ALLOWED_CONTENT_TYPES = {
    "application/octet-stream",
    "text/plain",
    "text/tab-separated-values",
}
LOGGER = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in job.items()
        if key not in {"path", "completed_at_dt"}
    }


def prune_expired_jobs(app: FastAPI) -> None:
    cutoff = utc_now() - RESULT_TTL
    expired = [
        job_id
        for job_id, job in app.state.jobs.items()
        if job.get("completed_at_dt") and job["completed_at_dt"] < cutoff
    ]
    for job_id in expired:
        app.state.jobs.pop(job_id, None)


async def worker_loop(app: FastAPI) -> None:
    while True:
        job_id = await app.state.queue.get()
        job = app.state.jobs.get(job_id)
        if not job:
            app.state.queue.task_done()
            continue
        if job["status"] == "cancelled":
            Path(job["path"]).unlink(missing_ok=True)
            app.state.queue.task_done()
            continue

        try:
            job.update(status="validating", updated_at=iso_now())
            result = await asyncio.to_thread(
                run_checkpoint_inference,
                Path(job["path"]),
                filename=job["filename"],
                task=job["task"],
            )
            if job["status"] != "cancelled":
                completed_at = utc_now()
                job.update(
                    status="succeeded",
                    updated_at=completed_at.isoformat(),
                    completed_at=completed_at.isoformat(),
                    completed_at_dt=completed_at,
                    result=result,
                )
        except InputValidationError as exc:
            completed_at = utc_now()
            job.update(
                status="failed",
                updated_at=completed_at.isoformat(),
                completed_at=completed_at.isoformat(),
                completed_at_dt=completed_at,
                error={"code": exc.code, "message": exc.message, "line": exc.line},
            )
        except InferenceRuntimeError as exc:
            completed_at = utc_now()
            job.update(
                status="failed",
                updated_at=completed_at.isoformat(),
                completed_at=completed_at.isoformat(),
                completed_at_dt=completed_at,
                error={"code": exc.code, "message": exc.message},
            )
        except Exception:
            LOGGER.exception("Unexpected RNABag inference failure for analysis %s", job_id)
            completed_at = utc_now()
            job.update(
                status="failed",
                updated_at=completed_at.isoformat(),
                completed_at=completed_at.isoformat(),
                completed_at_dt=completed_at,
                error={
                    "code": "INFERENCE_FAILED",
                    "message": "The local inference worker failed unexpectedly.",
                },
            )
        finally:
            Path(job["path"]).unlink(missing_ok=True)
            app.state.queue.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configured_temp = os.getenv("RNABAG_TEMP_DIR")
    if configured_temp:
        temp_dir = Path(configured_temp).expanduser().resolve()
        temp_dir.mkdir(parents=True, exist_ok=True)
        owns_temp_dir = False
    else:
        temp_dir = Path(tempfile.mkdtemp(prefix="rnabag-local-"))
        owns_temp_dir = True

    app.state.temp_dir = temp_dir
    app.state.owns_temp_dir = owns_temp_dir
    app.state.jobs = {}
    app.state.queue = asyncio.Queue(maxsize=QUEUE_CAPACITY)
    app.state.worker_task = asyncio.create_task(worker_loop(app))
    try:
        yield
    finally:
        app.state.worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await app.state.worker_task
        for job in app.state.jobs.values():
            if job.get("path"):
                Path(job["path"]).unlink(missing_ok=True)
        if app.state.owns_temp_dir:
            shutil.rmtree(app.state.temp_dir, ignore_errors=True)


app = FastAPI(
    title="RNABag Local API",
    version="0.2.0",
    description="Local RNABag API backed by the project checkpoints.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["null"],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-RNABag-Filename"],
)


@app.get("/api/v1/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok", "mode": "checkpoint"}


@app.get("/api/v1/health/ready")
async def health_ready(request: Request) -> dict[str, Any]:
    try:
        assets = runtime_asset_summary()
    except InferenceRuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return {
        "status": "ready",
        "mode": "checkpoint",
        **assets,
        "queue_size": request.app.state.queue.qsize(),
        "queue_capacity": QUEUE_CAPACITY,
    }


@app.get("/api/v1/tasks")
async def list_tasks() -> dict[str, Any]:
    return {"mode": "checkpoint", "tasks": public_task_catalog()}


@app.post("/api/v1/analyses", status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(
    request: Request,
    task: str = Query(...),
) -> dict[str, Any]:
    prune_expired_jobs(request.app)
    definition = TASKS.get(task)
    if not definition:
        raise HTTPException(status_code=400, detail={"code": "UNKNOWN_TASK", "message": "Unknown task."})
    if not definition["enabled"]:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TASK_UNAVAILABLE",
                "message": definition.get("unavailable_reason", "Task is unavailable."),
            },
        )
    if request.app.state.queue.full():
        raise HTTPException(
            status_code=429,
            detail={"code": "QUEUE_FULL", "message": "The local inference queue is full."},
        )

    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail={"code": "UNSUPPORTED_MEDIA_TYPE", "message": "Upload a TSV file body."},
        )

    filename = unquote(request.headers.get("x-rnabag-filename", "upload.tsv")).strip()
    if not filename.lower().endswith(".tsv"):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_EXTENSION", "message": "Filename must end with .tsv."},
        )

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_CONTENT_LENGTH", "message": "Invalid Content-Length header."},
            ) from exc
        if declared_size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail={"code": "FILE_TOO_LARGE", "message": "Upload exceeds the configured size limit."},
            )

    job_id = str(uuid.uuid4())
    upload_path = request.app.state.temp_dir / f"{job_id}.tsv"
    digest = hashlib.sha256()
    size_bytes = 0
    try:
        with upload_path.open("wb") as handle:
            async for chunk in request.stream():
                if not chunk:
                    continue
                size_bytes += len(chunk)
                if size_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail={
                            "code": "FILE_TOO_LARGE",
                            "message": "Upload exceeds the configured size limit.",
                        },
                    )
                digest.update(chunk)
                handle.write(chunk)
    except Exception:
        upload_path.unlink(missing_ok=True)
        raise

    if size_bytes == 0:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail={"code": "EMPTY_FILE", "message": "Uploaded file is empty."},
        )

    created_at = iso_now()
    job = {
        "analysis_id": job_id,
        "status": "queued",
        "task": task,
        "modality": definition["modality"],
        "filename": Path(filename).name,
        "size_bytes": size_bytes,
        "file_digest": digest.hexdigest(),
        "created_at": created_at,
        "updated_at": created_at,
        "path": str(upload_path),
        "mode": "checkpoint",
    }
    request.app.state.jobs[job_id] = job
    try:
        request.app.state.queue.put_nowait(job_id)
    except asyncio.QueueFull as exc:
        request.app.state.jobs.pop(job_id, None)
        upload_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=429,
            detail={"code": "QUEUE_FULL", "message": "The local inference queue is full."},
        ) from exc
    return public_job(job)


@app.get("/api/v1/analyses/{analysis_id}")
async def get_analysis(analysis_id: str, request: Request) -> dict[str, Any]:
    prune_expired_jobs(request.app)
    job = request.app.state.jobs.get(analysis_id)
    if not job:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Analysis not found."})
    return public_job(job)


@app.get("/api/v1/analyses/{analysis_id}/result")
async def get_result(analysis_id: str, request: Request) -> dict[str, Any]:
    job = request.app.state.jobs.get(analysis_id)
    if not job:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Analysis not found."})
    if job["status"] != "succeeded":
        raise HTTPException(
            status_code=409,
            detail={"code": "RESULT_NOT_READY", "message": "Analysis result is not ready."},
        )
    return job["result"]


@app.delete("/api/v1/analyses/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(analysis_id: str, request: Request) -> Response:
    job = request.app.state.jobs.get(analysis_id)
    if not job:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Analysis not found."})
    job["status"] = "cancelled"
    Path(job["path"]).unlink(missing_ok=True)
    request.app.state.jobs.pop(analysis_id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "index.html")


app.mount("/frontend", StaticFiles(directory=PROJECT_ROOT / "frontend", html=True), name="frontend")
app.mount("/asset", StaticFiles(directory=PROJECT_ROOT / "asset"), name="asset")
