from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers

from astheral.data import SPECIAL
from astheral.heldout import answer_batch


def tokenizer():
    result = Tokenizer(models.BPE())
    result.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    result.decoder = decoders.ByteLevel()
    result.train_from_iterator(["Prompt Answer"], trainers.BpeTrainer(vocab_size=280, special_tokens=SPECIAL, initial_alphabet=pre_tokenizers.ByteLevel.alphabet()))
    return result


def test_reference_loss_labels_only_human_answer_and_end():
    tok = tokenizer()
    record = {"instruction": "Prompt", "response": "Answer"}
    inputs, targets, _, answer_cut = answer_batch(tok, record, 512)
    expected = tok.encode("Answer").ids + [tok.token_to_id("<|end|>")]
    assert targets[targets != -100].tolist() == expected
    assert inputs.shape == targets.shape
    assert int((targets == -100).sum()) > 0
    assert not answer_cut


def test_long_reference_is_cropped_to_real_context_capacity():
    tok = tokenizer()
    record = {"instruction": "Prompt " * 100, "response": "Answer " * 100}
    inputs, targets, prompt_cut, answer_cut = answer_batch(tok, record, 16)
    assert inputs.shape == targets.shape == (1, 16)
    assert int((targets != -100).sum()) == 8
    assert prompt_cut and answer_cut
