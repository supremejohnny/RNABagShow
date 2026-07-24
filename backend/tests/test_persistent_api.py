from __future__ import annotations

import asyncio
import os
import time
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import main
from backend.app.persistence import public_analysis


class _FakePersistenceBackend:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, object]] = {}
        self.payloads: dict[str, bytes] = {}

    def startup(self) -> list[str]:
        return []

    def healthcheck(self) -> None:
        return None

    def create_analysis(self, path: Path, **values: object) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        analysis_id = str(values["analysis_id"])
        row: dict[str, object] = {
            "id": uuid.UUID(analysis_id),
            "status": "queued",
            "task": values["task"],
            "modality": values["modality"],
            "original_filename": values["original_filename"],
            "file_size_bytes": values["file_size_bytes"],
            "file_sha256": values["file_sha256"],
            "content_type": values["content_type"],
            "storage_provider": "s3",
            "storage_bucket": "test-bucket",
            "storage_key": f"uploads/{analysis_id}/input.tsv",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "completed_at": None,
            "purged_at": None,
            "result": None,
        }
        self.rows[analysis_id] = row
        self.payloads[analysis_id] = path.read_bytes()
        return public_analysis(row)

    def claim_analysis(self, analysis_id: str) -> dict[str, object] | None:
        row = self.rows.get(analysis_id)
        if row is None or row["status"] != "queued":
            return None
        row["status"] = "validating"
        row["started_at"] = datetime.now(timezone.utc)
        return row

    def download_for_inference(self, row: dict[str, object], destination: Path) -> None:
        destination.write_bytes(self.payloads[str(row["id"])])

    def mark_running(self, analysis_id: str) -> bool:
        self.rows[analysis_id]["status"] = "running"
        return True

    def mark_succeeded(self, analysis_id: str, result: dict[str, object]) -> bool:
        row = self.rows[analysis_id]
        row["status"] = "succeeded"
        row["result"] = result
        row["completed_at"] = datetime.now(timezone.utc)
        row["updated_at"] = row["completed_at"]
        return True

    def mark_failed(self, analysis_id: str, error: dict[str, object]) -> bool:
        self.rows[analysis_id]["status"] = "failed"
        self.rows[analysis_id]["error"] = error
        return True

    def get_analysis(self, analysis_id: str) -> dict[str, object] | None:
        row = self.rows.get(analysis_id)
        return public_analysis(row) if row else None

    def get_result(self, analysis_id: str) -> tuple[str, dict[str, object] | None] | None:
        row = self.rows.get(analysis_id)
        if row is None:
            return None
        return str(row["status"]), row["result"]

    def purge_analysis(self, analysis_id: str) -> bool:
        row = self.rows.get(analysis_id)
        if row is None:
            return False
        row["status"] = "purged"
        row["result"] = None
        self.payloads.pop(analysis_id, None)
        return True


def _fake_result(_path: Path, *, filename: str, task: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "mode": "checkpoint",
        "task": task,
        "modality": "platelet",
        "model_version": "test-model",
        "input_summary": {"filename": filename},
        "predictions": [],
        "warnings": [],
    }


class PersistentApiTests(unittest.TestCase):
    def test_queue_reservations_close_the_concurrent_upload_window(self) -> None:
        queue_app = SimpleNamespace(
            state=SimpleNamespace(queue=asyncio.Queue(), queue_reservations=0)
        )
        with patch.object(main, "QUEUE_CAPACITY", 1):
            self.assertTrue(main.try_reserve_queue_slot(queue_app))
            self.assertFalse(main.try_reserve_queue_slot(queue_app))
            main.release_queue_slot(queue_app)

            queue_app.state.queue.put_nowait("already-waiting")
            self.assertFalse(main.try_reserve_queue_slot(queue_app))

    def test_filename_must_fit_the_persistence_schema(self) -> None:
        with (
            patch.dict(os.environ, {"RNABAG_PERSISTENCE_ENABLED": "false"}),
            TestClient(main.app) as client,
        ):
            response = client.post(
                "/api/v1/analyses?task=platelet_cancer_detection",
                content=b"GeneID\tSample\n1\t1\n",
                headers={
                    "Content-Type": "text/tab-separated-values",
                    "X-RNABag-Filename": f"{'a' * 509}.tsv",
                },
            )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()["detail"]["code"], "INVALID_FILENAME")

    def test_demo_data_downloads_are_limited_to_verified_modalities(self) -> None:
        with (
            patch.dict(os.environ, {"RNABAG_PERSISTENCE_ENABLED": "false"}),
            TestClient(main.app) as client,
        ):
            expected = {
                "tissue": ("tissue_sample_fpkm_to_joh.tsv", 12),
                "platelet": ("Platelet_sample_to_joh.tsv", 3),
            }
            for modality, (filename, sample_count) in expected.items():
                response = client.get(f"/api/v1/demo-data/{modality}")
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(
                    response.headers["content-type"],
                    "text/tab-separated-values; charset=utf-8",
                )
                self.assertIn(filename, response.headers["content-disposition"])
                lines = response.content.splitlines()
                header = lines[1].decode("utf-8").split("\t")
                self.assertEqual(len(header) - 1, sample_count)

            self.assertEqual(client.get("/api/v1/demo-data/plasma").status_code, 404)

    def test_plasma_cancer_detection_is_enabled_in_catalog_and_accepts_upload(self) -> None:
        with (
            patch.dict(os.environ, {"RNABAG_PERSISTENCE_ENABLED": "false"}),
            TestClient(main.app) as client,
        ):
            tasks_response = client.get("/api/v1/tasks")
            self.assertEqual(tasks_response.status_code, 200)
            tasks = {item["task"]: item for item in tasks_response.json()["tasks"]}
            self.assertIn("plasma_cancer_detection", tasks)
            self.assertTrue(tasks["plasma_cancer_detection"]["enabled"])
            self.assertEqual(tasks["plasma_cancer_detection"]["modality"], "plasma")
            self.assertEqual(tasks["plasma_cancer_detection"]["output_type"], "binary")

            response = client.post(
                "/api/v1/analyses?task=plasma_cancer_detection",
                content=b"GeneID\tSample\n1\t1\n",
                headers={
                    "Content-Type": "text/tab-separated-values",
                    "X-RNABag-Filename": "test.tsv",
                },
            )
            self.assertEqual(response.status_code, 202, response.text)

    def test_tissue_and_platelet_demo_data_still_returns_200(self) -> None:
        with (
            patch.dict(os.environ, {"RNABAG_PERSISTENCE_ENABLED": "false"}),
            TestClient(main.app) as client,
        ):
            self.assertEqual(client.get("/api/v1/demo-data/tissue").status_code, 200)
            self.assertEqual(client.get("/api/v1/demo-data/platelet").status_code, 200)

    def test_persistent_upload_worker_result_and_purge(self) -> None:
        fake_backend = _FakePersistenceBackend()
        environment = {
            "RNABAG_PERSISTENCE_ENABLED": "true",
            "RNABAG_DATABASE_URL": "postgresql://unused",
            "RNABAG_S3_ENDPOINT_URL": "http://unused",
            "RNABAG_S3_ACCESS_KEY": "unused",
            "RNABAG_S3_SECRET_KEY": "unused",
            "RNABAG_S3_BUCKET": "unused",
        }

        with TemporaryDirectory() as directory:
            environment["RNABAG_TEMP_DIR"] = directory
            with (
                patch.dict(os.environ, environment),
                patch.object(main, "PersistenceBackend", return_value=fake_backend),
                patch.object(main, "run_checkpoint_inference", side_effect=_fake_result),
                TestClient(main.app) as client,
            ):
                response = client.post(
                    "/api/v1/analyses?task=platelet_cancer_detection",
                    content=b"GeneID\tSample\n1\t1\n",
                    headers={
                        "Content-Type": "text/tab-separated-values",
                        "X-RNABag-Filename": "sample.tsv",
                    },
                )
                self.assertEqual(response.status_code, 202, response.text)
                analysis_id = response.json()["analysis_id"]

                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    job = client.get(f"/api/v1/analyses/{analysis_id}").json()
                    if job["status"] in {"succeeded", "failed"}:
                        break
                    time.sleep(0.01)

                self.assertEqual(job["status"], "succeeded")
                result = client.get(f"/api/v1/analyses/{analysis_id}/result")
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()["schema_version"], 1)
                self.assertEqual(
                    client.get("/api/v1/health/ready").json()["persistence"],
                    "postgres-s3",
                )
                self.assertEqual(
                    client.delete(f"/api/v1/analyses/{analysis_id}").status_code,
                    204,
                )
                self.assertNotIn(analysis_id, fake_backend.payloads)


if __name__ == "__main__":
    unittest.main()
