# RNA Data Processing Pipeline

This repository contains a simplified and refactored version of the RNA-seq data processing pipeline for RNAbag inference.

## Overview

The processing script `data/process_data.py` performs the following steps:
1.  **Gene Mapping**: Maps GeneID to Symbol using a provided annotation file.
2.  **Data Transposition**: Transposes FPKM data to have samples as rows and genes as columns.
3.  **Tissue Extraction**: Maps sample IDs to tissue types using an `info.txt` file.
4.  **Label Generation**: Generates binary labels (1 for 'carcinoma', 0 for other) and tissue type files.
5.  **HVG Filtering**: Filters the expression data to include only the specified High Variability Genes (HVGs).
6.  **Transformation**: Applies a `log1p` transformation and saves the result as a `.npy` file.

## Required Input Files

To run the pipeline, you need the following input files:

1.  **`fpkm.tsv`**: FPKM expression data.
2.  **`gene_mapping` (TSV)**: Gene annotation file (e.g., `Human_GRCh38.p13_annot.tsv`).
3.  **`info.txt`**: Metadata file containing sample-to-tissue mapping.
4.  **`tcga_hvg_gene_4096.txt`**: List of 4096 High Variability Genes.

## Usage

Run the refactored script with the following command:

```bash
python data/process_data.py \
    --fpkm path/to/fpkm.tsv \
    --mapping path/to/gene_mapping.tsv \
    --info path/to/info.txt \
    --hvg path/to/tcga_hvg_gene_4096.txt \
    --out output_dir
```

### Arguments:
- `--fpkm`: Path to the FPKM data file.
- `--mapping`: Path to the gene mapping/annotation file.
- `--info`: Path to the tissue information file.
- `--hvg`: Path to the HVG gene list (default: `tcga_hvg_gene_4096.txt`).
- `--out`: Directory where output files will be saved (default: `output`).

## Output Files

The script will generate the following files in the specified output directory:
- `log1p_data.npy`: Processed and transformed expression data.

