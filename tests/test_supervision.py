import numpy as np
from astheral.supervision import assistant_mask


def test_only_assistant_answers_and_their_end_tokens_are_labeled():
    # Role IDs: assistant 1, end 2, user 3, system 4; text IDs >=10.
    tokens = np.array([4, 10, 2, 3, 11, 2, 1, 12, 13, 2, 3, 14, 2, 1, 15, 2])
    mask = assistant_mask(tokens, 1, 2, 3, 4)
    assert np.flatnonzero(mask).tolist() == [7, 8, 9, 14, 15]
    # Next-token target masks must shift one position relative to input windows.
    assert mask[6 + 1:6 + 4].tolist() == [1, 1, 1]


def test_incomplete_or_interrupted_answers_are_not_mislabeled():
    tokens = np.array([1, 10, 3, 11, 2, 1, 12])
    assert not assistant_mask(tokens, 1, 2, 3, 4).any()
