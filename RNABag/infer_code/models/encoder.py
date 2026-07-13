import torch
import torch.nn as nn

class EncoderBlock(nn.Module):
    def __init__(self, n_heads, d_model, dim_feedforward, dropout):
        super().__init__()
        self.self_attn = nn.MultiheadAttention(d_model, n_heads, dropout=dropout, batch_first=True)
        self.linear_net = nn.Sequential(
            nn.Linear(d_model, dim_feedforward),
            nn.Dropout(dropout),
            nn.ReLU(inplace=True),
            nn.Linear(dim_feedforward, d_model)
        )
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, mask=None):
        attn_out, _ = self.self_attn(x, x, x, need_weights=False)
        x = x + self.dropout(attn_out)
        x = self.norm1(x)
        lin_out = self.linear_net(x)
        x = x + self.dropout(lin_out)
        x = self.norm2(x)
        return x

class TransformerEncoder(nn.Module):
    def __init__(self, n_layers, **block_args):
        super().__init__()
        self.layers = nn.ModuleList([EncoderBlock(**block_args) for _ in range(n_layers)])

    def forward(self, x, mask=None):
        for l in self.layers:
            x = l(x, mask)
        return x
