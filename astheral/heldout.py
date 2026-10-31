"""Measure answers to existing held-out human instructions, excluding prompt-token loss."""
import hashlib
import json
import math
from pathlib import Path

import torch
from torch.nn import functional as F

from .data import format_record


def select_records(raw, per_category=1):
    categories = {}
    seen = set()
    for line in raw.splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        digest = hashlib.sha256(format_record(record).encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        if int(digest[:8], 16) % 50 != 0:
            continue
        categories.setdefault(record["category"], []).append((digest, record))
    return [(digest, record) for category in sorted(categories) for digest, record in sorted(categories[category], key=lambda item: item[0])[:per_category]]


def answer_batch(tokenizer, record, context):
    ids = tokenizer.encode(format_record(record)).ids
    answer_start = ids.index(tokenizer.token_to_id("<|assistant|>")) + 1
    answer_end = ids.index(tokenizer.token_to_id("<|end|>"), answer_start) + 1
    answer = ids[answer_start:answer_end][:min(128, context // 2)]
    prefix = ids[:answer_start]
    kept_prefix = prefix[-(context + 1 - len(answer)):]
    sequence = kept_prefix + answer
    targets = [-100] * (len(kept_prefix) - 1) + answer
    return torch.tensor([sequence[:-1]]), torch.tensor([targets]), len(prefix) > len(kept_prefix), answer_end - answer_start > len(answer)


@torch.inference_mode()
def assess_references(assistant, source="data/raw/databricks-dolly-15k.jsonl", per_category=1):
    source = Path(source)
    if not source.exists():
        return {"status": "unrun", "reason": "Original held-out dataset is unavailable"}
    raw = source.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != "e442d96b320010510c67a6cc0a86ea988a2a6f71c7570d1afbdf4fa631896e58":
        raise ValueError("Held-out dataset checksum mismatch")
    records = select_records(raw, per_category)
    if not records:
        raise ValueError("No held-out examples selected")
    results, total_nll, total_tokens, total_correct = [], 0.0, 0, 0
    with torch.autocast("cpu", dtype=torch.bfloat16):
        for digest, record in records:
            tokens, targets, truncated_prompt, truncated_answer = answer_batch(assistant.tokenizer, record, assistant.model.cfg.context)
            logits, _ = assistant.model(tokens)
            selected = targets != -100
            count = int(selected.sum())
            nll = float(F.cross_entropy(logits.float().reshape(-1, logits.shape[-1]), targets.reshape(-1), reduction="sum"))
            correct = int(((logits.argmax(-1) == targets) & selected).sum())
            total_nll += nll
            total_tokens += count
            total_correct += correct
            results.append({"record_sha256": digest, "category": record["category"], "answer_tokens": count, "answer_cross_entropy": nll / count, "answer_token_accuracy": correct / count, "prompt_truncated": truncated_prompt, "answer_truncated": truncated_answer})
    loss = total_nll / total_tokens
    return {"status": "completed", "examples": len(results), "answer_tokens": total_tokens, "answer_cross_entropy": loss, "answer_perplexity": math.exp(loss), "answer_token_accuracy": total_correct / total_tokens, "dataset_sha256": sha, "results": results, "interpretation": "Teacher-forced prediction of existing held-out human answers. Prompt/system tokens are excluded from loss; these measurements do not certify conversational ability."}
