"""Complete-example batches: retain prompt context and ignore padding targets."""
import numpy as np


def complete_batch(array, ranges, mask, indices, sequence, pad_id=0):
    x = np.full((len(indices), sequence), pad_id, dtype=np.int64)
    y = np.full_like(x, -100)
    for row, index in enumerate(indices):
        start, end = map(int, ranges[index])
        if not 0 <= start < end <= len(array) or not 2 <= end - start <= sequence + 1:
            raise ValueError("Invalid complete-example range")
        length = end - start - 1
        x[row, :length] = array[start:end - 1]
        targets = np.asarray(array[start + 1:end], dtype=np.int64).copy()
        targets[np.asarray(mask[start + 1:end]) == 0] = -100
        if not np.any(targets != -100):
            raise ValueError("Complete example has no assistant targets")
        y[row, :length] = targets
    return x, y
