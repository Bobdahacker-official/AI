from dataclasses import asdict, dataclass, replace
import math

import torch
from torch import nn
from torch.nn import functional as F


@dataclass
class Config:
    vocab_size: int = 8192
    width: int = 1024
    layers: int = 32
    heads: int = 16
    hidden: int = 2816
    context: int = 512
    tie_embeddings: bool = True

    def __post_init__(self):
        dimensions = [value for name, value in asdict(self).items() if name != "tie_embeddings"]
        if min(dimensions) < 1 or self.width % self.heads or (self.width // self.heads) % 2:
            raise ValueError("Positive dimensions and an even, integral head dimension are necessary")


class RMSNorm(nn.Module):
    def __init__(self, width):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(width))

    def forward(self, x):
        return (x.float() * torch.rsqrt(x.float().square().mean(-1, keepdim=True) + 1e-5)).to(x.dtype) * self.weight


class Block(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.heads = cfg.heads
        self.norm1, self.norm2 = RMSNorm(cfg.width), RMSNorm(cfg.width)
        self.qkv = nn.Linear(cfg.width, 3 * cfg.width, bias=False)
        self.out = nn.Linear(cfg.width, cfg.width, bias=False)
        self.gate = nn.Linear(cfg.width, cfg.hidden, bias=False)
        self.up = nn.Linear(cfg.width, cfg.hidden, bias=False)
        self.down = nn.Linear(cfg.hidden, cfg.width, bias=False)
        inv = 1 / (10000 ** (torch.arange(0, cfg.width // cfg.heads, 2).float() / (cfg.width // cfg.heads)))
        self.register_buffer("inv_freq", inv, persistent=False)

    def rotate(self, x, offset=0):
        phase = torch.outer(torch.arange(offset, offset + x.shape[-2], device=x.device), self.inv_freq)
        cos, sin = phase.cos().to(x.dtype), phase.sin().to(x.dtype)
        even, odd = x[..., 0::2], x[..., 1::2]
        return torch.stack((even * cos - odd * sin, even * sin + odd * cos), dim=-1).flatten(-2)

    def forward(self, x, cache=None, use_cache=False):
        b, t, c = x.shape
        q, k, v = self.qkv(self.norm1(x)).view(b, t, 3, self.heads, c // self.heads).unbind(2)
        q, k, v = [a.transpose(1, 2) for a in (q, k, v)]
        offset = 0 if cache is None else cache[0].shape[-2]
        q, k = self.rotate(q, offset), self.rotate(k, offset)
        if cache is not None:
            k, v = torch.cat((cache[0], k), dim=-2), torch.cat((cache[1], v), dim=-2)
        if offset and t > 1:
            mask = torch.arange(k.shape[-2], device=x.device).unsqueeze(0) <= torch.arange(offset, offset + t, device=x.device).unsqueeze(1)
            y = F.scaled_dot_product_attention(q, k, v, attn_mask=mask)
        else:
            y = F.scaled_dot_product_attention(q, k, v, is_causal=not offset)
        x = x + self.out(y.transpose(1, 2).contiguous().view(b, t, c))
        z = self.norm2(x)
        result = x + self.down(F.silu(self.gate(z)) * self.up(z))
        return (result, (k, v)) if use_cache else result


class Astheral(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.embedding = nn.Embedding(cfg.vocab_size, cfg.width)
        self.blocks = nn.ModuleList([Block(cfg) for _ in range(cfg.layers)])
        self.norm = RMSNorm(cfg.width)
        self.output = None if cfg.tie_embeddings else nn.Linear(cfg.width, cfg.vocab_size, bias=False)
        self.apply(self.initialize)
        for block in self.blocks:
            nn.init.normal_(block.out.weight, std=0.02 / math.sqrt(2 * cfg.layers))
            nn.init.normal_(block.down.weight, std=0.02 / math.sqrt(2 * cfg.layers))

    @staticmethod
    def initialize(module):
        if isinstance(module, (nn.Linear, nn.Embedding)):
            nn.init.normal_(module.weight, std=0.02)

    @property
    def parameter_count(self):
        return sum(p.numel() for p in self.parameters())

    def untie_output(self):
        if self.output is None:
            self.output = nn.Linear(self.cfg.width, self.cfg.vocab_size, bias=False, device=self.embedding.weight.device, dtype=self.embedding.weight.dtype)
            with torch.no_grad():
                self.output.weight.copy_(self.embedding.weight)
            self.cfg = replace(self.cfg, tie_embeddings=False)

    def project(self, hidden):
        return F.linear(hidden, self.embedding.weight) if self.output is None else self.output(hidden)

    def forward(self, tokens, targets=None):
        if tokens.ndim != 2 or tokens.shape[1] > self.cfg.context:
            raise ValueError("Expected [batch, sequence] within configured context")
        x = self.embedding(tokens)
        for block in self.blocks:
            x = block(x)
        logits = self.project(self.norm(x))
        loss = None if targets is None else F.cross_entropy(logits.float().reshape(-1, self.cfg.vocab_size), targets.reshape(-1))
        return logits, loss

    def forward_cached(self, tokens, cache=None):
        offset = 0 if cache is None else cache[0][0].shape[-2]
        if tokens.ndim != 2 or tokens.shape[1] + offset > self.cfg.context:
            raise ValueError("Cached sequence exceeds the configured context")
        x, updated = self.embedding(tokens), []
        for index, block in enumerate(self.blocks):
            x, entry = block(x, None if cache is None else cache[index], use_cache=True)
            updated.append(entry)
        return self.project(self.norm(x[:, -1:])), updated
