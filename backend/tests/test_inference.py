from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from backend.app.inference import (
    InputValidationError,
    inspect_tsv,
    load_gene_resources,
    preprocess_tsv,
    run_checkpoint_inference,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = PROJECT_ROOT / "sampledata"


class InputInspectionTests(unittest.TestCase):
    def test_gene_resources_match_documented_contract(self) -> None:
        resources = load_gene_resources()

        self.assertEqual(len(resources.hvg_genes), 4096)
        self.assertEqual(len(resources.known_gene_ids), 39376)
        self.assertEqual(len(set(resources.target_by_gene_id.values())), 4051)
        self.assertEqual(resources.safe_synonym_targets, 145)

    def test_standard_header_and_first_duplicate_wins(self) -> None:
        resources = load_gene_resources()
        gene_id, target = next(iter(resources.target_by_gene_id.items()))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.tsv"
            path.write_text(
                f"GeneID\tSample_1\n{gene_id}\t1\n{gene_id}\t99\n",
                encoding="utf-8",
            )
            matrix, summary = preprocess_tsv(path, filename=path.name)

        self.assertEqual(summary.title_rows_skipped, 0)
        self.assertEqual(summary.duplicate_gene_rows, 1)
        self.assertAlmostEqual(
            matrix[0, resources.hvg_index[target]],
            np.log1p(1.0),
        )

    def test_scientific_notation_gene_id_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "rounded.tsv"
            path.write_text("GeneID\tSample_1\n1.00287102E8\t1\n", encoding="utf-8")
            with self.assertRaises(InputValidationError) as context:
                inspect_tsv(path, filename=path.name)

        self.assertEqual(context.exception.code, "INVALID_GENE_ID")

    def test_platelet_sample_contract(self) -> None:
        path = SAMPLE_DIR / "Platelet_sample_to_joh.tsv"
        summary = inspect_tsv(path, filename=path.name)

        self.assertEqual(summary.gene_rows, 6010)
        self.assertEqual(summary.unique_gene_ids, 6010)
        self.assertEqual(summary.duplicate_gene_rows, 0)
        self.assertEqual(summary.mapped_unique_gene_ids, 6010)
        self.assertEqual(summary.model_hvg_found, 664)
        self.assertEqual(summary.sample_count, 3)
        self.assertEqual(summary.title_rows_skipped, 1)
        self.assertEqual(summary.duplicate_gene_strategy, "first")

    def test_tissue_sample_contract(self) -> None:
        path = SAMPLE_DIR / "tissue_sample_fpkm_to_joh.tsv"
        matrix, summary = preprocess_tsv(path, filename=path.name)

        self.assertEqual(summary.gene_rows, 39376)
        self.assertEqual(summary.unique_gene_ids, 39376)
        self.assertEqual(summary.duplicate_gene_rows, 0)
        self.assertEqual(summary.mapped_unique_gene_ids, 39376)
        self.assertEqual(summary.model_hvg_found, 4051)
        self.assertEqual(summary.model_hvg_missing, 45)
        self.assertEqual(summary.sample_count, 12)
        self.assertEqual(matrix.shape, (12, 4096))

    def test_real_checkpoint_result_contract(self) -> None:
        path = SAMPLE_DIR / "Platelet_sample_to_joh.tsv"
        result = run_checkpoint_inference(
            path,
            filename=path.name,
            task="platelet_cancer_detection",
        )

        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["mode"], "checkpoint")
        self.assertIn("Platelet_cancer_detect", result["model_version"])
        self.assertEqual(len(result["predictions"]), 3)
        for prediction in result["predictions"]:
            self.assertIn(prediction["predicted_label"], {"Healthy", "Cancer"})
            self.assertAlmostEqual(
                sum(score["score"] for score in prediction["scores"]),
                1.0,
                places=6,
            )


if __name__ == "__main__":
    unittest.main()
