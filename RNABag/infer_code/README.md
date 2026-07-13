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

1. Install the required dependencies:
```bash
pip install -r requirements.txt
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
python main.py --task tissue_cancer_detect --tag clinic_pancreas --device cuda
```

### 2. Tissue Origin Mode
```bash
python main.py --task tissue_origin --tag clinic_gastric --device cuda
```

### Arguments:
- `--task`: Choose between `tissue_cancer_detect` and `tissue_origin`.
- `--tag`: Data tag for loading input files (expects `log1p_tissue.npy`).
- `--device`: Device to run on (default: `cuda` if available, else `cpu`).

## Key Features
- **Stripped Inference Logic**: All masking and unused training utilities have been removed.
- **Modular Structure**: Clear separation between configuration, model definition, data pipeline, and inference logic.
- **Unified Task Switching**: Easily switch between tasks using the `--task` argument.
