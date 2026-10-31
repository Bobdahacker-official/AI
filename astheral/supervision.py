"""Label existing assistant responses without inventing training text."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from tokenizers import Tokenizer


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assistant_mask(tokens, assistant_id, end_id, user_id, system_id):
    result = np.zeros(len(tokens), dtype=np.uint8)
    boundaries = np.flatnonzero(np.isin(tokens, (assistant_id, end_id, user_id, system_id)))
    start = None
    for position in boundaries:
        token = tokens[position]
        if token == assistant_id:
            start = position + 1
        elif token == end_id:
            if start is not None:
                result[start:position + 1] = 1
            start = None
        else:
            start = None
    return result


def prepare(directory):
    directory = Path(directory)
    tokenizer_path = directory / "tokenizer.json"
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    roles = [tokenizer.token_to_id(t) for t in ("<|assistant|>", "<|end|>", "<|user|>", "<|system|>")]
    manifest = {"tokenizer_sha256": file_hash(tokenizer_path), "partitions": {}}
    for name in ("train", "val"):
        path = directory / f"{name}.npy"
        tokens = np.load(path, mmap_mode="r")
        mask = assistant_mask(tokens, *roles)
        temporary = directory / f"{name}_assistant_mask.tmp"
        with temporary.open("wb") as handle:
            np.save(handle, mask)
        temporary.replace(directory / f"{name}_assistant_mask.npy")
        manifest["partitions"][name] = {"tokens_sha256": file_hash(path), "tokens": len(tokens), "assistant_targets": int(mask.sum())}
    temporary = directory / "supervision.tmp"
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(directory / "supervision.json")
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/combined")
    prepare(parser.parse_args().data)
