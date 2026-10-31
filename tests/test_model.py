from dataclasses import asdict
import torch
import pytest

from astheral.model import Astheral, Config
from astheral.train import atomic_save


def small():
    torch.manual_seed(7)
    torch.set_num_threads(1)
    return Astheral(Config(vocab_size=32, width=32, layers=2, heads=4, hidden=64, context=16))


def test_full_parameter_count_without_allocating_weights():
    with torch.device("meta"):
        model = Astheral(Config())
    assert model.parameter_count >= 400_000_000
    assert model.parameter_count == 419_496_960


def test_attention_is_causal():
    model = small().eval()
    tokens = torch.randint(0, 32, (1, 8))
    changed = tokens.clone()
    changed[:, 4:] = (changed[:, 4:] + 1) % 32
    first = model(tokens)[0]
    second = model(changed)[0]
    torch.testing.assert_close(first[:, :4], second[:, :4])
    assert not torch.allclose(first[:, 4:], second[:, 4:])


def test_backprop_updates_every_block_and_reduces_loss():
    model = small()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.01)
    tokens = torch.arange(8).unsqueeze(0)
    targets = tokens + 1
    initial = model(tokens, targets)[1].item()
    for _ in range(15):
        optimizer.zero_grad()
        _, loss = model(tokens, targets)
        loss.backward()
        assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters())
        optimizer.step()
    assert model(tokens, targets)[1].item() < initial * 0.6


def test_checkpoint_roundtrip_and_optimizer_resume(tmp_path):
    model = small()
    optimizer = torch.optim.AdamW(model.parameters())
    x = torch.arange(8).unsqueeze(0)
    loss = model(x, x + 1)[1]
    loss.backward()
    optimizer.step()
    path = tmp_path / "latest.pt"
    atomic_save({"model": model.state_dict(), "optimizer": optimizer.state_dict(), "config": asdict(model.cfg)}, path)
    loaded = torch.load(path, weights_only=True)
    replica = Astheral(Config(**loaded["config"]))
    replica.load_state_dict(loaded["model"])
    resumed = torch.optim.AdamW(replica.parameters())
    resumed.load_state_dict(loaded["optimizer"])
    torch.testing.assert_close(model(x)[0], replica(x)[0])
    assert resumed.state_dict()["state"]


def test_context_limit():
    with pytest.raises(ValueError):
        small()(torch.zeros(1, 17, dtype=torch.long))
