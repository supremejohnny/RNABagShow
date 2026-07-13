from argparse import Namespace

def get_config(task="cancer-detect"):
    config = Namespace(
        indir='Data_path',
        bs=8,
        cpu_workers=1,
        total_ids=4096+1,
        seq_len=4096+3,
        d_id=32,
        d_value=4,
        d_model=128,
        d_ffn=128*4,
        dropout=0.1,
        n_layers=8,
        n_heads=8,
        compress_d_model=128,
        compress_seq_len=1,
    )
    
    if task == "tissue_cancer_detect":
        config.n_labels = 2
        config.pretrained_model_path = "checkpoints/Tissue_cancer_detect.ckpt"
    elif task == "plasma_cancer_detect":
        config.n_labels = 2
        config.pretrained_model_path = "checkpoints/Plasma_cancer_detect.ckpt"
    elif task == "platelet_cancer_detect":
        config.n_labels = 2
        config.pretrained_model_path = "checkpoints/Platelet_cancer_detect.ckpt"
    elif task == "platelet_tumor_local":
        config.n_labels = 5
        config.pretrained_model_path = "checkpoints/Platelet_tumor_local.ckpt"
    elif task == "tissue_origin":
        config.n_labels = 36
        config.pretrained_model_path = "checkpoints/Tissue_origin.ckpt"
    else:
        raise ValueError(f"Unknown task: {task}")
        
    return config
