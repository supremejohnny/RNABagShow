from __future__ import annotations

import hashlib
import os
import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.app.persistence import PersistenceBackend, PersistenceSettings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = PROJECT_ROOT / "sampledata"
RUN_INTEGRATION = os.getenv("RNABAG_RUN_PERSISTENCE_INTEGRATION") == "1"


@unittest.skipUnless(
    RUN_INTEGRATION,
    "Set RNABAG_RUN_PERSISTENCE_INTEGRATION=1 with test persistence credentials.",
)
class PersistenceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.backend = PersistenceBackend(PersistenceSettings.from_environment())
        cls.backend.initialize()
        cls.analysis_ids: list[str] = []

    @classmethod
    def tearDownClass(cls) -> None:
        for analysis_id in cls.analysis_ids:
            cls.backend.purge_analysis(analysis_id)

    def _store_sample(self, filename: str, task: str, modality: str) -> tuple[str, bytes]:
        path = SAMPLE_DIR / filename
        content = path.read_bytes()
        analysis_id = str(uuid.uuid4())
        self.backend.create_analysis(
            path,
            analysis_id=analysis_id,
            task=task,
            modality=modality,
            original_filename=filename,
            file_size_bytes=len(content),
            file_sha256=hashlib.sha256(content).hexdigest(),
            content_type="text/tab-separated-values",
        )
        self.analysis_ids.append(analysis_id)
        return analysis_id, content

    def test_platelet_and_tissue_original_bytes_round_trip(self) -> None:
        cases = [
            (
                "Platelet_sample_to_joh.tsv",
                "platelet_cancer_detection",
                "platelet",
            ),
            (
                "tissue_sample_fpkm_to_joh.tsv",
                "tissue_cancer_detection",
                "tissue",
            ),
        ]

        with TemporaryDirectory() as directory:
            for filename, task, modality in cases:
                with self.subTest(filename=filename):
                    analysis_id, expected = self._store_sample(filename, task, modality)
                    row = self.backend.claim_analysis(analysis_id)
                    self.assertIsNotNone(row)
                    destination = Path(directory) / f"{analysis_id}.tsv"
                    self.backend.download_for_inference(row, destination)
                    self.assertEqual(destination.read_bytes(), expected)

    def test_duplicate_bytes_reuse_one_object_until_last_purge(self) -> None:
        filename = "Platelet_sample_to_joh.tsv"
        first_id, expected = self._store_sample(
            filename,
            "platelet_cancer_detection",
            "platelet",
        )
        second_id, _ = self._store_sample(
            filename,
            "platelet_tumor_localization",
            "platelet",
        )

        with self.backend._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, storage_key FROM analyses WHERE id IN (%s, %s)",
                    (uuid.UUID(first_id), uuid.UUID(second_id)),
                )
                rows = cursor.fetchall()
        self.assertEqual(len({row["storage_key"] for row in rows}), 1)

        self.backend.purge_analysis(first_id)
        second_row = self.backend.claim_analysis(second_id)
        self.assertIsNotNone(second_row)
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "still-referenced.tsv"
            self.backend.download_for_inference(second_row, destination)
            self.assertEqual(destination.read_bytes(), expected)


if __name__ == "__main__":
    unittest.main()
