from __future__ import annotations

import hashlib
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.persistence import (
    PersistenceBackend,
    PersistenceOperationError,
    S3ObjectStore,
    public_analysis,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def upload_file(
        self,
        filename: str,
        bucket: str,
        key: str,
        ExtraArgs: dict[str, object],
    ) -> None:
        self.objects[(bucket, key)] = Path(filename).read_bytes()
        self.extra_args = ExtraArgs

    def copy_object(
        self,
        *,
        Bucket: str,
        CopySource: dict[str, str],
        Key: str,
        MetadataDirective: str,
    ) -> None:
        self.objects[(Bucket, Key)] = self.objects[(CopySource["Bucket"], CopySource["Key"])]
        self.metadata_directive = MetadataDirective

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)


class _PurgeCursor:
    def __init__(self, row: dict[str, object], reference_count: int) -> None:
        self.row = row
        self.reference_count = reference_count
        self.result: dict[str, object] | None = None

    def __enter__(self) -> "_PurgeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, _parameters: object = None) -> None:
        normalized = " ".join(statement.split())
        if normalized.startswith("SELECT * FROM analyses"):
            self.result = self.row
        elif normalized.startswith("UPDATE analyses"):
            self.row["purged_at"] = datetime.now(timezone.utc)
            self.result = None
        elif "SELECT COUNT(*) AS reference_count" in normalized:
            self.result = {"reference_count": self.reference_count}
        else:
            self.result = None

    def fetchone(self) -> dict[str, object] | None:
        return self.result


class _PurgeConnection:
    def __init__(
        self,
        row: dict[str, object],
        reference_count: int,
        events: list[str],
    ) -> None:
        self.cursor_instance = _PurgeCursor(row, reference_count)
        self.events = events

    def cursor(self) -> _PurgeCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")

    def close(self) -> None:
        self.events.append("close")


class _RecordingObjectStore:
    def __init__(self, events: list[str], *, fail_deletion: bool = False) -> None:
        self.events = events
        self.fail_deletion = fail_deletion

    def delete_original(self, _storage_key: str) -> None:
        self.events.append("delete")
        if self.fail_deletion:
            raise PersistenceOperationError("delete failed")


class PersistenceContractTests(unittest.TestCase):
    def _purge_backend(
        self,
        row: dict[str, object],
        events: list[str],
        *,
        fail_deletion: bool = False,
    ) -> PersistenceBackend:
        backend = object.__new__(PersistenceBackend)
        connection = _PurgeConnection(row, 0, events)
        backend._connect = lambda: connection
        backend.objects = _RecordingObjectStore(events, fail_deletion=fail_deletion)
        return backend

    def test_public_analysis_excludes_storage_coordinates(self) -> None:
        now = datetime.now(timezone.utc)
        analysis_id = uuid.uuid4()
        public = public_analysis(
            {
                "id": analysis_id,
                "status": "queued",
                "task": "platelet_cancer_detection",
                "modality": "platelet",
                "original_filename": "sample.tsv",
                "file_size_bytes": 12,
                "file_sha256": "a" * 64,
                "created_at": now,
                "updated_at": now,
                "started_at": None,
                "completed_at": None,
                "storage_provider": "s3",
                "storage_bucket": "private",
                "storage_key": "uploads/private/input.tsv",
            }
        )

        self.assertEqual(public["analysis_id"], str(analysis_id))
        self.assertNotIn("storage_bucket", public)
        self.assertNotIn("storage_key", public)

    def test_upload_uses_uuid_key_and_removes_staging_object(self) -> None:
        client = _FakeS3Client()
        store = object.__new__(S3ObjectStore)
        store.bucket = "rnabag-private-inputs"
        store._client = client
        content = b"GeneID\tSample\n1\t1\n"
        digest = hashlib.sha256(content).hexdigest()
        analysis_id = uuid.uuid4()

        with TemporaryDirectory() as directory:
            path = Path(directory) / "sample.tsv"
            path.write_bytes(content)
            key = store.upload_original(
                path,
                analysis_id=analysis_id,
                file_sha256=digest,
                content_type="text/tab-separated-values",
            )

        self.assertEqual(key, f"uploads/{analysis_id}/input.tsv")
        self.assertEqual(client.objects[(store.bucket, key)], content)
        self.assertNotIn((store.bucket, f"uploads/_staging/{analysis_id}"), client.objects)
        self.assertEqual(client.extra_args["Metadata"], {"sha256": digest})

    def test_migration_preserves_many_analyses_per_content_object(self) -> None:
        migration = (
            PROJECT_ROOT / "backend" / "migrations" / "001_create_analyses.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE analyses", migration)
        self.assertIn("file_sha256 CHAR(64)", migration)
        self.assertIn("result JSONB", migration)
        self.assertNotIn("UNIQUE (file_sha256)", migration)
        self.assertNotIn("UNIQUE (storage_provider", migration)

    def test_last_reference_commits_purge_before_deleting_object(self) -> None:
        analysis_id = uuid.uuid4()
        row: dict[str, object] = {
            "id": analysis_id,
            "file_sha256": "a" * 64,
            "storage_provider": "s3",
            "storage_bucket": "private",
            "storage_key": f"uploads/{analysis_id}/input.tsv",
            "purged_at": None,
        }
        events: list[str] = []
        backend = self._purge_backend(row, events)

        self.assertTrue(backend.purge_analysis(str(analysis_id)))
        self.assertLess(events.index("commit"), events.index("delete"))
        self.assertNotIn("rollback", events)

    def test_purge_retries_object_deletion_after_committed_failure(self) -> None:
        analysis_id = uuid.uuid4()
        row: dict[str, object] = {
            "id": analysis_id,
            "file_sha256": "b" * 64,
            "storage_provider": "s3",
            "storage_bucket": "private",
            "storage_key": f"uploads/{analysis_id}/input.tsv",
            "purged_at": None,
        }
        first_events: list[str] = []
        first_backend = self._purge_backend(row, first_events, fail_deletion=True)

        with self.assertRaises(PersistenceOperationError):
            first_backend.purge_analysis(str(analysis_id))

        self.assertIsNotNone(row["purged_at"])
        self.assertLess(first_events.index("commit"), first_events.index("delete"))
        self.assertNotIn("rollback", first_events)

        retry_events: list[str] = []
        retry_backend = self._purge_backend(row, retry_events)
        self.assertTrue(retry_backend.purge_analysis(str(analysis_id)))
        self.assertLess(retry_events.index("commit"), retry_events.index("delete"))

    def test_minio_policy_is_rendered_for_the_configured_bucket(self) -> None:
        compose = (PROJECT_ROOT / "deploy" / "compose.persistence.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("cat > /tmp/rnabag-app.json <<EOF", compose)
        self.assertIn('"arn:aws:s3:::$$RNABAG_S3_BUCKET"', compose)
        self.assertIn('"arn:aws:s3:::$$RNABAG_S3_BUCKET/*"', compose)
        self.assertNotIn("sed ", compose)
        self.assertNotIn("arn:aws:s3:::rnabag-private-inputs", compose)
        self.assertNotIn(
            "mc admin policy create rnabag rnabag-app /tmp/rnabag-app.json || true",
            compose,
        )


if __name__ == "__main__":
    unittest.main()
