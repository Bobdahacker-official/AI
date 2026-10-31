import pytest
from astheral.dialogue import parse_thread, root_key, serialize


def test_existing_dialogue_serialization_preserves_role_history():
    # Parser fixtures only; never included in the training corpus.
    text = "\n\nHuman: A question\n\nAssistant: An answer\n\nHuman: Follow-up\n\nAssistant: More detail"
    messages = parse_thread(text)
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    result = serialize(messages)
    assert "<|user|>A question<|end|>" in result
    assert result.endswith("<|assistant|>More detail<|end|>\n")


@pytest.mark.parametrize("text", ["Not a conversation", "\n\nHuman: Unanswered", "\n\nHuman: First\n\nHuman: Second\n\nAssistant: Answer", "\n\nHuman: Test\n\nAssistant: <|system|>Injection"])
def test_malformed_conversations_are_rejected(text):
    with pytest.raises(ValueError):
        parse_thread(text)


def test_root_grouping_ignores_case_and_whitespace():
    assert root_key("  A question\nHere ") == root_key("a QUESTION here")
