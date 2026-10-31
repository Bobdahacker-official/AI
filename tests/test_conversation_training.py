import torch
from astheral.model import Astheral, Config
from astheral.conversation_train import prefix, suffix


def test_frozen_cache_matches_full_forward_and_trains_suffix_only():
    torch.manual_seed(1)
    model = Astheral(Config(vocab_size=32, width=16, layers=3, heads=2, hidden=32, context=12))
    x = torch.tensor([[2, 4, 7, 8]])
    for p in model.parameters():
        p.requires_grad_(False)
    model.blocks[-1].requires_grad_(True)
    with torch.no_grad():
        hidden = prefix(model, x, 2)
    logits = suffix(model, hidden, 2)
    expected, _ = model(x)
    torch.testing.assert_close(logits, expected)
    logits.square().sum().backward()
    assert model.embedding.weight.grad is None
    assert model.blocks[0].qkv.weight.grad is None
    assert model.blocks[-1].qkv.weight.grad.abs().sum() > 0
