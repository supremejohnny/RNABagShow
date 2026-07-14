# RNA Data Processing Pipeline

This repository contains a simplified and refactored version of the RNA-seq data processing pipeline for RNAbag inference.

## Overview

The processing script `data/process_data.py` performs the following steps:
1.  **Gene Mapping**: Maps GeneID to the model gene name using the provided current Symbol and a conservative historical-Synonym fallback.
2.  **Duplicate Handling**: Preserves input row order, keeps the first GeneID/Symbol occurrence, and discards later duplicates.
3.  **Data Transposition**: Transposes FPKM data to have samples as rows and genes as columns.
4.  **HVG Reindexing**: Reindexes to the exact order in the 4096-gene HVG file and fills missing genes with zero.
5.  **Transformation**: Applies a `log1p` transformation and saves the result as `log1p_data.npy`.

The input may begin directly with the `GeneID` header or include a short export
title above it. The parser searches the first five rows for the real header.

## HVG Symbol and Synonym Policy

The checked-in HVG list contains historical names that are not all present as
current `Symbol` values in the GRCh38.p13 annotation. The inference contract is:

1. Use the annotation's current `Symbol` when it is one of the 4096 HVGs.
2. Otherwise, inspect the pipe-delimited `Synonyms` field. Accept it only when
   that annotation row has exactly one name in the HVG list and no other GeneID
   owns that name as either a current Symbol or synonym.
3. Never guess by spelling, numeric proximity, or nearest GeneID. Ambiguous and
   unresolved names remain absent and their model columns are filled with zero.

With `mapping/Human_GRCh38.p13_annot.tsv`, 3,906 HVGs match current Symbols and
145 additional HVGs are recovered safely, for 4,051/4,096 model genes. The
remaining 45 are zero-filled even for a complete 39,376-row annotation export.
The current platelet sample contains 664/4,096 model genes because that assay
measures a smaller gene panel.

This is the recommended showcase policy, not a training-derived gold standard.
When the team finalizes a golden dataset, review this section, the
`build_model_gene_mapping` implementation, and saved expected predictions
together.

## Duplicate-Gene Policy

The project rule is **first occurrence wins**. Input row order is preserved. If
the input repeats a GeneID, only its first mapped row is retained. If different
GeneIDs map to the same Symbol, only the first row for that Symbol is retained.
All later occurrences are discarded without summing or averaging.

If the training preprocessing contract changes in the future, update both
`DUPLICATE_GENE_POLICY` in `process_data.py` and this section, then regenerate
the golden-sample results.

## Required Input Files

To run the pipeline, you need the following input files:

1.  **`fpkm.tsv`**: FPKM expression data. GeneID values must be exported as
    integer text without spreadsheet rounding or scientific-notation loss.
2.  **`gene_mapping` (TSV)**: Gene annotation file. The repository default is
    `mapping/Human_GRCh38.p13_annot.tsv`.
3.  **`tcga_hvg_gene_4096.txt`**: Ordered list of exactly 4096 unique High Variability Genes.

`info.txt` is not part of the inference tensor contract. The CLI still accepts
`--info` as an optional compatibility argument, but the processing function
does not use it to create `log1p_data.npy`.

## Optional `info.txt` for Research Metadata

You do **not** need to create `info.txt` for the current inference pipeline. If
you want to preserve non-identifying metadata for future golden-sample
evaluation and batch auditing, use a UTF-8 tab-separated text file with one row
per sample. `SampleID` must exactly match a sample column in `fpkm.tsv` and must
be unique.

Recommended schema:

```tsv
SampleID\tModality\tBatch\tCohort\tTissue\tCancerStatus\tTumorLocation
1\ttissue\tbatch_001\tstudy_A\tLung\tCancer\tNSCLC
2\ttissue\tbatch_001\tstudy_A\tUnknown\tUnknown\tUnknown
```

- `SampleID`: required identifier matching the expression-matrix header.
- `Modality`: `tissue`, `plasma`, or `platelet`.
- `Batch`: sequencing, library-preparation, or processing batch identifier.
- `Cohort`: study or project identifier.
- `Tissue`, `CancerStatus`, `TumorLocation`: optional known labels for later
  evaluation; use `Unknown` when no ground truth exists.

This metadata is not sent into the model and does not change predictions. The
current code does not parse it yet. Because the showcase is public, do not put
patient names, medical record numbers, dates of birth, contact details, or
other directly identifying information in this file.

## Usage

Run the refactored script with the following command:

```bash
python data/process_data.py \
    --fpkm path/to/fpkm.tsv \
    --hvg path/to/tcga_hvg_gene_4096.txt \
    --out output_dir
```

### Arguments:
- `--fpkm`: Path to the FPKM data file.
- `--mapping`: Optional override for the GeneID-to-Symbol annotation TSV;
  defaults to `mapping/Human_GRCh38.p13_annot.tsv`.
- `--info`: Optional compatibility argument; currently unused for inference preprocessing.
- `--hvg`: Path to the HVG gene list (default: `tcga_hvg_gene_4096.txt`).
- `--out`: Directory where output files will be saved (default: `output`).

## Output Files

The script will generate the following files in the specified output directory:
- `log1p_data.npy`: Processed and transformed expression data.

GeneID matching is exact and identifiers must be preserved as text. The
pipeline deliberately does not guess rounded or nearby GeneIDs. Missing model
genes are always represented by zero in the ordered 4096-column matrix.
