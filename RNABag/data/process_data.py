import pandas as pd
import numpy as np
import argparse
import csv
import os


# Duplicate handling contract confirmed by the team: preserve input row order,
# keep the first row for each mapped Symbol, and discard later occurrences.
DUPLICATE_GENE_POLICY = "first"
DEFAULT_MAPPING_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "mapping",
        "Human_GRCh38.p13_annot.tsv",
    )
)


GENE_HEADER_NAMES = {"geneid", "gene_id", "gene"}


def find_expression_header(path):
    """Return the zero-based row containing the actual GeneID header.

    The supplied showcase exports optionally contain one dataset-title row
    before the tabular header. Standard TSV files beginning directly with
    ``GeneID`` remain supported.
    """
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for row_number, row in enumerate(reader):
            if row and row[0].strip().lower() in GENE_HEADER_NAMES:
                return row_number
            if row_number >= 4:
                break
    raise ValueError("FPKM TSV must contain a GeneID header within its first five rows.")


def build_model_gene_mapping(gene_mapping, hvg_genes):
    """Map GeneID to the exact model gene name using conservative aliases.

    Current Symbols always win. A historical Synonym is accepted only when
    exactly one HVG synonym is present for that annotation row and that name is
    owned by no other current Symbol or synonym in the mapping table.
    """
    required_columns = {"GeneID", "Symbol"}
    if not required_columns.issubset(gene_mapping.columns):
        raise ValueError("Mapping TSV must contain GeneID and Symbol columns.")

    mapping = gene_mapping.copy()
    if "Synonyms" not in mapping.columns:
        mapping["Synonyms"] = ""
    mapping = mapping[["GeneID", "Symbol", "Synonyms"]].fillna("")
    for column in mapping.columns:
        mapping[column] = mapping[column].astype("string").str.strip()
    mapping = mapping[(mapping["GeneID"] != "") & (mapping["Symbol"] != "")]

    conflicting_gene_ids = (
        mapping.groupby("GeneID")["Symbol"].nunique().loc[lambda counts: counts > 1]
    )
    if not conflicting_gene_ids.empty:
        raise ValueError(
            "Mapping TSV assigns multiple current Symbols to the same GeneID; "
            "resolve the mapping before preprocessing."
        )
    mapping = mapping.drop_duplicates(subset="GeneID", keep="first")

    hvg_set = set(hvg_genes)
    owners = {}
    synonym_candidates = {}
    for row in mapping.itertuples(index=False):
        gene_id = row.GeneID
        if row.Symbol in hvg_set:
            owners.setdefault(row.Symbol, set()).add(gene_id)
        candidates = {
            alias.strip()
            for alias in row.Synonyms.split("|")
            if alias.strip() in hvg_set
        }
        synonym_candidates[gene_id] = candidates
        for alias in candidates:
            owners.setdefault(alias, set()).add(gene_id)

    targets = {}
    synonym_targets = 0
    for row in mapping.itertuples(index=False):
        if row.Symbol in hvg_set:
            targets[row.GeneID] = row.Symbol
            continue
        candidates = synonym_candidates[row.GeneID]
        if len(candidates) == 1:
            alias = next(iter(candidates))
            if owners.get(alias) == {row.GeneID}:
                targets[row.GeneID] = alias
                synonym_targets += 1

    return targets, synonym_targets


def process_rna_data(fpkm_file, mapping_file, info_file, hvg_file, output_dir="output"):
    """
    Refactored RNA data processing script.
    - Maps GeneID to Symbol
    - Transposes FPKM data
    - Keeps the first duplicate GeneID/Symbol row and discards later rows
    - Filters by HVG genes
    - Applies log1p transformation

    ``info_file`` is retained for command-line compatibility but is not used by
    inference preprocessing. Labels and sample metadata belong outside the
    expression tensor contract.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # 1. Load data
    print("Loading data...")
    gene_mapping = pd.read_csv(mapping_file, sep="\t", dtype="string")
    fpkm_data = pd.read_csv(
        fpkm_file,
        sep="\t",
        header=find_expression_header(fpkm_file),
        dtype={"GeneID": "string"},
    )

    if "GeneID" not in fpkm_data.columns or len(fpkm_data.columns) < 2:
        raise ValueError("FPKM TSV must contain GeneID and at least one sample column.")

    sample_columns = [column for column in fpkm_data.columns if column != "GeneID"]
    fpkm_data[sample_columns] = fpkm_data[sample_columns].apply(
        pd.to_numeric,
        errors="raise",
    )
    if not np.isfinite(fpkm_data[sample_columns].to_numpy(dtype=float)).all():
        raise ValueError("FPKM expression values must be finite.")
    if (fpkm_data[sample_columns] < 0).any().any():
        raise ValueError("FPKM expression values must be non-negative.")
    fpkm_data["GeneID"] = fpkm_data["GeneID"].str.strip()

    with open(hvg_file, "r", encoding="utf-8") as f:
        hvg_genes = [line.strip() for line in f if line.strip()]
    if len(hvg_genes) != 4096 or len(set(hvg_genes)) != 4096:
        raise ValueError("HVG file must contain exactly 4096 unique Gene Symbols.")

    # 2. Map GeneID to Symbol
    print("Mapping GeneID to Symbol...")
    gene_symbol_dict, synonym_targets = build_model_gene_mapping(gene_mapping, hvg_genes)
    print(f"Accepted {synonym_targets} unambiguous historical-Symbol mappings.")
    fpkm_data["gene_name"] = fpkm_data["GeneID"].map(gene_symbol_dict)

    unmapped_rows = int(fpkm_data["gene_name"].isna().sum())
    if unmapped_rows:
        print(f"Ignoring {unmapped_rows} rows that do not map to a model HVG.")

    mapped_data = fpkm_data.dropna(subset=["gene_name"])
    duplicate_rows = len(mapped_data) - mapped_data["gene_name"].nunique()
    if duplicate_rows:
        print(
            f"Discarding {duplicate_rows} later duplicate Symbol rows with "
            f"strategy={DUPLICATE_GENE_POLICY}."
        )

    # One row per Symbol. Input order is preserved, so this handles both repeated
    # GeneID rows and different GeneIDs mapping to the same Symbol consistently.
    expression_by_symbol = (
        mapped_data.drop_duplicates(subset="gene_name", keep="first")
        .set_index("gene_name")[sample_columns]
    )
    
    # 3. Transpose data
    print("Transposing data...")
    fpkm_transposed = expression_by_symbol.T
    
    # 4. Filter by HVG Genes
    print("Filtering by HVG genes...")
    # Reindex guarantees both the exact model order and exactly 4096 columns.
    # Genes absent from the uploaded matrix are filled with zero.
    extracted_data = fpkm_transposed.reindex(
        columns=hvg_genes,
        fill_value=0,
    ).fillna(0)
    
    # 5. Apply Log1p and Save
    print("Applying log1p transformation and saving...")
    log1p_data = np.log1p(extracted_data.values)
    npy_path = os.path.join(output_dir, 'log1p_data.npy')
    np.save(npy_path, log1p_data)
    
    print(f"Processing complete. File saved to: {npy_path}")
    return npy_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Briefed RNA Data Processing")
    parser.add_argument("--fpkm", type=str, required=True, help="Path to fpkm.tsv")
    parser.add_argument(
        "--mapping",
        type=str,
        default=DEFAULT_MAPPING_PATH,
        help="Path to GeneID-to-Symbol mapping TSV",
    )
    parser.add_argument(
        "--info",
        type=str,
        default=None,
        help="Reserved metadata path; currently unused by inference preprocessing",
    )
    parser.add_argument(
        "--hvg",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "tcga_hvg_gene_4096.txt"),
        help="Path to the ordered 4096-gene HVG list",
    )
    parser.add_argument("--out", type=str, default="output", help="Output directory")
    
    args = parser.parse_args()
    
    process_rna_data(args.fpkm, args.mapping, args.info, args.hvg, args.out)
