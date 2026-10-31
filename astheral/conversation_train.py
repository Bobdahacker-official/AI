"""Real focused continuation with a cached, frozen prefix of Astheral."""
import argparse
import hashlib
from dataclasses import asdict
import fcntl
import json
from pathlib import Path
import os
import random
import signal
import time

import numpy as np
import torch
from torch.nn import functional as F

from .chat import Assistant, build_prompt
from .supervision import assistant_mask, file_hash
from .train import atomic_save
from .intents import LABELS, answer_intent


def examples(path, tokenizer, replay=(), context_replay=False):
    lesson = json.loads(Path(path).read_text())
    for extra in replay:
        lesson["train"].extend(json.loads(Path(extra).read_text())["train"])
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
                    prompt, _ = build_prompt(tokenizer, messages[:-1], 512 - 64)
                    answer = tokenizer.encode(messages[-1]["content"]).ids + [roles[1]]
                    if len(answer) > 64:
                        raise ValueError("Short conversation targets must fit the 64-token answer budget")
                    ids = np.asarray(prompt + answer)
                    mask = assistant_mask(ids, *roles)
                    targets = ids[1:].copy()
                    targets[mask[1:] == 0] = -100
                    # Each prefix learns only its final reply. Earlier replies remain context.
                    boundary = np.flatnonzero(ids == roles[0])[-1]
                    targets[:boundary] = -100
                    rows.append((torch.tensor(ids[:-1]), torch.tensor(targets)))
        splits[split] = rows
    if context_replay:
        rng = random.Random(819)
        # A first question and its answer are self-contained. Reuse that same
        # teacher target after other authored training conversations, supervising
        # only the final answer. Validation content never enters these contexts.
        roots = list({tuple(turns[:2]) for turns in lesson["train"]})
        roots.sort()
        for question, answer in roots:
            previous = rng.choice(lesson["train"])
            pairs = rng.randint(1, len(previous) // 2)
            turns = previous[:2 * pairs] + [question, answer]
            messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": text} for i, text in enumerate(turns)]
            prompt, _ = build_prompt(tokenizer, messages[:-1], 448)
            answer_ids = tokenizer.encode(answer).ids + [roles[1]]
            if len(answer_ids) > 64:
                raise ValueError("Context replay answer exceeds budget")
            ids = np.asarray(prompt + answer_ids)
            targets = ids[1:].copy()
            targets[:len(prompt) - 1] = -100
            splits["train"].append((torch.tensor(ids[:-1]), torch.tensor(targets)))
    return lesson, splits


def prefix(model, tokens, boundary):
    x = model.embedding(tokens)
    for block in model.blocks[:boundary]:
        x = block(x)
    return x


def suffix(model, hidden, boundary, return_hidden=False):
    for block in model.blocks[boundary:]:
        hidden = block(hidden)
    hidden = model.norm(hidden)
    logits = F.linear(hidden, model.embedding.weight)
    return (logits, hidden) if return_hidden else logits


def reply_loss(logits, targets, start_weight=1.0):
    losses = F.cross_entropy(logits.float().reshape(-1, logits.shape[-1]), targets.reshape(-1), reduction="none").reshape_as(targets)
    valid = targets != -100
    first = valid & (valid.cumsum(dim=1) <= 3)
    weights = valid.float() * torch.where(first, start_weight, 1.0)
    return (losses * weights).sum() / weights.sum().clamp_min(1)


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
    parser.add_argument("--replay", action="append", default=[], help="Retain earlier training dialogues; validation examples are not replayed")
    parser.add_argument("--context-replay", action="store_true", help="Teach self-contained questions after unrelated training histories")
    parser.add_argument("--reply-start-weight", type=float, default=1.0)
    parser.add_argument("--intent-weight", type=float, default=0.0)
    args = parser.parse_args()
    if min(args.layers, args.batch, args.save_every) < 1 or args.steps < 0 or args.lr <= 0 or args.reply_start_weight < 1 or args.intent_weight < 0:
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
    intent_head = torch.nn.Linear(model.cfg.width, len(LABELS)) if args.intent_weight else None
    if "intent_head" in state:
        if intent_head is None or state["intent_labels"] != list(LABELS):
            raise ValueError("Resume this checkpoint with the same auxiliary intent objective")
        intent_head.load_state_dict(state["intent_head"])
        optimizer.add_param_group({"params": list(intent_head.parameters())})
    lesson_sources = {path: file_hash(path) for path in [args.lessons, *args.replay]}
    fingerprint = file_hash(args.lessons) if not args.replay else hashlib.sha256(json.dumps(lesson_sources, sort_keys=True).encode()).hexdigest()
    if args.context_replay:
        fingerprint = hashlib.sha256((fingerprint + ":context-replay-v1").encode()).hexdigest()
    history = state.get("conversation_training", {}).get("curriculum_history", [])
    update = 0
    if "conversation_training" in state:
        details = state["conversation_training"]
        if (details["lessons_sha256"] != fingerprint and not args.allow_lesson_change) or details["layers"] != args.layers:
            raise ValueError("Conversation lesson or layer settings changed")
        if details["lessons_sha256"] != fingerprint:
            history = [*history, {"through_update": details["updates"], "lessons_sha256": details["lessons_sha256"]}]
        optimizer.load_state_dict(state["optimizer"])
        update = details["updates"]
        torch.set_rng_state(state["rng"])
    if intent_head is not None and "intent_head" not in state:
        optimizer.add_param_group({"params": list(intent_head.parameters())})
    for group in optimizer.param_groups:
        group["lr"] = args.lr
    source_step = state.get("conversation_training", {}).get("source_step", state["step"])
    base_tokens = state["tokens_seen"]
    source_data = state.get("source_data", state["data"])
    data = {"tokenizer_sha256": state["data"]["tokenizer_sha256"], "metadata": {"dataset": "Synthetic conversation teaching curriculum", "lessons_sha256": fingerprint, "sources_sha256": lesson_sources}}
    del state
    lesson, raw = examples(args.lessons, assistant.tokenizer, args.replay, args.context_replay)
    cache = {}
    intent_targets = {}
    for split, rows in raw.items():
        cache[split] = []
        intent_targets[split] = []
        for x, y in rows:
            if len(x) > model.cfg.context:
                raise ValueError("Lesson exceeds context")
            with torch.no_grad(), torch.autocast("cpu", dtype=torch.bfloat16):
                hidden = prefix(model, x[None], boundary).detach()
            cache[split].append((hidden, y))
            intent_targets[split].append(answer_intent(assistant.tokenizer.decode(y[y != -100].tolist(), skip_special_tokens=True)))
        print(json.dumps({"event": "cached", "split": split, "examples": len(rows)}), flush=True)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    tokens_seen = base_tokens
    # Anchor uniformly over examples, then sample within its length bucket.
    # Every example retains equal marginal probability, with less padding work.
    buckets = {}
    for i, (_, target) in enumerate(cache["train"]):
        buckets.setdefault(len(target) // 64, []).append(i)

    def loss_for(rows, categories=None):
        longest = max(len(y) for _, y in rows)
        h = torch.zeros(len(rows), longest, model.cfg.width)
        y = torch.full((len(rows), longest), -100, dtype=torch.long)
        for i, (hidden, target) in enumerate(rows):
            h[i, :len(target)] = hidden[0]
            y[i, :len(target)] = target
        with torch.autocast("cpu", dtype=torch.bfloat16):
            logits, hidden = suffix(model, h, boundary, return_hidden=True)
            loss = reply_loss(logits, y, args.reply_start_weight)
            if intent_head is not None and categories is not None:
                positions = (y != -100).int().argmax(dim=1)
                query_hidden = hidden[torch.arange(len(rows)), positions]
                loss = loss + args.intent_weight * F.cross_entropy(intent_head(query_hidden).float(), torch.tensor(categories))
            return loss

    def save():
        model.eval()
        with torch.no_grad():
            val = sum(float(loss_for([row])) for row in cache["validation"]) / len(cache["validation"])
        assistant.step = source_step + update
        assistant.tokens_seen = tokens_seen
        assistant.validation_loss = val
        details = {"source_step": source_step, "updates": update, "layers": args.layers, "lessons_sha256": fingerprint, "teacher_provenance": lesson["provenance"], "train_examples": len(cache["train"]), "validation_examples": len(cache["validation"]), "curriculum_history": history}
        saved = {"name": "Astheral", "config": asdict(model.cfg), "model": model.state_dict(), "optimizer": optimizer.state_dict(), "step": source_step + update, "tokens_seen": tokens_seen, "rng": torch.get_rng_state(), "data": data, "source_data": source_data, "validation_loss": val, "conversation_training": details, "training_args": vars(args)}
        if intent_head is not None:
            saved.update(intent_head=intent_head.state_dict(), intent_labels=list(LABELS))
        atomic_save(saved, checkpoint)
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
            anchor = int(torch.randint(len(cache["train"]), (1,)))
            bucket = buckets[len(cache["train"][anchor][1]) // 64]
            indices = [anchor] + [bucket[i] for i in torch.randint(len(bucket), (args.batch - 1,)).tolist()]
            rows = [cache["train"][i] for i in indices]
            optimizer.zero_grad(set_to_none=True)
            loss = loss_for(rows, [intent_targets["train"][i] for i in indices])
            if not torch.isfinite(loss):
                raise FloatingPointError("Nonfinite loss")
            loss.backward()
            parameters = [p for group in optimizer.param_groups for p in group["params"]]
            torch.nn.utils.clip_grad_norm_(parameters, 1.0, error_if_nonfinite=True)
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
