import json
from tokenizers import Tokenizer, models, pre_tokenizers, trainers, decoders
from astheral.data import SPECIAL, format_record, SYSTEM
from astheral.corpus import format_dialogue


def test_conversation_serialization():
    text = format_record({"instruction": "Summarize", "context": "A real passage", "response": "Summary"})
    assert text.startswith(f"<|system|>{SYSTEM}<|end|>")
    assert "<|user|>Summarize\n\nA real passage<|end|>" in text
    assert text.endswith("<|assistant|>Summary<|end|>\n")


def test_byte_tokenizer_roundtrip():
    tokenizer = Tokenizer(models.BPE())
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tokenizer.decoder = decoders.ByteLevel()
    tokenizer.train_from_iterator(["Hello world"], trainers.BpeTrainer(vocab_size=300, special_tokens=SPECIAL, initial_alphabet=pre_tokenizers.ByteLevel.alphabet()))
    text = "Astheral says hello! café 🌟"
    assert tokenizer.decode(tokenizer.encode(text).ids) == text


def test_dialogue_format_preserves_roles_and_multiple_turns():
    # Verify serialization only; this fixture is never used for model training.
    dialogue = {"utterances": [{"speaker": "USER", "text": "First"}, {"speaker": "ASSISTANT", "text": "Second"}, {"speaker": "USER", "text": "Third"}]}
    result = format_dialogue(dialogue)
    assert "<|user|>First<|end|>\n<|assistant|>Second<|end|>\n<|user|>Third<|end|>" in result
