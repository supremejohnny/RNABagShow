import argparse
import torch
from inference.run_inference import run_inference

def main():
    parser = argparse.ArgumentParser(description="RNAbag Inference Main Entry")
    parser.add_argument("--task", type=str, required=True,  \
        choices=["tissue_cancer_detect", "tissue_origin","platelet_cancer_detect", \
            "platelet_tumor_local","plasma_cancer_detect"], help="Inference task")
    parser.add_argument("--device", type=str, default="cuda" if torch.cuda.is_available() else "cpu", help="Device to run on")
    
    args = parser.parse_args()
    
    # Run the inference
    predictions = run_inference(args.task, args.device)
    
    # Display the results
    print(f"Task: {args.task}")
    print(f"Predicted labels: {predictions}")

if __name__ == "__main__":
    main()
