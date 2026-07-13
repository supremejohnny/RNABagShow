import torch
import torch.nn as nn
import math
from .encoder import TransformerEncoder

class EmbeddingInt(nn.Module):
    def __init__(self, n_int, d_embed):
        super().__init__()
        self.d_embed = d_embed
        self.embed = nn.Embedding(n_int, d_embed)
    def forward(self, x):
        return self.embed(x) * math.sqrt(self.d_embed)

class MLP(nn.Module):
    def __init__(self, in_dim, hidden_dim, out_dim, dropout=0.1):
        super().__init__()
        self.link = nn.Sequential(
            nn.Linear(in_dim, hidden_dim),
            nn.Dropout(dropout),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, out_dim),
        )
    def forward(self, x):
        return self.link(x)

class theModel(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.config = config
        d_model = config.d_model
        dropout = config.dropout
        total_ids = config.total_ids
        d_id = config.d_id
        d_value = config.d_value
        seq_len = config.seq_len
        compress_d_model = config.compress_d_model
        compress_seq_len = config.compress_seq_len
        n_labels = config.n_labels

        self.id_embedding = EmbeddingInt(total_ids, d_id)
        self.value_embedding = nn.Linear(1, d_value)
        self.correct_dim = MLP(d_id + d_value, d_model, d_model, dropout)
        
        self.encoder = TransformerEncoder(
            n_layers=config.n_layers,
            n_heads=config.n_heads,
            d_model=d_model,
            dim_feedforward=config.d_ffn,
            dropout=dropout
        )


        self._create_emb = self._create_emb_cls
        d_emb = d_model
        self.decoder_label = MLP(d_emb, d_emb, n_labels, dropout)

    def _create_emb_cls(self, encoder_output):
        return encoder_output[:, 0, :]

    def forward(self, batch):
        x, gene_ids = batch['expr'], batch['gene']
        id_emb = self.id_embedding(gene_ids)
        
        x = x.unsqueeze(-1)
        val_emb = self.value_embedding(x)
        
        x = torch.cat([id_emb, val_emb], dim=-1)
        x = self.correct_dim(x)
        
        encoder_output = self.encoder(x)
        emb = self._create_emb(encoder_output)
        pred_label = self.decoder_label(emb)
        
        return pred_label
