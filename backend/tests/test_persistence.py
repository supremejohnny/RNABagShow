from __future__ import annotations

import hashlib
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.persistence import S3ObjectStore, public_analysis


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


class PersistenceContractTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
