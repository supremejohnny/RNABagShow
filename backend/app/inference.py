from __future__ import annotations

import csv
import hashlib
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .catalog import TASKS


class InputValidationError(ValueError):
    def __init__(self, code: str, message: str, *, line: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.line = line


@dataclass(frozen=True)
class InputSummary:
    filename: str
    size_bytes: int
    gene_rows: int
    unique_gene_ids: int
    duplicate_gene_rows: int
    sample_count: int
    sample_ids: list[str]
    minimum_expression: float
    maximum_expression: float
    zero_values: int
    duplicate_gene_strategy: str


def inspect_tsv(
    path: Path,
    *,
    filename: str,
    duplicate_gene_strategy: str = "provisional_sum",
) -> InputSummary:
    gene_ids: set[str] = set()
    duplicate_gene_rows = 0
    gene_rows = 0
    zero_values = 0
    minimum_expression = math.inf
    maximum_expression = -math.inf

    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except UnicodeDecodeError as exc:
        raise InputValidationError("INVALID_ENCODING", "TSV must be UTF-8 encoded.") from exc

    try:
        with handle:
            reader = csv.reader(handle, delimiter="\t")
            try:
                header = next(reader)
            except StopIteration as exc:
                raise InputValidationError("EMPTY_FILE", "The uploaded TSV is empty.") from exc

            if len(header) < 2:
                raise InputValidationError(
                    "INVALID_HEADER", "TSV must contain GeneID and at least one sample column."
                )

            gene_header = header[0].strip().lower()
            if gene_header not in {"geneid", "gene_id", "gene"}:
                raise InputValidationError(
                    "INVALID_GENE_HEADER", "The first column must be named GeneID."
                )

            sample_ids = [value.strip() for value in header[1:]]
            if any(not sample_id for sample_id in sample_ids):
                raise InputValidationError("EMPTY_SAMPLE_ID", "Sample column names must not be empty.")
            if len(sample_ids) != len(set(sample_ids)):
                raise InputValidationError("DUPLICATE_SAMPLE_ID", "Sample column names must be unique.")

            for line_number, row in enumerate(reader, start=2):
                if not row or all(not cell.strip() for cell in row):
                    continue
                if len(row) != len(header):
                    raise InputValidationError(
                        "INCONSISTENT_COLUMNS",
                        f"Expected {len(header)} columns but found {len(row)}.",
                        line=line_number,
                    )

                gene_id = row[0].strip()
                if not gene_id:
                    raise InputValidationError(
                        "EMPTY_GENE_ID", "GeneID must not be empty.", line=line_number
                    )
                if gene_id in gene_ids:
                    duplicate_gene_rows += 1
                else:
                    gene_ids.add(gene_id)

                for value in row[1:]:
                    try:
                        expression = float(value)
                    except ValueError as exc:
                        raise InputValidationError(
                            "NON_NUMERIC_EXPRESSION",
                            "Expression values must be numeric.",
                            line=line_number,
                        ) from exc
                    if not math.isfinite(expression) or expression < 0:
                        raise InputValidationError(
                            "INVALID_EXPRESSION",
                            "Expression values must be finite and non-negative.",
                            line=line_number,
                        )
                    if expression == 0:
                        zero_values += 1
                    minimum_expression = min(minimum_expression, expression)
                    maximum_expression = max(maximum_expression, expression)

                gene_rows += 1
    except UnicodeDecodeError as exc:
        raise InputValidationError("INVALID_ENCODING", "TSV must be UTF-8 encoded.") from exc

    if gene_rows == 0:
        raise InputValidationError("NO_GENE_ROWS", "TSV contains no gene expression rows.")

    return InputSummary(
        filename=filename,
        size_bytes=path.stat().st_size,
        gene_rows=gene_rows,
        unique_gene_ids=len(gene_ids),
        duplicate_gene_rows=duplicate_gene_rows,
        sample_count=len(sample_ids),
        sample_ids=sample_ids,
        minimum_expression=minimum_expression,
        maximum_expression=maximum_expression,
        zero_values=zero_values,
        duplicate_gene_strategy=duplicate_gene_strategy,
    )


def _stable_unit_interval(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    integer = int.from_bytes(digest[:8], "big")
    return (integer + 1) / (2**64 + 1)


def _mock_scores(file_digest: str, task: str, sample_id: str, labels: list[str]) -> list[dict[str, Any]]:
    if len(labels) == 2:
        positive = 0.15 + 0.70 * _stable_unit_interval(f"{file_digest}:{task}:{sample_id}")
        values = [1.0 - positive, positive]
    else:
        raw = [
            0.05 + _stable_unit_interval(f"{file_digest}:{task}:{sample_id}:{label}")
            for label in labels
        ]
        total = sum(raw)
        values = [value / total for value in raw]

    return sorted(
        [
            {"label": label, "score": round(score, 6)}
            for label, score in zip(labels, values, strict=True)
        ],
        key=lambda item: item["score"],
        reverse=True,
    )


def run_mock_inference(
    path: Path,
    *,
    filename: str,
    file_digest: str,
    task: str,
) -> dict[str, Any]:
    definition = TASKS[task]
    summary = inspect_tsv(path, filename=filename)
    predictions = []
    for sample_id in summary.sample_ids:
        scores = _mock_scores(file_digest, task, sample_id, definition["labels"])
        predictions.append(
            {
                "sample_id": sample_id,
                "predicted_label": scores[0]["label"],
                "scores": scores,
            }
        )

    warnings = [
        "This result was generated by the deterministic local mock adapter, not an RNABag checkpoint."
    ]
    if summary.duplicate_gene_rows:
        warnings.append(
            f"Detected {summary.duplicate_gene_rows} duplicate GeneID rows. "
            "Sum is recorded as the provisional strategy and must be confirmed against training preprocessing. "
            "The mock adapter does not use expression values to calculate scores."
        )

    return {
        "mode": "mock",
        "task": task,
        "modality": definition["modality"],
        "model_version": "local-mock-v1",
        "input_summary": asdict(summary),
        "predictions": predictions,
        "warnings": warnings,
    }
