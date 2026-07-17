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
from .persistence import (
    PersistenceBackend,
    PersistenceOperationError,
    PersistenceSettings,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_DATASETS = {
    "tissue": PROJECT_ROOT / "sampledata" / "tissue_sample_fpkm_to_joh.tsv",
    "platelet": PROJECT_ROOT / "sampledata" / "Platelet_sample_to_joh.tsv",
}
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


def persistence_enabled() -> bool:
    return os.getenv("RNABAG_PERSISTENCE_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def public_memory_job(job: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in job.items()
        if key not in {"path", "completed_at_dt"}
    }


def prune_expired_memory_jobs(app: FastAPI) -> None:
    cutoff = utc_now() - RESULT_TTL
    expired = [
        job_id
        for job_id, job in app.state.jobs.items()
        if job.get("completed_at_dt") and job["completed_at_dt"] < cutoff
    ]
    for job_id in expired:
        app.state.jobs.pop(job_id, None)


def try_reserve_queue_slot(app: FastAPI) -> bool:
    pending_count = app.state.queue.qsize() + app.state.queue_reservations
    if pending_count >= QUEUE_CAPACITY:
        return False
    app.state.queue_reservations += 1
    return True


def release_queue_slot(app: FastAPI) -> None:
    app.state.queue_reservations -= 1


def safe_filename(raw_filename: str) -> str:
    filename = raw_filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return "".join(character for character in filename if ord(character) >= 32)


def normalized_analysis_id(analysis_id: str) -> str:
    try:
        return str(uuid.UUID(analysis_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Analysis not found."},
        ) from exc


def input_error(exc: InputValidationError) -> dict[str, Any]:
    error: dict[str, Any] = {"code": exc.code, "message": exc.message}
    if exc.line is not None:
        error["line"] = exc.line
    return error


async def process_memory_job(app: FastAPI, job_id: str) -> None:
    job = app.state.jobs.get(job_id)
    if not job:
        return
    if job["status"] == "cancelled":
        Path(job["path"]).unlink(missing_ok=True)
        return

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
            error=input_error(exc),
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


async def process_persistent_job(
    app: FastAPI,
    persistence: PersistenceBackend,
    analysis_id: str,
) -> None:
    row = await asyncio.to_thread(persistence.claim_analysis, analysis_id)
    if row is None:
        return

    inference_path = app.state.temp_dir / f"{analysis_id}-inference.tsv"
    try:
        await asyncio.to_thread(persistence.download_for_inference, row, inference_path)
        running = await asyncio.to_thread(persistence.mark_running, analysis_id)
        if not running:
            return
        result = await asyncio.to_thread(
            run_checkpoint_inference,
            inference_path,
            filename=row["original_filename"],
            task=row["task"],
        )
        await asyncio.to_thread(persistence.mark_succeeded, analysis_id, result)
    except InputValidationError as exc:
        await asyncio.to_thread(persistence.mark_failed, analysis_id, input_error(exc))
    except InferenceRuntimeError as exc:
        await asyncio.to_thread(
            persistence.mark_failed,
            analysis_id,
            {"code": exc.code, "message": exc.message},
        )
    except PersistenceOperationError as exc:
        LOGGER.error("Persistence operation failed for analysis %s: %s", analysis_id, exc)
        await asyncio.to_thread(
            persistence.mark_failed,
            analysis_id,
            {
                "code": "PERSISTENCE_FAILED",
                "message": "Stored analysis input could not be processed.",
            },
        )
    except Exception:
        LOGGER.exception("Unexpected RNABag inference failure for analysis %s", analysis_id)
        with contextlib.suppress(Exception):
            await asyncio.to_thread(
                persistence.mark_failed,
                analysis_id,
                {
                    "code": "INFERENCE_FAILED",
                    "message": "The inference worker failed unexpectedly.",
                },
            )
    finally:
        inference_path.unlink(missing_ok=True)


async def worker_loop(app: FastAPI) -> None:
    while True:
        analysis_id = await app.state.queue.get()
        try:
            persistence = app.state.persistence
            if persistence is None:
                await process_memory_job(app, analysis_id)
            else:
                await process_persistent_job(app, persistence, analysis_id)
        except Exception:
            LOGGER.exception("RNABag worker could not process analysis %s", analysis_id)
        finally:
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
    app.state.queue = asyncio.Queue()
    app.state.queue_reservations = 0
    app.state.persistence = None

    if persistence_enabled():
        settings = PersistenceSettings.from_environment()
        persistence = PersistenceBackend(settings)
        pending_analysis_ids = await asyncio.to_thread(persistence.startup)
        app.state.persistence = persistence
        for analysis_id in pending_analysis_ids:
            app.state.queue.put_nowait(analysis_id)

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
    title="RNABag API",
    version="0.3.0",
    description="RNABag checkpoint API with optional PostgreSQL and private object persistence.",
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
        persistence = request.app.state.persistence
        if persistence is not None:
            await asyncio.to_thread(persistence.healthcheck)
    except InferenceRuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except Exception as exc:
        LOGGER.exception("RNABag persistence readiness check failed")
        raise HTTPException(
            status_code=503,
            detail={
                "code": "PERSISTENCE_UNAVAILABLE",
                "message": "The persistence services are unavailable.",
            },
        ) from exc
    return {
        "status": "ready",
        "mode": "checkpoint",
        **assets,
        "persistence": "postgres-s3" if request.app.state.persistence else "memory",
        "queue_size": request.app.state.queue.qsize(),
        "queue_capacity": QUEUE_CAPACITY,
    }


@app.get("/api/v1/tasks")
async def list_tasks() -> dict[str, Any]:
    return {"mode": "checkpoint", "tasks": public_task_catalog()}


@app.get("/api/v1/demo-data/{modality}")
async def download_demo_data(modality: str) -> FileResponse:
    path = DEMO_DATASETS.get(modality)
    if path is None or not path.is_file():
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Demo dataset not found."},
        )
    return FileResponse(
        path,
        media_type="text/tab-separated-values",
        filename=path.name,
    )


@app.post("/api/v1/analyses", status_code=status.HTTP_202_ACCEPTED)
async def create_analysis(
    request: Request,
    task: str = Query(...),
) -> dict[str, Any]:
    if request.app.state.persistence is None:
        prune_expired_memory_jobs(request.app)
    definition = TASKS.get(task)
    if not definition:
        raise HTTPException(
            status_code=400,
            detail={"code": "UNKNOWN_TASK", "message": "Unknown task."},
        )
    if not definition["enabled"]:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TASK_UNAVAILABLE",
                "message": definition.get("unavailable_reason", "Task is unavailable."),
            },
        )
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail={"code": "UNSUPPORTED_MEDIA_TYPE", "message": "Upload a TSV file body."},
        )

    filename = safe_filename(unquote(request.headers.get("x-rnabag-filename", "upload.tsv")))
    if not filename or len(filename) > 512:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_FILENAME",
                "message": "Filename must contain between 1 and 512 characters.",
            },
        )
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
        if declared_size < 0:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_CONTENT_LENGTH", "message": "Invalid Content-Length header."},
            )
        if declared_size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail={"code": "FILE_TOO_LARGE", "message": "Upload exceeds the configured size limit."},
            )

    if not try_reserve_queue_slot(request.app):
        raise HTTPException(
            status_code=429,
            detail={"code": "QUEUE_FULL", "message": "The inference queue is full."},
        )

    try:
        analysis_id = str(uuid.uuid4())
        upload_path = request.app.state.temp_dir / f"{analysis_id}-upload.tsv"
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
        except BaseException:
            upload_path.unlink(missing_ok=True)
            raise

        if size_bytes == 0:
            upload_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400,
                detail={"code": "EMPTY_FILE", "message": "Uploaded file is empty."},
            )

        persistence = request.app.state.persistence
        if persistence is not None:
            try:
                job = await asyncio.to_thread(
                    persistence.create_analysis,
                    upload_path,
                    analysis_id=analysis_id,
                    task=task,
                    modality=definition["modality"],
                    original_filename=filename,
                    file_size_bytes=size_bytes,
                    file_sha256=digest.hexdigest(),
                    content_type=content_type,
                )
            except Exception as exc:
                LOGGER.exception("Persistent analysis creation failed for %s", analysis_id)
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "PERSISTENCE_UNAVAILABLE",
                        "message": "The analysis could not be stored.",
                    },
                ) from exc
            finally:
                upload_path.unlink(missing_ok=True)
            request.app.state.queue.put_nowait(analysis_id)
            return job

        created_at = iso_now()
        job = {
            "analysis_id": analysis_id,
            "status": "queued",
            "task": task,
            "modality": definition["modality"],
            "filename": filename,
            "size_bytes": size_bytes,
            "file_digest": digest.hexdigest(),
            "created_at": created_at,
            "updated_at": created_at,
            "path": str(upload_path),
            "mode": "checkpoint",
        }
        request.app.state.jobs[analysis_id] = job
        request.app.state.queue.put_nowait(analysis_id)
        return public_memory_job(job)
    finally:
        release_queue_slot(request.app)


@app.get("/api/v1/analyses/{analysis_id}")
async def get_analysis(analysis_id: str, request: Request) -> dict[str, Any]:
    analysis_id = normalized_analysis_id(analysis_id)
    persistence = request.app.state.persistence
    if persistence is not None:
        try:
            job = await asyncio.to_thread(persistence.get_analysis, analysis_id)
        except Exception as exc:
            LOGGER.exception("Persistent analysis read failed for %s", analysis_id)
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "PERSISTENCE_UNAVAILABLE",
                    "message": "The stored analysis could not be read.",
                },
            ) from exc
    else:
        prune_expired_memory_jobs(request.app)
        memory_job = request.app.state.jobs.get(analysis_id)
        job = public_memory_job(memory_job) if memory_job else None
    if not job:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Analysis not found."},
        )
    return job


@app.get("/api/v1/analyses/{analysis_id}/result")
async def get_result(analysis_id: str, request: Request) -> dict[str, Any]:
    analysis_id = normalized_analysis_id(analysis_id)
    persistence = request.app.state.persistence
    if persistence is not None:
        try:
            stored = await asyncio.to_thread(persistence.get_result, analysis_id)
        except Exception as exc:
            LOGGER.exception("Persistent analysis result read failed for %s", analysis_id)
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "PERSISTENCE_UNAVAILABLE",
                    "message": "The stored analysis result could not be read.",
                },
            ) from exc
        if stored is None:
            job_status = None
            result = None
        else:
            job_status, result = stored
    else:
        job = request.app.state.jobs.get(analysis_id)
        job_status = job["status"] if job else None
        result = job.get("result") if job else None
    if job_status is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Analysis not found."},
        )
    if job_status != "succeeded" or result is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "RESULT_NOT_READY", "message": "Analysis result is not ready."},
        )
    return result


@app.delete("/api/v1/analyses/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(analysis_id: str, request: Request) -> Response:
    analysis_id = normalized_analysis_id(analysis_id)
    persistence = request.app.state.persistence
    if persistence is not None:
        try:
            found = await asyncio.to_thread(persistence.purge_analysis, analysis_id)
        except Exception as exc:
            LOGGER.exception("Analysis purge failed for %s", analysis_id)
            raise HTTPException(
                status_code=503,
                detail={"code": "PURGE_FAILED", "message": "Analysis could not be purged."},
            ) from exc
        if not found:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND", "message": "Analysis not found."},
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    job = request.app.state.jobs.get(analysis_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": "Analysis not found."},
        )
    job["status"] = "cancelled"
    Path(job["path"]).unlink(missing_ok=True)
    request.app.state.jobs.pop(analysis_id, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "index.html")


app.mount("/frontend", StaticFiles(directory=PROJECT_ROOT / "frontend", html=True), name="frontend")
app.mount("/asset", StaticFiles(directory=PROJECT_ROOT / "asset"), name="asset")
