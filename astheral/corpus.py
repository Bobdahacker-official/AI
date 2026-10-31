"""Add Google's existing human-written Taskmaster-1 conversations without changing token IDs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from tokenizers import Tokenizer

from .data import SYSTEM, format_record

REVISION = "d92cb6af3005f1dc09c39e75e7daf4a04905e00b"
FILES = {
    "self-dialogs.json": "1e590ed0ccee279e40c2fb9e083d3b9417477c6bfe35ce5b2277167698dd858d",
    "woz-dialogs.json": "cd3bc4e968487315d412c044d30af2bf0a4b33c3ef8b74c589f1e1fa832bf72f",
}


def format_dialogue(dialogue):
    text = f"<|system|>{SYSTEM}<|end|>"
    for utterance in dialogue["utterances"]:
        speaker = utterance["speaker"].lower()
        if speaker not in ("user", "assistant"):
            raise ValueError(f"Unknown Taskmaster speaker {speaker}")
        text += f"\n<|{speaker}|>{utterance['text'].strip()}<|end|>"
    return text + "\n"


def prepare(taskmaster_root=None, destination="data/combined"):
    raw = Path("data/raw/taskmaster")
    raw.mkdir(parents=True, exist_ok=True)
    for filename, checksum in FILES.items():
        target = raw / filename
        if taskmaster_root:
            shutil.copyfile(Path(taskmaster_root) / "TM-1-2019" / filename, target)
        elif not target.exists():
            url = f"https://raw.githubusercontent.com/google-research-datasets/Taskmaster/{REVISION}/TM-1-2019/{filename}"
            subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error", "--max-time", "180", url, "-o", str(target)], check=True)
        if hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Unverified source file: {target}")
    output = Path(destination)
    output.mkdir(parents=True, exist_ok=True)
    tokenizer_path = Path("data/processed/tokenizer.json")
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    # Retain the original Dolly split and vocabulary for checkpoint compatibility.
    partitions = {"train": [], "val": []}
    seen = set()
    records = [json.loads(line) for line in Path("data/raw/databricks-dolly-15k.jsonl").read_text().splitlines() if line.strip()]
    for record in records:
        text = format_record(record)
        digest = hashlib.sha256(text.encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        partitions["val" if int(digest[:8], 16) % 50 == 0 else "train"].append(text)
    counts = {}
    for filename in FILES:
        dialogues = json.loads((raw / filename).read_text())
        count = {"train": 0, "val": 0, "duplicates": 0, "ambiguous_speaker": 0}
        for dialogue in dialogues:
            if any(u["speaker"].lower() not in ("user", "assistant") for u in dialogue["utterances"]):
                count["ambiguous_speaker"] += 1
                continue
            text = format_dialogue(dialogue)
            digest = hashlib.sha256(text.encode()).hexdigest()
            if digest in seen:
                count["duplicates"] += 1
                continue
            seen.add(digest)
            # All turns from a conversation remain in exactly one partition.
            partition = "val" if int(digest[:8], 16) % 50 == 0 else "train"
            partitions[partition].append(text)
            count[partition] += 1
        counts[filename] = count
    metadata = {"dataset": "Dolly-15k + Google Taskmaster-1", "vocab_size": tokenizer.get_vocab_size(), "taskmaster_revision": REVISION, "taskmaster_sha256": FILES, "taskmaster_records": counts, "dolly_sha256": hashlib.sha256(Path("data/raw/databricks-dolly-15k.jsonl").read_bytes()).hexdigest()}
    for name, texts in partitions.items():
        ids = []
        for start in range(0, len(texts), 256):
            ids.extend(token for encoded in tokenizer.encode_batch(texts[start:start + 256]) for token in encoded.ids)
        temporary = output / f"{name}.npy.tmp"
        with temporary.open("wb") as handle:
            np.save(handle, np.asarray(ids, dtype=np.uint16))
        temporary.replace(output / f"{name}.npy")
        metadata[f"{name}_records"] = len(texts)
        metadata[f"{name}_tokens"] = len(ids)
    shutil.copyfile(tokenizer_path, output / "tokenizer.tmp")
    (output / "tokenizer.tmp").replace(output / "tokenizer.json")
    (output / "metadata.tmp").write_text(json.dumps(metadata, indent=2) + "\n")
    (output / "metadata.tmp").replace(output / "metadata.json")
    print(json.dumps(metadata, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--taskmaster-root")
    parser.add_argument("--output", default="data/combined")
    args = parser.parse_args()
    prepare(args.taskmaster_root, args.output)
