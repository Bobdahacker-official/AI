import numpy as np
import pytest
from astheral.batching import complete_batch


def test_examples_keep_full_prefix_and_mask_prompt_and_padding():
    tokens = np.array([2, 10, 3, 11, 4, 2, 20, 3, 21, 22, 4])
    mask = np.array([0, 0, 0, 1, 1, 0, 0, 0, 1, 1, 1])
    ranges = np.array([[0, 5], [5, 11]])
    x, y = complete_batch(tokens, ranges, mask, [1, 0], 6)
    assert x.tolist() == [[2, 20, 3, 21, 22, 0], [2, 10, 3, 11, 0, 0]]
    assert y.tolist() == [[-100, -100, 21, 22, 4, -100], [-100, -100, 11, 4, -100, -100]]


def test_invalid_or_unsupervised_examples_fail():
    with pytest.raises(ValueError):
        complete_batch(np.arange(8), np.array([[0, 8]]), np.ones(8), [0], 3)
    with pytest.raises(ValueError):
        complete_batch(np.arange(3), np.array([[0, 3]]), np.zeros(3), [0], 3)
