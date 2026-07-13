import argparse
import torch
import torch.nn.functional as F
from config.config import get_config
from models.model import theModel
from data.datamodule import Data4Module
from utils.helpers import load_checkpoint
from utils.seeds import set_seed

def run_inference(task, device="cpu"):
    set_seed(42)
    config = get_config(task)
    if task == "tissue_cancer_detect":
        from data.id_to_name import key_to_cancer_detect as key_to_name
    elif task == "plasma_cancer_detect":
        from data.id_to_name import key_to_cancer_detect as key_to_name
    elif task == "platelet_cancer_detect":
        from data.id_to_name import key_to_cancer_detect as key_to_name
    elif task == "platelet_tumor_local":
        from data.id_to_name import key_to_platelet_tumor_local as key_to_name
    elif task == "tissue_origin":
        from data.id_to_name import key_to_tissue_origin as key_to_name

        
    # Load data
    dm = Data4Module(config)
    dm.setup()
    dataloader = dm.test_dataloader()
    
    # Instantiate and load model
    model = theModel(config)
    model = load_checkpoint(model, config.pretrained_model_path, device)
    # Run inference
    all_preds = []
    with torch.no_grad():
        for batch in dataloader:
            batch = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in batch.items()}
            logits = model(batch)
            probs = F.softmax(logits, dim=-1)
            
            if task == "platelet_cancer_detect":
                preds_list = []
                for item in probs:
                    if item[0] > 0.003955459:
                        preds_list.append(0)
                    else:
                        preds_list.append(1)
                all_preds.extend(preds_list)
            else:
                preds = torch.argmax(probs, dim=-1)
                all_preds.extend(preds.cpu().numpy().tolist())
            
    # Map predictions to names
    pred_names = [key_to_name[pred] for pred in all_preds]
    
    return pred_names
