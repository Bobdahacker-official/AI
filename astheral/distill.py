"""Offline response distillation from human-preferred Anthropic 52B outputs."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import shutil

import numpy as np
from tokenizers import Tokenizer

from .dialogue import REVISION, parse_thread, root_key, serialize
from .evaluate import CASES
from .supervision import file_hash, prepare as prepare_masks

SOURCES = {
    "train": "518a5bf288456fc9f3b7c980c54116fba0c52f274d3f4d344675d83e4058f6f4",
    "test": "8be3fc1a13b27901631696f2be6f184c799f1baeaf145f53ac5db24960adc37b",
}


def prepare(raw, output, max_tokens=257):
    from .data import format_record
    raw, output = Path(raw), Path(output)
    if not 3 <= max_tokens <= 513:
        raise ValueError("Complete examples must fit the model context")
    for split, digest in SOURCES.items():
        if file_hash(raw / "helpful-base" / f"{split}.jsonl.gz") != digest:
            raise ValueError("Teacher source checksum mismatch")
    tokenizer_path = Path("data/processed/tokenizer.json")
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    rows, roots, counts = {}, {}, Counter()
    for split in SOURCES:
        rows[split], roots[split] = [], set()
        with gzip.open(raw / "helpful-base" / f"{split}.jsonl.gz", "rt") as handle:
            for line in handle:
                try:
                    messages = parse_thread(json.loads(line)["chosen"])
                except (ValueError, KeyError):
                    counts["malformed"] += 1
                    continue
                key = root_key(messages[0]["content"])
                roots[split].add(key)
                rows[split].append((key, messages))
    protected = roots["test"] | {root_key(c["messages"][0]["content"]) for c in CASES}
    protected.add(root_key("Hello"))
    # Old Dolly validation questions remain excluded from this phase's training.
    for line in Path("data/raw/databricks-dolly-15k.jsonl").read_text().splitlines():
        row = json.loads(line)
        import hashlib
        digest = hashlib.sha256(format_record(row).encode()).hexdigest()
        if int(digest[:8], 16) % 50 == 0:
            question = row["instruction"].strip()
            if row.get("context", "").strip():
                question += "\n\n" + row["context"].strip()
            protected.add(root_key(question))
    # The old broad phase saw helpful-base training roots, so remove those roots
    # from validation too. This is not a newly unseen test set for the checkpoint.
    output.mkdir(parents=True, exist_ok=True)
    metadata = {
        "dataset": "Anthropic 52B helpful-base chosen short complete conversations",
        "vocab_size": tokenizer.get_vocab_size(), "revision": REVISION,
        "sources_sha256": SOURCES, "max_example_tokens": max_tokens,
        "teacher": "Anthropic context-distilled 52B (published HH-RLHF helpful-base)",
        "selection": "Human-preferred chosen response; correctness not guaranteed",
        "mode": "offline hard-label distillation; no teacher weights or API",
        "validation_note": "Official test split; may have been seen in earlier validation, never optimized in this phase",
    }
    seen, selected_roots = set(), {}
    for source_split, target in (("train", "train"), ("test", "val")):
        flat, ranges, selected_roots[target] = [], [], set()
        for key, messages in rows[source_split]:
            if (source_split == "train" and key in protected) or (source_split == "test" and key in roots["train"]):
                counts["heldout_root_collision"] += 1
                continue
            if any(word in m["content"].casefold() for m in messages if m["role"] == "assistant" for word in ("anthropic", "claude")):
                counts["conflicting_identity"] += 1
                continue
            text = serialize(messages)
            if text in seen:
                counts["duplicate"] += 1
                continue
            ids = tokenizer.encode(text).ids
            if len(ids) > max_tokens:
                counts["long_examples_excluded_not_truncated"] += 1
                continue
            seen.add(text)
            ranges.append((len(flat), len(flat) + len(ids)))
            flat.extend(ids)
            selected_roots[target].add(key)
        if not ranges:
            raise ValueError("No complete teacher examples selected")
        for name, array in ((target, np.asarray(flat, dtype=np.uint16)), (target + "_ranges", np.asarray(ranges, dtype=np.int64))):
            temporary = output / f"{name}.tmp"
            with temporary.open("wb") as handle:
                np.save(handle, array)
            temporary.replace(output / f"{name}.npy")
        metadata[target + "_records"] = len(ranges)
        metadata[target + "_tokens"] = len(flat)
        metadata[target + "_ranges_sha256"] = file_hash(output / f"{target}_ranges.npy")
    assert not selected_roots["train"] & selected_roots["val"]
    metadata["filters"] = dict(counts)
    shutil.copyfile(tokenizer_path, output / "tokenizer.json")
    prepare_masks(output)
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="data/raw/hh")
    parser.add_argument("--output", default="data/teacher")
    parser.add_argument("--max-tokens", type=int, default=257)
    args = parser.parse_args()
    prepare(args.raw, args.output, args.max_tokens)
