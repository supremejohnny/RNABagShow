# RNAbag Inference Code

This repository contains the refactored and consolidated inference logic for RNAbag model tasks: **Cancer Detection** and **Tissue Origin Identification**.

## Project Structure

```
brief_code/
├── config/
│   └── config.py              # Configuration & hyperparameters
├── models/
│   ├── __init__.py
│   ├── encoder.py             # Transformer Encoder blocks
│   └── model.py               # Main model (theModel)
├── data/
│   ├── __init__.py
│   ├── dataset.py             # myDataset class (inference-ready)
│   └── datamodule.py          # Data4Module (LightningDataModule)
├── utils/
│   ├── __init__.py
│   ├── seeds.py               # Seed setting functions
│   └── helpers.py             # Utility functions
├── inference/
│   └── run_inference.py       # Core inference logic
├── checkpoints/
│   └── Tissue_cancer_detect.ckpt
├── main.py                    # Unified entry point
├── requirements.txt
└── README.md
```

## Setup

1. The included `requirements.txt` is a legacy Conda environment export. Create
   and activate it with:
```bash
conda env create -f requirements.txt
conda activate RNABag
```

2. Ensure your model checkpoints are placed in the `checkpoints/` directory:
   - `checkpoints/Tissue_cancer_detect.ckpt`
   - `checkpoints/Tissue_origin.ckpt`
   - `checkpoints/Platelet_cancer_detect.ckpt`
   - `checkpoints/Plasma_cancer_detect.ckpt`
   - `checkpoints/Platelet_tumor_local.ckpt`

## Running Inference

You can run inference using the `main.py` entry point or by calling the `inference/run_inference.py` script directly.

### 1. Cancer Detection Mode
```bash
python main.py --task tissue_cancer_detect --device cuda
```

### 2. Tissue Origin Mode
```bash
python main.py --task tissue_origin --device cuda
```

### Arguments:
- `--task`: Choose between `tissue_cancer_detect` and `tissue_origin`.
- `--device`: Device to run on (default: `cuda` if available, else `cpu`).

Set `indir` in `config/config.py` to the directory containing
`log1p_data.npy`. The file must contain samples as rows and exactly 4096 HVG
columns in the order defined by `../data/tcga_hvg_gene_4096.txt`.

Duplicate GeneID/Symbol rows use the **first occurrence wins** rule documented
in `../data/README.md`: input order is preserved and later duplicates are
discarded without summing or averaging.

Gene names use the current annotation Symbol first. A historical HVG synonym
is accepted only when it is the row's sole HVG synonym and no other GeneID owns
that name. Unresolved or ambiguous HVGs are filled with zero. This recommended
showcase rule must be reviewed together with the future golden dataset.

`raw_sum` and `input_sum` intentionally contain the same sum of each final
4096-gene `log1p_data.npy` row. The two copies occupy separate summary-token
positions expected by the trained model and are retained for batch-effect
mitigation. Despite the historical name `raw_sum`, it is not computed from the
raw FPKM matrix in the current inference contract.

## Key Features
- **Stripped Inference Logic**: All masking and unused training utilities have been removed.
- **Modular Structure**: Clear separation between configuration, model definition, data pipeline, and inference logic.
- **Unified Task Switching**: Easily switch between tasks using the `--task` argument.
