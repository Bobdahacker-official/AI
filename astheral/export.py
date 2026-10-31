"""Export real trained model tensors without optimizer state."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import torch
from .train import atomic_save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default="runs/astheral/latest.pt")
    parser.add_argument("--tokenizer", default="data/processed/tokenizer.json")
    parser.add_argument("--output", default="exports/astheral")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True, mmap=True)
    if state["step"] < 1:
        raise ValueError("Refusing to label untrained initialization as a trained export")
    tokenizer = Path(args.tokenizer)
    if hashlib.sha256(tokenizer.read_bytes()).hexdigest() != state["data"]["tokenizer_sha256"]:
        raise ValueError("Tokenizer mismatch")
    exported = {key: value for key, value in state.items() if key not in ("optimizer", "rng")}
    weights = output / "weights.pt"
    atomic_save(exported, weights)
    shutil.copyfile(tokenizer, output / "tokenizer.json")
    digest = hashlib.sha256()
    with weights.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    manifest = {"model": "Astheral", "parameters": sum(t.numel() for t in state["model"].values()), "step": state["step"], "tokens_seen": state["tokens_seen"], "validation_loss": state["validation_loss"], "weights_sha256": digest.hexdigest(), "tokenizer_sha256": state["data"]["tokenizer_sha256"], "dataset": state["data"]["metadata"], "base_model": None, "initialization": "random", "conversational_quality": "Not established; early experimental checkpoint"}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
