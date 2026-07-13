# RNAbag

## Overview
![RNABag](./img/overview.png)


[RNABag: A Generalizable Transcriptome Foundation Model for Precision Oncology across Biopsy Modalities](https://www.biorxiv.org/content/10.64898/2026.04.19.719450v1)
It supports the following tasks:

- **Tissue Cancer Detection**  
- **Tissue Origin Identification**  
- **Plasma Cancer Detection**
- **Platelet Cancer Detection**  
- **Platelet Tumor Localization**  

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/DTD007/RNABag)
## Project Structure

The project is organized into two primary modules:

```
Inference_code/
├── data/                  # Data processing module
│   ├── process_data.py    # Main processing script
│   └── README.md          # Data processing documentation
└── infer_code/            # Inference module
    ├── main.py            # Unified entry point for inference
    ├── checkpoints/       # Model weights (.ckpt)
    ├── config/            # Model configurations
    ├── data/              # Dataset and DataModule definitions
    ├── inference/         # Core inference logic
    ├── models/            # Transformer architecture
    ├── utils/             # Helper utilities
    └── README.md          # Inference documentation
```

---

## Workflow Overview

The overall workflow consists of two main steps:

### 1. Data Processing
Before running inference, raw RNA-seq data (FPKM) must be processed and transformed. The `data/process_data.py` script handles mapping, filtering, and normalization.

**Key inputs required:**
- `fpkm.tsv`: Raw expression data.
- `gene_mapping.tsv`: Annotation file mapping GeneID to Symbol.
- `info.txt`: Sample metadata for tissue mapping.
- `tcga_hvg_gene_4096.txt`: List of 4096 High Variability Genes.

**Command to run processing:**
```bash
python data/process_data.py \
    --fpkm path/to/fpkm.tsv \
    --mapping path/to/gene_mapping.tsv \
    --info path/to/info.txt \
    --out output_dir
```
*The output will include `log1p_tissue.npy`.*

### 2. Downsteam Tasks
Once the data is processed, you can use the `infer_code` module to predict cancer presence or tissue origin.

**Setup:**
1. Install dependencies: `pip install -r infer_code/requirements.txt`
2. Ensure checkpoints (e.g., `Tissue_cancer_detect.ckpt`) are in `infer_code/checkpoints/`.

**Command to run:**
```bash
# For Downsteam Tasks
python infer_code/main.py --task <task_name> --device cuda

task_name :
    - tissue_cancer_detect
    - tissue_origin
    - plasma_cancer_detect
    - platelet_cancer_detect
    - platelet_tumor_local

```
*Note: The `--tag` argument should match the prefix of your processed files (e.g., if files are `log1p_tissue.npy`, use `--tag clinic_pancreas`).*
check data path: `infer_code/config/config.py`

---

email: Pengchao Luo[lingshumaa@gmail.com]

## License

This project is licensed under the MIT License.
