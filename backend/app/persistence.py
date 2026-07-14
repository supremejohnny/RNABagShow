from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = PROJECT_ROOT / "backend" / "migrations"


class PersistenceConfigurationError(RuntimeError):
    pass


class PersistenceOperationError(RuntimeError):
    pass


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise PersistenceConfigurationError(
            f"{name} is required when RNABAG_PERSISTENCE_ENABLED=true."
        )
    return value


@dataclass(frozen=True)
class PersistenceSettings:
    database_url: str
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    s3_region: str = "us-east-1"

    @classmethod
    def from_environment(cls) -> "PersistenceSettings":
        return cls(
            database_url=_required_environment("RNABAG_DATABASE_URL"),
            s3_endpoint_url=_required_environment("RNABAG_S3_ENDPOINT_URL"),
            s3_access_key=_required_environment("RNABAG_S3_ACCESS_KEY"),
            s3_secret_key=_required_environment("RNABAG_S3_SECRET_KEY"),
            s3_bucket=_required_environment("RNABAG_S3_BUCKET"),
            s3_region=os.getenv("RNABAG_S3_REGION", "us-east-1").strip() or "us-east-1",
        )


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def public_analysis(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "analysis_id": str(row["id"]),
        "status": row["status"],
        "task": row["task"],
        "modality": row["modality"],
        "filename": row["original_filename"],
        "size_bytes": row["file_size_bytes"],
        "file_digest": row["file_sha256"],
        "created_at": _isoformat(row["created_at"]),
        "updated_at": _isoformat(row["updated_at"]),
        "started_at": _isoformat(row.get("started_at")),
        "completed_at": _isoformat(row.get("completed_at")),
        "mode": "checkpoint",
    }


class S3ObjectStore:
    def __init__(self, settings: PersistenceSettings) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise PersistenceConfigurationError(
                "boto3 is required when RNABAG persistence is enabled."
            ) from exc

        self.bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return
        except Exception as exc:
            response = getattr(exc, "response", {})
            code = str(response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise PersistenceOperationError(
                    "Private object-storage bucket health check failed."
                ) from exc

        try:
            self._client.create_bucket(Bucket=self.bucket)
        except Exception as exc:
            raise PersistenceOperationError(
                "Private object-storage bucket could not be created."
            ) from exc

    def healthcheck(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except Exception as exc:
            raise PersistenceOperationError(
                "Private object-storage bucket is unavailable."
            ) from exc

    def upload_original(
        self,
        path: Path,
        *,
        analysis_id: uuid.UUID,
        file_sha256: str,
        content_type: str,
    ) -> str:
        staging_key = f"uploads/_staging/{analysis_id}"
        final_key = f"uploads/{analysis_id}/input.tsv"
        uploaded_staging = False
        try:
            self._client.upload_file(
                str(path),
                self.bucket,
                staging_key,
                ExtraArgs={
                    "ContentType": content_type,
                    "Metadata": {"sha256": file_sha256},
                },
            )
            uploaded_staging = True
            self._client.copy_object(
                Bucket=self.bucket,
                CopySource={"Bucket": self.bucket, "Key": staging_key},
                Key=final_key,
                MetadataDirective="COPY",
            )
        except Exception as exc:
            with _ignore_object_error():
                self._client.delete_object(Bucket=self.bucket, Key=final_key)
            raise PersistenceOperationError("Original upload could not be stored.") from exc
        finally:
            if uploaded_staging:
                with _ignore_object_error():
                    self._client.delete_object(Bucket=self.bucket, Key=staging_key)
        return final_key

    def download_original(self, storage_key: str, destination: Path) -> None:
        try:
            self._client.download_file(self.bucket, storage_key, str(destination))
        except Exception as exc:
            destination.unlink(missing_ok=True)
            raise PersistenceOperationError("Stored original upload could not be read.") from exc

    def delete_original(self, storage_key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=storage_key)
        except Exception as exc:
            raise PersistenceOperationError("Stored original upload could not be deleted.") from exc


class _ignore_object_error:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: object) -> bool:
        return True


class PersistenceBackend:
    def __init__(self, settings: PersistenceSettings) -> None:
        try:
            import psycopg  # noqa: F401
        except ImportError as exc:
            raise PersistenceConfigurationError(
                "psycopg is required when RNABAG persistence is enabled."
            ) from exc
        self.settings = settings
        self.objects = S3ObjectStore(settings)

    def _connect(self) -> Any:
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.settings.database_url, row_factory=dict_row)

    def startup(self) -> list[str]:
        self.initialize()
        return self.recover_pending_analyses()

    def initialize(self) -> None:
        self._apply_migrations()
        self.objects.ensure_bucket()

    def recover_pending_analyses(self) -> list[str]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE analyses
                    SET status = 'queued',
                        started_at = NULL,
                        updated_at = NOW()
                    WHERE status IN ('validating', 'running')
                    """
                )
                cursor.execute(
                    """
                    SELECT id
                    FROM analyses
                    WHERE status = 'queued'
                    ORDER BY created_at ASC
                    """
                )
                return [str(row["id"]) for row in cursor.fetchall()]

    def _apply_migrations(self) -> None:
        migration_paths = sorted(MIGRATIONS_DIR.glob("*.sql"))
        if not migration_paths:
            raise PersistenceConfigurationError("No PostgreSQL migrations were found.")

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version TEXT PRIMARY KEY,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                for path in migration_paths:
                    cursor.execute(
                        "SELECT 1 FROM schema_migrations WHERE version = %s",
                        (path.name,),
                    )
                    if cursor.fetchone():
                        continue
                    cursor.execute(path.read_text(encoding="utf-8"))
                    cursor.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)",
                        (path.name,),
                    )

    def healthcheck(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        self.objects.healthcheck()

    def create_analysis(
        self,
        path: Path,
        *,
        analysis_id: str,
        task: str,
        modality: str,
        original_filename: str,
        file_size_bytes: int,
        file_sha256: str,
        content_type: str,
    ) -> dict[str, Any]:
        analysis_uuid = uuid.UUID(analysis_id)
        created_storage_key: str | None = None
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (file_sha256,),
                )
                cursor.execute(
                    """
                    SELECT storage_provider, storage_bucket, storage_key
                    FROM analyses
                    WHERE file_sha256 = %s
                      AND purged_at IS NULL
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    (file_sha256,),
                )
                existing = cursor.fetchone()
                if existing:
                    storage_provider = existing["storage_provider"]
                    storage_bucket = existing["storage_bucket"]
                    storage_key = existing["storage_key"]
                else:
                    storage_provider = "s3"
                    storage_bucket = self.settings.s3_bucket
                    storage_key = self.objects.upload_original(
                        path,
                        analysis_id=analysis_uuid,
                        file_sha256=file_sha256,
                        content_type=content_type,
                    )
                    created_storage_key = storage_key

                cursor.execute(
                    """
                    INSERT INTO analyses (
                        id,
                        task,
                        modality,
                        status,
                        original_filename,
                        file_size_bytes,
                        file_sha256,
                        content_type,
                        storage_provider,
                        storage_bucket,
                        storage_key
                    )
                    VALUES (
                        %s, %s, %s, 'queued', %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING *
                    """,
                    (
                        analysis_uuid,
                        task,
                        modality,
                        original_filename,
                        file_size_bytes,
                        file_sha256,
                        content_type,
                        storage_provider,
                        storage_bucket,
                        storage_key,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            if created_storage_key is not None:
                with _ignore_object_error():
                    self.objects.delete_original(created_storage_key)
            raise
        finally:
            connection.close()

        if row is None:
            raise PersistenceOperationError("Analysis row was not created.")
        return public_analysis(row)

    def claim_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE analyses
                    SET status = 'validating',
                        started_at = COALESCE(started_at, NOW()),
                        updated_at = NOW()
                    WHERE id = %s
                      AND status = 'queued'
                    RETURNING *
                    """,
                    (uuid.UUID(analysis_id),),
                )
                return cursor.fetchone()

    def mark_running(self, analysis_id: str) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE analyses
                    SET status = 'running', updated_at = NOW()
                    WHERE id = %s AND status = 'validating'
                    """,
                    (uuid.UUID(analysis_id),),
                )
                return cursor.rowcount == 1

    def mark_succeeded(self, analysis_id: str, result: dict[str, Any]) -> bool:
        from psycopg.types.json import Jsonb

        input_summary = result.get("input_summary")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE analyses
                    SET status = 'succeeded',
                        input_summary = %s,
                        result = %s,
                        error = NULL,
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                      AND status IN ('validating', 'running')
                    """,
                    (Jsonb(input_summary), Jsonb(result), uuid.UUID(analysis_id)),
                )
                return cursor.rowcount == 1

    def mark_failed(self, analysis_id: str, error: dict[str, Any]) -> bool:
        from psycopg.types.json import Jsonb

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE analyses
                    SET status = 'failed',
                        error = %s,
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                      AND status IN ('queued', 'validating', 'running')
                    """,
                    (Jsonb(error), uuid.UUID(analysis_id)),
                )
                return cursor.rowcount == 1

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM analyses WHERE id = %s", (uuid.UUID(analysis_id),))
                row = cursor.fetchone()
        return public_analysis(row) if row else None

    def get_result(self, analysis_id: str) -> tuple[str, dict[str, Any] | None] | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT status, result FROM analyses WHERE id = %s",
                    (uuid.UUID(analysis_id),),
                )
                row = cursor.fetchone()
        return (row["status"], row["result"]) if row else None

    def download_for_inference(self, row: dict[str, Any], destination: Path) -> None:
        if row["storage_provider"] != "s3" or row["storage_bucket"] != self.settings.s3_bucket:
            raise PersistenceOperationError("Analysis refers to unsupported object storage.")
        self.objects.download_original(row["storage_key"], destination)

    def purge_analysis(self, analysis_id: str) -> bool:
        analysis_uuid = uuid.UUID(analysis_id)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM analyses WHERE id = %s FOR UPDATE",
                    (analysis_uuid,),
                )
                row = cursor.fetchone()
                if row is None:
                    connection.rollback()
                    return False
                if row["purged_at"] is not None:
                    connection.commit()
                    return True

                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (row["file_sha256"],),
                )
                cursor.execute(
                    """
                    UPDATE analyses
                    SET status = 'purged',
                        original_filename = 'purged.tsv',
                        file_size_bytes = 0,
                        input_summary = NULL,
                        result = NULL,
                        error = NULL,
                        purged_at = NOW(),
                        completed_at = COALESCE(completed_at, NOW()),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (analysis_uuid,),
                )
                cursor.execute(
                    """
                    SELECT COUNT(*) AS reference_count
                    FROM analyses
                    WHERE storage_provider = %s
                      AND storage_bucket = %s
                      AND storage_key = %s
                      AND purged_at IS NULL
                    """,
                    (row["storage_provider"], row["storage_bucket"], row["storage_key"]),
                )
                reference_count = cursor.fetchone()["reference_count"]
                if reference_count == 0:
                    self.objects.delete_original(row["storage_key"])
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
