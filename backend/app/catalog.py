from __future__ import annotations

from typing import Any


TISSUE_ORIGIN_LABELS = [
    "Adipose_Tissue",
    "Adrenal_Cortex",
    "Adrenal_Gland",
    "Bladder",
    "Blood",
    "Blood_Vessel",
    "Bone_Marrow",
    "Brain",
    "Breast",
    "Cervix",
    "Colon",
    "Esophagus",
    "Eye_Uvea",
    "Head_and_Neck",
    "Heart",
    "Kidney",
    "Liver",
    "Lung",
    "Mesothelium",
    "Muscle",
    "Nerve",
    "Ovary",
    "Pancreas",
    "Pituitary",
    "Prostate",
    "Salivary_Gland",
    "Skin",
    "Small_Intestine",
    "Soft_Tissue",
    "Spleen",
    "Stomach",
    "Testis",
    "Thymus",
    "Thyroid",
    "Uterus",
    "Vagina",
]


TASKS: dict[str, dict[str, Any]] = {
    "tissue_cancer_detection": {
        "modality": "tissue",
        "enabled": True,
        "labels": ["Healthy", "Cancer"],
        "output_type": "binary",
    },
    "tissue_origin_identification": {
        "modality": "tissue",
        "enabled": True,
        "labels": TISSUE_ORIGIN_LABELS,
        "output_type": "ranked",
    },
    "plasma_cancer_detection": {
        "modality": "plasma",
        "enabled": False,
        "labels": ["Healthy", "Cancer"],
        "output_type": "binary",
        "unavailable_reason": "Plasma inference is not available in the local prototype.",
    },
    "platelet_cancer_detection": {
        "modality": "platelet",
        "enabled": True,
        "labels": ["Healthy", "Cancer"],
        "output_type": "binary",
    },
    "platelet_tumor_localization": {
        "modality": "platelet",
        "enabled": True,
        "labels": ["HNSC", "NSCLC", "Glioma", "PAAD", "OV"],
        "output_type": "ranked",
    },
}


def public_task_catalog() -> list[dict[str, Any]]:
    return [{"task": task, **definition} for task, definition in TASKS.items()]
