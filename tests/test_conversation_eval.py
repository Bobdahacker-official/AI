import pytest
from astheral.conversation_eval import assess, CASES


class HarnessOnlyAssistant:
    """A unit-test stub for report/history plumbing, never capability evidence."""
    step = 10
    def __init__(self):
        self.history_lengths = []
    def reply(self, messages, **kwargs):
        self.history_lengths.append(len(messages))
        assert messages[-1]["role"] == "user"
        return {"response": "unit-test output", "history_messages_dropped": 0}


def test_evaluator_runs_25_user_turns_with_generated_history():
    model = HarnessOnlyAssistant()
    report = assess(model)
    assert len(CASES) == 25
    assert model.history_lengths == list(range(1, 50, 2))
    assert report["user_turns"] == 25
    assert report["total_messages"] == 50
    assert len(report["results"]) == 25


@pytest.mark.parametrize("turns", [0, 26])
def test_evaluator_rejects_invalid_turn_counts(turns):
    with pytest.raises(ValueError):
        assess(HarnessOnlyAssistant(), turns)
