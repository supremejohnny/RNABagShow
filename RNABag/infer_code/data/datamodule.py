import lightning.pytorch as L
from torch.utils.data import DataLoader
from .dataset import myDataset

class Data4Module(L.LightningDataModule):
    def __init__(self, config):
        super().__init__()
        self.config = config

    def setup(self, stage=None):
        self.dataset = myDataset(self.config)

    def train_dataloader(self):
        return DataLoader(self.dataset, batch_size=self.config.bs, shuffle=True, num_workers=self.config.cpu_workers)
        
    def val_dataloader(self):
        return DataLoader(self.dataset, batch_size=self.config.bs, shuffle=False, num_workers=self.config.cpu_workers)
    
    def test_dataloader(self):
        return DataLoader(self.dataset, batch_size=self.config.bs, shuffle=False, num_workers=self.config.cpu_workers)
