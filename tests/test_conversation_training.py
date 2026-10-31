import torch
from astheral.model import Astheral, Config
from astheral.conversation_train import prefix, suffix


def test_reply_start_weight_emphasizes_reply_choice_and_ignores_padding():
    from astheral.conversation_train import reply_loss
    logits = torch.zeros(1, 8, 3)
    logits[0, 0, 1] = 8  # Wrong first supervised prediction.
    logits[0, 3:6, 0] = 8  # Easy continuation tokens.
    targets = torch.tensor([[0, 0, 0, 0, 0, 0, -100, -100]])
    assert reply_loss(logits, targets, 5) > reply_loss(logits, targets, 1)
    original = reply_loss(logits, targets, 5)
    logits[0, 6:] = 1000
    torch.testing.assert_close(reply_loss(logits, targets, 5), original)


def test_context_replay_labels_only_final_teacher_answer(tmp_path):
    import json
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers
    from astheral.data import SPECIAL
    from astheral.conversation_train import examples
    t = Tokenizer(models.BPE())
    t.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    t.train_from_iterator(["Hello world"], trainers.BpeTrainer(vocab_size=300, special_tokens=SPECIAL, initial_alphabet=pre_tokenizers.ByteLevel.alphabet()))
    path = tmp_path / "lessons.json"
    path.write_text(json.dumps({"train": [["Hello", "Hi"], ["Your name?", "Astheral"]], "validation": [["Bye", "Goodbye"]]}))
    _, base = examples(path, t)
    _, augmented = examples(path, t, context_replay=True)
    assert len(augmented["train"]) > len(base["train"])
    assert len(augmented["validation"]) == len(base["validation"])
    for x, y in augmented["train"][len(base["train"]):]:
        last_assistant = torch.nonzero(x == t.token_to_id("<|assistant|>"))[-1].item()
        assert torch.all(y[:last_assistant] == -100)
        assert torch.any(y[last_assistant:] != -100)
        assert len(x) <= 512


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


def test_auxiliary_topic_head_cannot_see_future_teacher_answer():
    torch.manual_seed(4)
    model = Astheral(Config(vocab_size=32, width=16, layers=3, heads=2, hidden=32, context=12))
    first = torch.tensor([[2, 4, 3, 7, 8]])
    changed_answer = torch.tensor([[2, 4, 3, 22, 23]])
    _, hidden = suffix(model, prefix(model, first, 2), 2, return_hidden=True)
    _, other = suffix(model, prefix(model, changed_answer, 2), 2, return_hidden=True)
    torch.testing.assert_close(hidden[:, 2], other[:, 2])
    head = torch.nn.Linear(16, 3)
    loss = torch.nn.functional.cross_entropy(head(hidden[:, 2]), torch.tensor([1]))
    loss.backward()
    assert head.weight.grad.abs().sum() > 0
    assert model.blocks[-1].qkv.weight.grad.abs().sum() > 0
