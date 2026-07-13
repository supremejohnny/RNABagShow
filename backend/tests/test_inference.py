from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from backend.app.inference import inspect_tsv, run_mock_inference


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = PROJECT_ROOT / "sampledata"


class InputInspectionTests(unittest.TestCase):
    def test_platelet_sample_contract(self) -> None:
        path = SAMPLE_DIR / "Platelet_sample_to_joh.tsv"
        summary = inspect_tsv(path, filename=path.name)

        self.assertEqual(summary.gene_rows, 6010)
        self.assertEqual(summary.unique_gene_ids, 4471)
        self.assertEqual(summary.duplicate_gene_rows, 1539)
        self.assertEqual(summary.sample_count, 3)

    def test_tissue_sample_contract(self) -> None:
        path = SAMPLE_DIR / "tissue_sample_fpkm_to_joh.tsv"
        summary = inspect_tsv(path, filename=path.name)

        self.assertEqual(summary.gene_rows, 31859)
        self.assertEqual(summary.unique_gene_ids, 21164)
        self.assertEqual(summary.duplicate_gene_rows, 10695)
        self.assertEqual(summary.sample_count, 12)

    def test_mock_result_is_deterministic(self) -> None:
        path = SAMPLE_DIR / "Platelet_sample_to_joh.tsv"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        arguments = {
            "filename": path.name,
            "file_digest": digest,
            "task": "platelet_cancer_detection",
        }

        first = run_mock_inference(path, **arguments)
        second = run_mock_inference(path, **arguments)

        self.assertEqual(first, second)
        self.assertEqual(len(first["predictions"]), 3)
        self.assertEqual(first["mode"], "mock")


if __name__ == "__main__":
    unittest.main()
