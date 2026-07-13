import numpy as np
import torch
from torch.utils.data import Dataset
import random

class myDataset(Dataset):
    def __init__(self, config, indir=None):
        self.config = config
        self.indir = indir or config.indir
        self.data, self.raw_sum, self.input_sum = self.load_data(self.indir)

    def load_data(self, indir):
        fn_data = f'{indir}/log1p_tissue.npy'
        data = np.load(fn_data, mmap_mode='r')
        raw_sum = np.sum(data, axis=1)
        input_sum = np.sum(data, axis=1)
        return data,raw_sum, input_sum

    def __len__(self):
        return self.data.shape[0]

    def __getitem__(self, idx):
        raw_sum = self.raw_sum[idx]
        input_sum = self.input_sum[idx]
        expr = self.data[idx]
        gene = np.arange(1, len(expr) + 1)
        
        # Inference mode: masking is stripped out as requested
        combined = list(zip(gene, expr))
        random.shuffle(combined)
        gene_shuffled, expr_shuffled = zip(*combined)

        record = {
            'gene': list(gene_shuffled),
            'expr': list(expr_shuffled),
        }

        # Add CLS token
        cls_val = 0
        record['gene'] = [cls_val] + record['gene']
        record['expr'] = [cls_val] + record['expr']

        # Add total expression summary
        record['gene'] = record['gene'] + [0, 0]
        record['expr'] = record['expr'] + [float(raw_sum), float(input_sum)]

        # Convert to tensor
        record['gene'] = torch.tensor(record['gene'], dtype=torch.long)
        record['expr'] = torch.tensor(record['expr'], dtype=torch.float32)
        
        return record
