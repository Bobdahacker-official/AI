"""Real focused continuation with a cached, frozen prefix of Astheral."""
import argparse
from dataclasses import asdict
import fcntl
import json
from pathlib import Path
import os
import signal
import time

import numpy as np
import torch
from torch.nn import functional as F

from .chat import Assistant
from .dialogue import serialize
from .supervision import assistant_mask, file_hash
from .train import atomic_save


def examples(path, tokenizer):
    lesson = json.loads(Path(path).read_text())
    roles = [tokenizer.token_to_id(t) for t in ("<|assistant|>", "<|end|>", "<|user|>", "<|system|>")]
    splits = {}
    for split in ("train", "validation"):
        rows = []
        for turns in lesson[split]:
            if not turns or len(turns) % 2 or any(not isinstance(t, str) or not t.strip() for t in turns):
                raise ValueError("Lessons need alternating nonempty user/assistant turns")
            messages = []
            for i, text in enumerate(turns):
                messages.append({"role": "user" if i % 2 == 0 else "assistant", "content": text})
                if i % 2:
                    ids = np.asarray(tokenizer.encode(serialize(messages)).ids)
                    mask = assistant_mask(ids, *roles)
                    targets = ids[1:].copy()
                    targets[mask[1:] == 0] = -100
                    # Each prefix learns only its final reply. Earlier replies remain context.
                    boundary = np.flatnonzero(ids == roles[0])[-1]
                    targets[:boundary] = -100
                    rows.append((torch.tensor(ids[:-1]), torch.tensor(targets)))
        splits[split] = rows
    return lesson, splits


def prefix(model, tokens, boundary):
    x = model.embedding(tokens)
    for block in model.blocks[:boundary]:
        x = block(x)
    return x


def suffix(model, hidden, boundary):
    for block in model.blocks[boundary:]:
        hidden = block(hidden)
    return F.linear(model.norm(hidden), model.embedding.weight)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="runs/astheral/latest.pt")
    parser.add_argument("--output", default="runs/astheral-conversation")
    parser.add_argument("--lessons", default="astheral/conversation_lessons.json")
    parser.add_argument("--layers", type=int, default=4)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--steps", type=int, default=0, help="0 continues until interrupted")
    parser.add_argument("--save-every", type=int, default=50)
    parser.add_argument("--allow-lesson-change", action="store_true")
    args = parser.parse_args()
    if min(args.layers, args.batch, args.save_every) < 1 or args.steps < 0 or args.lr <= 0:
        parser.error("Invalid training counts or rate")
    torch.set_num_threads(4)
    torch.manual_seed(102)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    lock = (out / "train.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    lock.seek(0); lock.truncate(); lock.write(str(os.getpid())); lock.flush()
    checkpoint = out / "latest.pt"
    source = checkpoint if checkpoint.exists() else Path(args.source)
    assistant = Assistant(source, threads=4)
    model = assistant.model
    boundary = len(model.blocks) - args.layers
    if boundary < 1:
        parser.error("Retain at least one frozen block")
    for p in model.parameters():
        p.requires_grad_(False)
    for block in model.blocks[boundary:]:
        block.requires_grad_(True)
    model.norm.requires_grad_(True)
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=args.lr, weight_decay=0.01, foreach=False)
    state = torch.load(source, weights_only=True, mmap=True)
    fingerprint = file_hash(args.lessons)
    update = 0
    if "conversation_training" in state:
        details = state["conversation_training"]
        if (details["lessons_sha256"] != fingerprint and not args.allow_lesson_change) or details["layers"] != args.layers:
            raise ValueError("Conversation lesson or layer settings changed")
        optimizer.load_state_dict(state["optimizer"])
        update = details["updates"]
        torch.set_rng_state(state["rng"])
    for group in optimizer.param_groups:
        group["lr"] = args.lr
    source_step = state.get("conversation_training", {}).get("source_step", state["step"])
    base_tokens = state["tokens_seen"]
    data = state["data"]
    del state
    lesson, raw = examples(args.lessons, assistant.tokenizer)
    cache = {}
    for split, rows in raw.items():
        cache[split] = []
        for x, y in rows:
            if len(x) > model.cfg.context:
                raise ValueError("Lesson exceeds context")
            with torch.no_grad(), torch.autocast("cpu", dtype=torch.bfloat16):
                hidden = prefix(model, x[None], boundary).detach()
            cache[split].append((hidden, y))
        print(json.dumps({"event": "cached", "split": split, "examples": len(rows)}), flush=True)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    tokens_seen = base_tokens

    def loss_for(rows):
        longest = max(len(y) for _, y in rows)
        h = torch.zeros(len(rows), longest, model.cfg.width)
        y = torch.full((len(rows), longest), -100, dtype=torch.long)
        for i, (hidden, target) in enumerate(rows):
            h[i, :len(target)] = hidden[0]
            y[i, :len(target)] = target
        with torch.autocast("cpu", dtype=torch.bfloat16):
            logits = suffix(model, h, boundary)
            return F.cross_entropy(logits.float().reshape(-1, model.cfg.vocab_size), y.reshape(-1))

    def save():
        model.eval()
        with torch.no_grad():
            val = sum(float(loss_for([row])) for row in cache["validation"]) / len(cache["validation"])
        details = {"source_step": source_step, "updates": update, "layers": args.layers, "lessons_sha256": fingerprint, "teacher_provenance": lesson["provenance"], "train_examples": len(cache["train"]), "validation_examples": len(cache["validation"])}
        atomic_save({"name": "Astheral", "config": asdict(model.cfg), "model": model.state_dict(), "optimizer": optimizer.state_dict(), "step": source_step + update, "tokens_seen": tokens_seen, "rng": torch.get_rng_state(), "data": data, "validation_loss": val, "conversation_training": details, "training_args": vars(args)}, checkpoint)
        reports = []
        for prompts in (["Hello", "What is your name?"], ["Hi Astheral!", "I want to discuss cooking."]):
            messages = []
            for prompt in prompts:
                messages.append({"role": "user", "content": prompt})
                answer = assistant.reply(messages, max_tokens=28, temperature=0)["response"]
                messages.append({"role": "assistant", "content": answer})
            reports.append(messages)
        status = {"updates": update, "step": source_step + update, "validation_loss": val, "trainable_parameters": sum(p.numel() for p in model.parameters() if p.requires_grad), "conversations": reports, "checkpoint": str(checkpoint), "trainer": "conversation_train"}
        (out / "status.json").write_text(json.dumps(status, indent=2) + "\n")
        print(json.dumps({"event": "assessment", **status}), flush=True)
        model.train()

    save()
    try:
        while not stopping and (not args.steps or update < args.steps):
            start = time.monotonic()
            indices = torch.randint(len(cache["train"]), (args.batch,)).tolist()
            rows = [cache["train"][i] for i in indices]
            optimizer.zero_grad(set_to_none=True)
            loss = loss_for(rows)
            if not torch.isfinite(loss):
                raise FloatingPointError("Nonfinite loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0, error_if_nonfinite=True)
            optimizer.step()
            update += 1
            tokens_seen += sum(len(y) for _, y in rows)
            print(json.dumps({"event": "update", "update": update, "loss": float(loss.detach()), "seconds": time.monotonic() - start}), flush=True)
            if update % args.save_every == 0:
                save()
    finally:
        save()


if __name__ == "__main__":
    main()
