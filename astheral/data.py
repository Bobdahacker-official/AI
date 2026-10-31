"""Train a byte-level BPE tokenizer and tokenize existing human-authored data."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers

SYSTEM = "You are Astheral, a friendly, helpful and honest AI assistant."
SPECIAL = ["<|pad|>", "<|system|>", "<|user|>", "<|assistant|>", "<|end|>"]


def format_record(record):
    context = record.get("context", "").strip()
    question = record["instruction"].strip() + ("\n\n" + context if context else "")
    return f"<|system|>{SYSTEM}<|end|>\n<|user|>{question}<|end|>\n<|assistant|>{record['response'].strip()}<|end|>\n"


def prepare(source, destination, vocab_size=8192):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    source = Path(source)
    raw = source.read_bytes()
    records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if len(records) < 100:
        raise ValueError("Dataset must contain at least 100 existing records")
    # Entire records are split BEFORE tokenizer fitting or packing, avoiding leakage.
    train, val, seen = [], [], set()
    for record in records:
        text = format_record(record)
        digest = hashlib.sha256(text.encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        (val if int(digest[:8], 16) % 50 == 0 else train).append(text)
    if not train or not val:
        raise ValueError("The deterministic split is empty")
    tokenizer = Tokenizer(models.BPE(unk_token="<|pad|>"))
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tokenizer.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(vocab_size=vocab_size, special_tokens=SPECIAL, initial_alphabet=pre_tokenizers.ByteLevel.alphabet())
    tokenizer.train_from_iterator(train, trainer=trainer)
    if tokenizer.get_vocab_size() != vocab_size:
        raise ValueError("Dataset could not fill requested vocabulary")
    tokenizer.save(str(destination / "tokenizer.json"))
    meta = {"dataset": "databricks/databricks-dolly-15k", "sha256": hashlib.sha256(raw).hexdigest(), "vocab_size": vocab_size, "train_records": len(train), "val_records": len(val), "duplicates_removed": len(records) - len(seen)}
    for name, texts in (("train", train), ("val", val)):
        ids = [token for encoded in tokenizer.encode_batch(texts) for token in encoded.ids]
        np.save(destination / f"{name}.npy", np.asarray(ids, dtype=np.uint16 if vocab_size <= 65536 else np.uint32))
        meta[f"{name}_tokens"] = len(ids)
    (destination / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="data/raw/databricks-dolly-15k.jsonl")
    parser.add_argument("--output", default="data/processed")
    args = parser.parse_args()
    prepare(args.source, args.output)
