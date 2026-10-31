"""Download and prepare an existing broad assistant corpus; retain Astheral's tokenizer."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import subprocess

import numpy as np
from tokenizers import Tokenizer

from .data import SPECIAL, SYSTEM, format_record
from .supervision import file_hash

REVISION = "c72f5cee8eb7b4d2ea5617657f4430d5e333af07"
SUBSETS = ("helpful-base", "helpful-online", "helpful-rejection-sampled")
MARKER = re.compile(r"(?:\A|\n\n)(Human|Assistant):[ \t]?")


def parse_thread(text):
    markers = list(MARKER.finditer(text))
    if not markers or text[:markers[0].start()].strip():
        raise ValueError("Missing conversation role markers")
    messages = []
    for index, marker in enumerate(markers):
        role = "user" if marker.group(1) == "Human" else "assistant"
        expected = "user" if index % 2 == 0 else "assistant"
        body = text[marker.end():markers[index + 1].start() if index + 1 < len(markers) else len(text)].strip()
        if role != expected or not body or any(token in body for token in SPECIAL):
            raise ValueError("Malformed or ambiguous conversation")
        messages.append({"role": role, "content": body})
    if messages[-1]["role"] != "assistant":
        raise ValueError("Preferred conversation does not end in an answer")
    return messages


def root_key(text):
    normalized = " ".join(text.split()).casefold()
    return hashlib.sha256(normalized.encode()).hexdigest()


def serialize(messages):
    return f"<|system|>{SYSTEM}<|end|>\n" + "\n".join(f"<|{m['role']}|>{m['content']}<|end|>" for m in messages) + "\n"


def download(raw):
    manifest = {}
    raw.mkdir(parents=True, exist_ok=True)
    for subset in SUBSETS:
        for split in ("train", "test"):
            relative = f"{subset}/{split}.jsonl.gz"
            pointer_url = f"https://raw.githubusercontent.com/anthropics/hh-rlhf/{REVISION}/{relative}"
            pointer = subprocess.check_output(["curl", "--fail", "--silent", "--show-error", "--location", "--max-time", "60", pointer_url], text=True)
            match = re.fullmatch(r"version https://git-lfs.github.com/spec/v1\noid sha256:([0-9a-f]{64})\nsize ([0-9]+)\n?", pointer)
            if match is None:
                raise ValueError("Publisher's pinned LFS pointer is invalid")
            expected, size = match.group(1), int(match.group(2))
            path = raw / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() or path.stat().st_size != size or file_hash(path) != expected:
                temporary = path.with_suffix(".download")
                url = f"https://github.com/anthropics/hh-rlhf/raw/{REVISION}/{relative}"
                subprocess.run(["curl", "--fail", "--silent", "--show-error", "--location", "--retry", "2", "--max-time", "180", url, "-o", str(temporary)], check=True)
                if temporary.stat().st_size != size or file_hash(temporary) != expected:
                    raise ValueError(f"Dataset object failed verification: {relative}")
                temporary.replace(path)
            # Opening a real gzip file rejects a pointer mistakenly substituted for data.
            with gzip.open(path, "rt") as handle:
                first = json.loads(next(handle))
                if not isinstance(first.get("chosen"), str):
                    raise ValueError("Unexpected preference record schema")
            manifest[relative] = {"sha256": expected, "bytes": size}
            print(json.dumps({"event": "verified_dataset", "file": relative, **manifest[relative]}), flush=True)
    (raw / "manifest.json").write_text(json.dumps({"revision": REVISION, "files": manifest}, indent=2) + "\n")
    license_url = f"https://raw.githubusercontent.com/anthropics/hh-rlhf/{REVISION}/LICENSE"
    license_text = subprocess.check_output(["curl", "--fail", "--silent", "--show-error", "--location", "--max-time", "60", license_url])
    (raw / "LICENSE").write_bytes(license_text)


def hh_records(raw, split, counters):
    for subset in SUBSETS:
        relative = f"{subset}/{split}.jsonl.gz"
        with gzip.open(raw / relative, "rt") as handle:
            for line in handle:
                record = json.loads(line)
                counters[f"{split}_source_records"] += 1
                try:
                    messages = parse_thread(record["chosen"])
                except ValueError:
                    counters[f"{split}_malformed"] += 1
                    continue
                # Keep existing text intact; exclude conflicting creator/identity claims.
                if re.search(r"\banthropic\b|\bclaude\b", record["chosen"], flags=re.I):
                    counters[f"{split}_identity_conflict"] += 1
                    continue
                yield root_key(messages[0]["content"]), serialize(messages)


def pack(texts, tokenizer, output, name):
    binary = output / f"{name}.tokens.tmp"
    count = 0
    with binary.open("wb") as handle:
        for start in range(0, len(texts), 64):
            encoded = tokenizer.encode_batch(texts[start:start + 64])
            flat = np.asarray([token for item in encoded for token in item.ids], dtype=np.uint16)
            handle.write(flat.tobytes())
            count += len(flat)
    temporary = output / f"{name}.npy.tmp"
    packed = np.lib.format.open_memmap(temporary, mode="w+", dtype=np.uint16, shape=(count,))
    source = np.memmap(binary, mode="r", dtype=np.uint16)
    for start in range(0, count, 1024 * 1024):
        packed[start:start + 1024 * 1024] = source[start:start + 1024 * 1024]
    packed.flush()
    del packed, source
    temporary.replace(output / f"{name}.npy")
    binary.unlink()
    return count


def prepare(raw, output):
    from .corpus import format_dialogue
    from .evaluate import CASES

    manifest = json.loads((raw / "manifest.json").read_text())
    if manifest["revision"] != REVISION:
        raise ValueError("Unexpected HH dataset revision")
    for relative, expected in manifest["files"].items():
        if file_hash(raw / relative) != expected["sha256"]:
            raise ValueError(f"Source object changed: {relative}")
    counters = Counter()
    partitions = {"train": [], "val": []}
    roots = {"train": set(), "val": set()}
    previous_train_roots = set()
    dolly = []
    seen = set()
    for line in Path("data/raw/databricks-dolly-15k.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        text = format_record(record)
        digest = hashlib.sha256(text.encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        question = record["instruction"].strip() + ("\n\n" + record["context"].strip() if record.get("context", "").strip() else "")
        key = root_key(question)
        split = "val" if int(digest[:8], 16) % 50 == 0 else "train"
        dolly.append((key, text, split))
        if split == "train":
            previous_train_roots.add(key)
    for filename in ("self-dialogs.json", "woz-dialogs.json"):
        for dialogue in json.loads((Path("data/raw/taskmaster") / filename).read_text()):
            if any(u["speaker"] not in ("USER", "ASSISTANT") for u in dialogue["utterances"]):
                continue
            digest = hashlib.sha256(format_dialogue(dialogue).encode()).hexdigest()
            if int(digest[:8], 16) % 50 != 0:
                first = next((u["text"] for u in dialogue["utterances"] if u["speaker"] == "USER"), None)
                if first:
                    previous_train_roots.add(root_key(first))
    test_records = list(hh_records(raw, "test", counters))
    test_roots = {key for key, _ in test_records}
    evaluation_roots = {root_key(case["messages"][0]["content"]) for case in CASES}
    dolly_val_roots = {key for key, _, split in dolly if split == "val"}
    protected = test_roots | evaluation_roots | dolly_val_roots
    seen.clear()

    def add(split, key, text):
        digest = hashlib.sha256(text.encode()).hexdigest()
        if digest in seen:
            counters["duplicate_records"] += 1
            return False
        seen.add(digest)
        partitions[split].append(text)
        roots[split].add(key)
        return True

    for key, text, split in dolly:
        if split == "val":
            add("val", key, text)
    for key, text in test_records:
        if key in previous_train_roots:
            counters["test_roots_seen_in_previous_training"] += 1
            continue
        add("val", key, text)
    for key, text, split in dolly:
        if split == "train":
            if key in protected:
                counters["dolly_train_heldout_root_collision"] += 1
            elif add("train", key, text):
                counters["dolly_train_records"] += 1
    for key, text in hh_records(raw, "train", counters):
        if key in protected:
            counters["hh_train_heldout_root_collision"] += 1
        elif add("train", key, text):
            counters["hh_train_records"] += 1
    if roots["train"] & roots["val"]:
        raise ValueError("Conversation root leakage across training and validation")
    output.mkdir(parents=True, exist_ok=True)
    tokenizer_path = Path("data/processed/tokenizer.json")
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    if tokenizer.get_vocab_size() != 8192:
        raise ValueError("Astheral's original tokenizer must be retained")
    metadata = {"dataset": "Dolly-15k + HH-RLHF helpful chosen conversations", "vocab_size": 8192, "hh_revision": REVISION, "hh_sources": manifest["files"], "filters": dict(counters), "shared_train_val_roots": 0, "tokenizer_sha256": file_hash(tokenizer_path), "dolly_sha256": file_hash("data/raw/databricks-dolly-15k.jsonl"), "hh_response_provenance": "Previously published model-generated responses ranked by human annotators; no teacher API or pretrained weights used here"}
    for name, texts in partitions.items():
        random.Random(2026).shuffle(texts)
        metadata[f"{name}_records"] = len(texts)
        metadata[f"{name}_tokens"] = pack(texts, tokenizer, output, name)
    shutil.copyfile(tokenizer_path, output / "tokenizer.tmp")
    (output / "tokenizer.tmp").replace(output / "tokenizer.json")
    (output / "metadata.tmp").write_text(json.dumps(metadata, indent=2) + "\n")
    (output / "metadata.tmp").replace(output / "metadata.json")
    print(json.dumps(metadata, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", default="data/raw/hh")
    parser.add_argument("--output", default="data/general-dialogue")
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    raw = Path(args.raw)
    if not args.prepare_only:
        download(raw)
    if not args.download_only:
        prepare(raw, Path(args.output))


if __name__ == "__main__":
    main()
