from __future__ import annotations

import csv
import math
import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .catalog import TASKS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAPPING_PATH = PROJECT_ROOT / "mapping" / "Human_GRCh38.p13_annot.tsv"
HVG_PATH = PROJECT_ROOT / "RNABag" / "data" / "tcga_hvg_gene_4096.txt"
CHECKPOINT_DIR = PROJECT_ROOT / "RNABag" / "infer_code" / "checkpoints"
GENE_HEADER_NAMES = {"geneid", "gene_id", "gene"}
PLATELET_HEALTHY_THRESHOLD = 0.003955459

MODEL_TASKS = {
    "tissue_cancer_detection": ("tissue_cancer_detect", "Tissue_cancer_detect.ckpt"),
    "tissue_origin_identification": ("tissue_origin", "Tissue_origin.ckpt"),
    "platelet_cancer_detection": ("platelet_cancer_detect", "Platelet_cancer_detect.ckpt"),
    "platelet_tumor_localization": ("platelet_tumor_local", "Platelet_tumor_local.ckpt"),
}


class InputValidationError(ValueError):
    def __init__(self, code: str, message: str, *, line: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.line = line


class InferenceRuntimeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class InputSummary:
    filename: str
    size_bytes: int
    gene_rows: int
    unique_gene_ids: int
    duplicate_gene_rows: int
    duplicate_symbol_rows: int
    mapped_unique_gene_ids: int
    unmapped_unique_gene_ids: int
    model_hvg_found: int
    model_hvg_total: int
    model_hvg_missing: int
    sample_count: int
    sample_ids: list[str]
    minimum_expression: float
    maximum_expression: float
    zero_values: int
    title_rows_skipped: int
    duplicate_gene_strategy: str
    synonym_strategy: str


@dataclass(frozen=True)
class GeneResources:
    hvg_genes: tuple[str, ...]
    hvg_index: dict[str, int]
    known_gene_ids: frozenset[str]
    target_by_gene_id: dict[str, str]
    safe_synonym_targets: int


@dataclass(frozen=True)
class _ScanSummary:
    gene_rows: int
    unique_gene_ids: int
    duplicate_gene_rows: int
    sample_ids: list[str]
    minimum_expression: float
    maximum_expression: float
    zero_values: int
    title_rows_skipped: int


@dataclass(frozen=True)
class _LoadedModel:
    model: Any
    device: Any
    version: str


@lru_cache(maxsize=1)
def load_gene_resources() -> GeneResources:
    if not MAPPING_PATH.is_file():
        raise InferenceRuntimeError("MAPPING_NOT_FOUND", f"Gene mapping is missing: {MAPPING_PATH}")
    if not HVG_PATH.is_file():
        raise InferenceRuntimeError("HVG_NOT_FOUND", f"HVG list is missing: {HVG_PATH}")

    hvg_genes = tuple(
        line.strip()
        for line in HVG_PATH.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    )
    if len(hvg_genes) != 4096 or len(set(hvg_genes)) != 4096:
        raise InferenceRuntimeError(
            "INVALID_HVG_LIST", "HVG list must contain exactly 4096 unique gene names."
        )
    hvg_set = set(hvg_genes)

    rows: list[tuple[str, str, set[str]]] = []
    current_by_gene_id: dict[str, str] = {}
    try:
        with MAPPING_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            required = {"GeneID", "Symbol"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise InferenceRuntimeError(
                    "INVALID_MAPPING", "Mapping TSV must contain GeneID and Symbol columns."
                )
            for row in reader:
                gene_id = (row.get("GeneID") or "").strip()
                symbol = (row.get("Symbol") or "").strip()
                if not gene_id or not symbol:
                    continue
                previous = current_by_gene_id.get(gene_id)
                if previous is not None:
                    if previous != symbol:
                        raise InferenceRuntimeError(
                            "AMBIGUOUS_MAPPING",
                            f"GeneID {gene_id} maps to multiple current Symbols.",
                        )
                    continue
                current_by_gene_id[gene_id] = symbol
                aliases = {
                    alias.strip()
                    for alias in (row.get("Synonyms") or "").split("|")
                    if alias.strip() in hvg_set
                }
                rows.append((gene_id, symbol, aliases))
    except UnicodeDecodeError as exc:
        raise InferenceRuntimeError("INVALID_MAPPING", "Mapping TSV must be UTF-8 encoded.") from exc

    owners: dict[str, set[str]] = {}
    for gene_id, symbol, aliases in rows:
        if symbol in hvg_set:
            owners.setdefault(symbol, set()).add(gene_id)
        for alias in aliases:
            owners.setdefault(alias, set()).add(gene_id)

    target_by_gene_id: dict[str, str] = {}
    safe_synonym_targets = 0
    for gene_id, symbol, aliases in rows:
        if symbol in hvg_set:
            target_by_gene_id[gene_id] = symbol
        elif len(aliases) == 1:
            alias = next(iter(aliases))
            if owners.get(alias) == {gene_id}:
                target_by_gene_id[gene_id] = alias
                safe_synonym_targets += 1

    return GeneResources(
        hvg_genes=hvg_genes,
        hvg_index={gene: index for index, gene in enumerate(hvg_genes)},
        known_gene_ids=frozenset(current_by_gene_id),
        target_by_gene_id=target_by_gene_id,
        safe_synonym_targets=safe_synonym_targets,
    )


def _read_header(reader: Any) -> tuple[list[str], int, int]:
    for line_number, row in enumerate(reader, start=1):
        if not row or all(not cell.strip() for cell in row):
            continue
        if row[0].strip().lower() not in GENE_HEADER_NAMES:
            if line_number >= 5:
                break
            continue
        if len(row) < 2:
            raise InputValidationError(
                "INVALID_HEADER", "TSV must contain GeneID and at least one sample column."
            )
        sample_ids = [value.strip() for value in row[1:]]
        if any(not sample_id for sample_id in sample_ids):
            raise InputValidationError("EMPTY_SAMPLE_ID", "Sample column names must not be empty.")
        if len(sample_ids) != len(set(sample_ids)):
            raise InputValidationError("DUPLICATE_SAMPLE_ID", "Sample column names must be unique.")
        return row, line_number, line_number - 1
    raise InputValidationError(
        "INVALID_GENE_HEADER",
        "A GeneID header must appear within the first five TSV rows.",
    )


def _scan_tsv(
    path: Path,
    *,
    on_header: Callable[[list[str]], None] | None = None,
    on_unique_row: Callable[[str, list[float]], None] | None = None,
) -> _ScanSummary:
    gene_ids: set[str] = set()
    duplicate_gene_rows = 0
    gene_rows = 0
    zero_values = 0
    minimum_expression = math.inf
    maximum_expression = -math.inf

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t")
            header, header_line, title_rows_skipped = _read_header(reader)
            sample_ids = [value.strip() for value in header[1:]]
            if on_header:
                on_header(sample_ids)

            for line_number, row in enumerate(reader, start=header_line + 1):
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
                if not gene_id.isascii() or not gene_id.isdigit():
                    raise InputValidationError(
                        "INVALID_GENE_ID",
                        "GeneID values must be unrounded integer text (for example, 100287102).",
                        line=line_number,
                    )

                values: list[float] = []
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
                    values.append(expression)
                    if expression == 0:
                        zero_values += 1
                    minimum_expression = min(minimum_expression, expression)
                    maximum_expression = max(maximum_expression, expression)

                if gene_id in gene_ids:
                    duplicate_gene_rows += 1
                else:
                    gene_ids.add(gene_id)
                    if on_unique_row:
                        on_unique_row(gene_id, values)
                gene_rows += 1
    except UnicodeDecodeError as exc:
        raise InputValidationError("INVALID_ENCODING", "TSV must be UTF-8 encoded.") from exc

    if gene_rows == 0:
        raise InputValidationError("NO_GENE_ROWS", "TSV contains no gene expression rows.")

    return _ScanSummary(
        gene_rows=gene_rows,
        unique_gene_ids=len(gene_ids),
        duplicate_gene_rows=duplicate_gene_rows,
        sample_ids=sample_ids,
        minimum_expression=minimum_expression,
        maximum_expression=maximum_expression,
        zero_values=zero_values,
        title_rows_skipped=title_rows_skipped,
    )


def preprocess_tsv(
    path: Path,
    *,
    filename: str,
    collect_matrix: bool = True,
) -> tuple[np.ndarray | None, InputSummary]:
    resources = load_gene_resources()
    matrix: np.ndarray | None = None
    mapped_unique_gene_ids = 0
    model_targets_seen: set[str] = set()
    duplicate_symbol_rows = 0

    def prepare_matrix(sample_ids: list[str]) -> None:
        nonlocal matrix
        if collect_matrix:
            # Float64 matches the historical pandas -> numpy log1p pipeline;
            # tensors are converted to float32 only at the model boundary.
            matrix = np.zeros((len(sample_ids), len(resources.hvg_genes)), dtype=np.float64)

    def consume_row(gene_id: str, values: list[float]) -> None:
        nonlocal mapped_unique_gene_ids, duplicate_symbol_rows
        if gene_id in resources.known_gene_ids:
            mapped_unique_gene_ids += 1
        target = resources.target_by_gene_id.get(gene_id)
        if target is None:
            return
        if target in model_targets_seen:
            duplicate_symbol_rows += 1
            return
        model_targets_seen.add(target)
        if matrix is not None:
            matrix[:, resources.hvg_index[target]] = np.log1p(
                np.asarray(values, dtype=np.float64)
            )

    scan = _scan_tsv(path, on_header=prepare_matrix, on_unique_row=consume_row)
    if not model_targets_seen:
        raise InputValidationError(
            "NO_MODEL_GENES",
            "No uploaded GeneID mapped to the 4096-gene RNABag input; check identifier export and mapping version.",
        )
    summary = InputSummary(
        filename=filename,
        size_bytes=path.stat().st_size,
        gene_rows=scan.gene_rows,
        unique_gene_ids=scan.unique_gene_ids,
        duplicate_gene_rows=scan.duplicate_gene_rows,
        duplicate_symbol_rows=duplicate_symbol_rows,
        mapped_unique_gene_ids=mapped_unique_gene_ids,
        unmapped_unique_gene_ids=scan.unique_gene_ids - mapped_unique_gene_ids,
        model_hvg_found=len(model_targets_seen),
        model_hvg_total=len(resources.hvg_genes),
        model_hvg_missing=len(resources.hvg_genes) - len(model_targets_seen),
        sample_count=len(scan.sample_ids),
        sample_ids=scan.sample_ids,
        minimum_expression=scan.minimum_expression,
        maximum_expression=scan.maximum_expression,
        zero_values=scan.zero_values,
        title_rows_skipped=scan.title_rows_skipped,
        duplicate_gene_strategy="first",
        synonym_strategy="current_symbol_then_single_unique_hvg_synonym",
    )
    return matrix, summary


def inspect_tsv(path: Path, *, filename: str) -> InputSummary:
    _, summary = preprocess_tsv(path, filename=filename, collect_matrix=False)
    return summary


def _resolve_device() -> str:
    try:
        import torch
    except ImportError as exc:
        raise InferenceRuntimeError(
            "TORCH_NOT_INSTALLED", "PyTorch is required for RNABag checkpoint inference."
        ) from exc

    configured = os.getenv("RNABAG_DEVICE", "auto").strip().lower()
    if configured == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if configured.startswith("cuda") and not torch.cuda.is_available():
        raise InferenceRuntimeError(
            "DEVICE_UNAVAILABLE", f"Configured device {configured!r} is not available."
        )
    if configured == "mps" and not torch.backends.mps.is_available():
        raise InferenceRuntimeError("DEVICE_UNAVAILABLE", "Configured MPS device is not available.")
    return configured


def runtime_asset_summary() -> dict[str, Any]:
    resources = load_gene_resources()
    missing_checkpoints = [
        checkpoint_name
        for _, checkpoint_name in MODEL_TASKS.values()
        if not (CHECKPOINT_DIR / checkpoint_name).is_file()
    ]
    if missing_checkpoints:
        raise InferenceRuntimeError(
            "CHECKPOINT_NOT_FOUND",
            f"Missing configured checkpoints: {', '.join(missing_checkpoints)}",
        )
    return {
        "hvg_genes": len(resources.hvg_genes),
        "mapping_gene_ids": len(resources.known_gene_ids),
        "checkpoints": len(MODEL_TASKS),
        "device": _resolve_device(),
    }


@lru_cache(maxsize=8)
def _load_model(task: str, device_name: str) -> _LoadedModel:
    try:
        import torch
        from RNABag.infer_code.config.config import get_config
        from RNABag.infer_code.models.model import theModel
    except ImportError as exc:
        raise InferenceRuntimeError(
            "MODEL_IMPORT_FAILED", "RNABag model dependencies could not be imported."
        ) from exc

    legacy_task, checkpoint_name = MODEL_TASKS[task]
    checkpoint_path = CHECKPOINT_DIR / checkpoint_name
    if not checkpoint_path.is_file():
        raise InferenceRuntimeError(
            "CHECKPOINT_NOT_FOUND", f"Checkpoint is missing: {checkpoint_path}"
        )

    config = get_config(legacy_task)
    device = torch.device(device_name)
    try:
        checkpoint = torch.load(checkpoint_path, map_location=device)
        state_dict = {
            (key[6:] if key.startswith("model.") else key): value
            for key, value in checkpoint["state_dict"].items()
        }
        model = theModel(config)
        incompatible = model.load_state_dict(state_dict, strict=False)
    except Exception as exc:
        raise InferenceRuntimeError(
            "CHECKPOINT_LOAD_FAILED", f"Failed to load {checkpoint_name}."
        ) from exc

    unexpected = [
        key for key in incompatible.unexpected_keys if not key.startswith("decoder_expr.")
    ]
    if incompatible.missing_keys or unexpected:
        raise InferenceRuntimeError(
            "CHECKPOINT_INCOMPATIBLE",
            f"{checkpoint_name} does not match the inference model architecture.",
        )
    model.to(device)
    model.eval()
    version = (
        f"{checkpoint_path.stem}"
        f"-epoch{checkpoint.get('epoch', 'unknown')}"
        f"-step{checkpoint.get('global_step', 'unknown')}"
    )
    return _LoadedModel(model=model, device=device, version=version)


def _configured_batch_size(device_type: str) -> int:
    default = "8" if device_type == "cuda" else "1"
    try:
        batch_size = int(os.getenv("RNABAG_BATCH_SIZE", default))
    except ValueError as exc:
        raise InferenceRuntimeError(
            "INVALID_BATCH_SIZE", "RNABAG_BATCH_SIZE must be a positive integer."
        ) from exc
    if batch_size < 1:
        raise InferenceRuntimeError(
            "INVALID_BATCH_SIZE", "RNABAG_BATCH_SIZE must be a positive integer."
        )
    return batch_size


def _predict(matrix: np.ndarray, task: str) -> tuple[list[dict[str, Any]], str]:
    import torch
    import torch.nn.functional as functional

    loaded = _load_model(task, _resolve_device())
    labels = TASKS[task]["labels"]
    batch_size = _configured_batch_size(loaded.device.type)
    matrix32 = matrix.astype(np.float32, copy=False)
    sums32 = matrix.sum(axis=1, dtype=np.float64).astype(np.float32, copy=False)

    gene_template = torch.cat(
        (
            torch.zeros(1, dtype=torch.long),
            torch.arange(1, 4097, dtype=torch.long),
            torch.zeros(2, dtype=torch.long),
        )
    ).to(loaded.device)
    all_probabilities: list[list[float]] = []
    try:
        with torch.inference_mode():
            for start in range(0, matrix32.shape[0], batch_size):
                stop = min(start + batch_size, matrix32.shape[0])
                expression = torch.from_numpy(matrix32[start:stop]).to(loaded.device)
                summary_tokens = torch.from_numpy(sums32[start:stop, None]).to(loaded.device)
                expression = torch.cat(
                    (
                        torch.zeros((stop - start, 1), device=loaded.device),
                        expression,
                        summary_tokens,
                        summary_tokens,
                    ),
                    dim=1,
                )
                genes = gene_template.unsqueeze(0).expand(stop - start, -1)
                probabilities = functional.softmax(
                    loaded.model({"gene": genes, "expr": expression}), dim=-1
                )
                all_probabilities.extend(probabilities.detach().cpu().tolist())
    except RuntimeError as exc:
        if "out of memory" in str(exc).lower():
            raise InferenceRuntimeError(
                "INFERENCE_OUT_OF_MEMORY",
                "Inference ran out of device memory; reduce RNABAG_BATCH_SIZE.",
            ) from exc
        raise InferenceRuntimeError(
            "MODEL_FORWARD_FAILED", "RNABag checkpoint inference failed."
        ) from exc

    predictions = []
    for probabilities in all_probabilities:
        if task == "platelet_cancer_detection":
            predicted_index = 0 if probabilities[0] > PLATELET_HEALTHY_THRESHOLD else 1
        else:
            predicted_index = int(np.argmax(probabilities))
        scores = sorted(
            [
                {"label": label, "score": round(float(score), 8)}
                for label, score in zip(labels, probabilities, strict=True)
            ],
            key=lambda item: item["score"],
            reverse=True,
        )
        predictions.append(
            {
                "predicted_label": labels[predicted_index],
                "scores": scores,
            }
        )
    return predictions, loaded.version


def run_checkpoint_inference(
    path: Path,
    *,
    filename: str,
    task: str,
) -> dict[str, Any]:
    if task not in MODEL_TASKS:
        raise InferenceRuntimeError("TASK_NOT_IMPLEMENTED", "No checkpoint is configured for this task.")
    definition = TASKS[task]
    matrix, summary = preprocess_tsv(path, filename=filename)
    if matrix is None:
        raise InferenceRuntimeError("PREPROCESSING_FAILED", "Model input matrix was not created.")

    predictions, model_version = _predict(matrix, task)
    for sample_id, prediction in zip(summary.sample_ids, predictions, strict=True):
        prediction["sample_id"] = sample_id

    warnings = [
        "Research-use output only; RNABag predictions are not clinical diagnoses."
    ]
    if summary.model_hvg_missing:
        warnings.append(
            f"{summary.model_hvg_missing} of {summary.model_hvg_total} model genes were absent "
            "and filled with zero."
        )
    if summary.duplicate_gene_rows or summary.duplicate_symbol_rows:
        warnings.append(
            "Duplicate GeneID/model-Symbol rows were resolved with first occurrence wins."
        )

    return {
        "mode": "checkpoint",
        "task": task,
        "modality": definition["modality"],
        "model_version": model_version,
        "input_summary": asdict(summary),
        "predictions": predictions,
        "warnings": warnings,
    }
