"""Real next-token training; default is continuous until interrupted."""
import argparse
from contextlib import nullcontext
from dataclasses import asdict
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import time

import numpy as np
import torch

from .model import Astheral, Config


def atomic_save(state, path):
    temporary = path.with_suffix(".tmp")
    with temporary.open("wb") as handle:
        torch.save(state, handle)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/processed")
    parser.add_argument("--output", default="runs/astheral")
    parser.add_argument("--steps", type=int, default=0, help="0 trains continuously")
    parser.add_argument("--sequence", type=int, default=128)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--accumulate", type=int, default=4)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--save-every", type=int, default=10)
    parser.add_argument("--eval-batches", type=int, default=4)
    parser.add_argument("--lr", type=float, default=0.0003)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--precision", choices=["bf16", "fp32"], default="bf16")
    args = parser.parse_args()
    if min(args.sequence, args.batch, args.accumulate, args.threads, args.save_every, args.eval_batches) <= 0 or args.steps < 0:
        parser.error("Counts must be positive; steps may be zero")
    torch.set_num_threads(args.threads)
    torch.manual_seed(args.seed)
    out, data = Path(args.output), Path(args.data)
    out.mkdir(parents=True, exist_ok=True)
    lock = (out / "train.lock").open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("A trainer already owns this run directory")
    lock.seek(0)
    lock.truncate()
    lock.write(str(os.getpid()))
    lock.flush()
    metadata = json.loads((data / "metadata.json").read_text())
    tokenizer_hash = hashlib.sha256((data / "tokenizer.json").read_bytes()).hexdigest()
    fingerprint = {"metadata": metadata, "tokenizer_sha256": tokenizer_hash}
    train = np.load(data / "train.npy", mmap_mode="r")
    val = np.load(data / "val.npy", mmap_mode="r")
    cfg = Config(vocab_size=metadata["vocab_size"])
    if args.sequence > cfg.context or min(len(train), len(val)) <= args.sequence:
        parser.error("Sequence length exceeds model or dataset capacity")
    model = Astheral(cfg).to(args.device)
    if model.parameter_count < 400_000_000:
        raise RuntimeError("Astheral must have at least 400 million parameters")
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.1, foreach=False)
    step, tokens_seen, checkpoint = 0, 0, out / "latest.pt"
    if checkpoint.exists():
        state = torch.load(checkpoint, map_location=args.device, weights_only=True, mmap=True)
        if state["config"] != asdict(cfg) or state["data"] != fingerprint:
            raise ValueError("Checkpoint architecture or training corpus/tokenizer mismatch")
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        step, tokens_seen = state["step"], state["tokens_seen"]
        torch.set_rng_state(state["rng"].cpu())
        del state
    # Validation sampling has a dedicated generator, never perturbing training RNG.
    validation_rng = torch.Generator().manual_seed(2026)
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def batch(array, generator=None):
        starts = torch.randint(len(array) - args.sequence, (args.batch,), generator=generator).tolist()
        x = np.stack([array[s:s + args.sequence].astype(np.int64) for s in starts])
        y = np.stack([array[s + 1:s + args.sequence + 1].astype(np.int64) for s in starts])
        return torch.from_numpy(x).to(args.device), torch.from_numpy(y).to(args.device)

    def autocast():
        return torch.autocast(args.device, dtype=torch.bfloat16) if args.precision == "bf16" else nullcontext()

    def evaluate():
        model.eval()
        validation_rng.manual_seed(2026)
        total = 0.0
        with torch.inference_mode(), autocast():
            for _ in range(args.eval_batches):
                _, loss = model(*batch(val, validation_rng))
                total += loss.item()
        model.train()
        return total / args.eval_batches

    def save(validation):
        atomic_save({"format": 1, "name": "Astheral", "config": asdict(cfg), "model": model.state_dict(), "optimizer": optimizer.state_dict(), "step": step, "tokens_seen": tokens_seen, "rng": torch.get_rng_state(), "data": fingerprint, "validation_loss": validation, "training_args": vars(args)}, checkpoint)
        temporary_status = out / "status.tmp"
        temporary_status.write_text(json.dumps({"step": step, "tokens_seen": tokens_seen, "parameters": model.parameter_count, "validation_loss": validation, "checkpoint": str(checkpoint), "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=2) + "\n")
        temporary_status.replace(out / "status.json")

    print(json.dumps({"event": "started", "pid": os.getpid(), "parameters": model.parameter_count, "step": step, "device": args.device, "precision": args.precision}), flush=True)
    baseline = evaluate()
    print(json.dumps({"event": "validation", "step": step, "loss": baseline}), flush=True)
    if not checkpoint.exists():
        save(baseline)
    metrics = (out / "metrics.jsonl").open("a", buffering=1)
    last_saved = step
    try:
        while not stopping and (args.steps == 0 or step < args.steps):
            started = time.monotonic()
            optimizer.zero_grad(set_to_none=True)
            total = 0.0
            for _ in range(args.accumulate):
                with autocast():
                    _, loss = model(*batch(train))
                if not torch.isfinite(loss):
                    raise FloatingPointError("Nonfinite training loss; previous checkpoint preserved")
                (loss / args.accumulate).backward()
                total += loss.item() / args.accumulate
            norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
            lr = args.lr * min(1.0, (step + 1) / 100)
            for group in optimizer.param_groups:
                group["lr"] = lr
            optimizer.step()
            step += 1
            tokens_seen += args.batch * args.sequence * args.accumulate
            record = {"step": step, "loss": total, "gradient_norm": float(norm), "lr": lr, "tokens_seen": tokens_seen, "seconds": time.monotonic() - started}
            print(json.dumps(record), flush=True)
            metrics.write(json.dumps(record) + "\n")
            if step == 1 or step % args.save_every == 0:
                validation = evaluate()
                print(json.dumps({"event": "validation", "step": step, "loss": validation}), flush=True)
                save(validation)
                last_saved = step
    finally:
        if step != last_saved:
            save(evaluate())
        metrics.close()
        print(json.dumps({"event": "stopped", "step": step, "tokens_seen": tokens_seen}), flush=True)


if __name__ == "__main__":
    main()
