import pandas as pd
import numpy as np
import argparse
import os

def process_rna_data(fpkm_file, mapping_file, info_file, hvg_file, output_dir="output"):
    """
    Refactored RNA data processing script.
    - Maps GeneID to Symbol
    - Transposes FPKM data
    - Extracts tissue info and labels
    - Filters by HVG genes
    - Applies log1p transformation
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 1. Load data
    print("Loading data...")
    gene_mapping = pd.read_csv(mapping_file, sep="\t")
    fpkm_data = pd.read_csv(fpkm_file, sep="\t")
    
    # 2. Map GeneID to Symbol
    print("Mapping GeneID to Symbol...")
    gene_symbol_dict = dict(zip(gene_mapping['GeneID'], gene_mapping['Symbol']))
    fpkm_data['gene_name'] = fpkm_data['GeneID'].map(gene_symbol_dict)
    
    # Reorder columns: gene_name first, remove GeneID
    cols = ['gene_name'] + [col for col in fpkm_data.columns if col not in ['gene_name', 'GeneID']]
    fpkm_data = fpkm_data[cols]
    
    # 3. Transpose data
    print("Transposing data...")
    fpkm_transposed = fpkm_data.set_index('gene_name').T
    
    # 4. Filter by HVG Genes
    print("Filtering by HVG genes...")
    with open(hvg_file, "r") as f:
        hvg_genes = [line.strip() for line in f]
    
    # Ensure all HVG genes exist in the dataframe, fill with 0 if missing
    for gene in hvg_genes:
        if gene not in fpkm_transposed.columns:
            fpkm_transposed[gene] = 0
            
    # Keep only HVG genes
    extracted_data = fpkm_transposed[hvg_genes].dropna()
    
    # 5. Apply Log1p and Save
    print("Applying log1p transformation and saving...")
    log1p_data = np.log1p(extracted_data.values)
    npy_path = os.path.join(output_dir, 'log1p_data.npy')
    np.save(npy_path, log1p_data)
    
    print(f"Processing complete. File saved to: {npy_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Briefed RNA Data Processing")
    parser.add_argument("--fpkm", type=str, required=True, help="Path to fpkm.tsv")
    parser.add_argument("--mapping", type=str, required=True, help="Path to gene mapping (TSV)")
    parser.add_argument("--info", type=str, required=True, help="Path to info.txt")
    parser.add_argument("--hvg", type=str, default="./tcga_hvg_gene_4096.txt", help="Path to HVG gene list")
    parser.add_argument("--out", type=str, default="output", help="Output directory")
    
    args = parser.parse_args()
    
    process_rna_data(args.fpkm, args.mapping, args.info, args.hvg, args.out)
