"""Inference directly from trained weights, with no canned response path."""
import argparse
import hashlib
import json
from pathlib import Path

from tokenizers import Tokenizer
import torch

from .data import SYSTEM
from .model import Astheral, Config


def build_prompt(tokenizer, messages, budget):
    """Keep system instructions and a suffix of complete exchanges within budget."""
    if not messages or len(messages) % 2 != 1:
        raise ValueError("Conversation must alternate user and assistant and end with user")
    end = tokenizer.token_to_id("<|end|>")
    newline = tokenizer.encode("\n").ids
    system = [tokenizer.token_to_id("<|system|>")] + tokenizer.encode(SYSTEM).ids + [end]
    tail = newline + [tokenizer.token_to_id("<|assistant|>")]
    encoded = []
    for index, message in enumerate(messages):
        role = "user" if index % 2 == 0 else "assistant"
        content = message.get("content")
        if message.get("role") != role or not isinstance(content, str) or not content.strip():
            raise ValueError("Messages must alternate nonempty user and assistant text")
        if any(marker in content for marker in ("<|user|>", "<|assistant|>", "<|system|>", "<|end|>", "<|pad|>")):
            raise ValueError("Reserved conversation delimiters in message")
        encoded.append(newline + [tokenizer.token_to_id(f"<|{role}|>")] + tokenizer.encode(content).ids + [end])
    removed = 0
    while len(encoded) > 1 and len(system) + sum(map(len, encoded)) + len(tail) > budget:
        encoded = encoded[2:]
        removed += 2
    ids = system + [token for message in encoded for token in message] + tail
    if len(ids) > budget:
        raise ValueError("Latest message exceeds the model's available context; shorten it")
    return ids, removed


class Assistant:
    def __init__(self, checkpoint=None, tokenizer="data/processed/tokenizer.json", threads=2, history_tokens=None):
        if checkpoint is None:
            selected = Path("runs/astheral-conversation/selected.pt")
            checkpoint = selected if selected.exists() else "runs/astheral/latest.pt"
        torch.set_num_threads(threads)
        state = torch.load(checkpoint, map_location="cpu", weights_only=True, mmap=True)
        if hashlib.sha256(Path(tokenizer).read_bytes()).hexdigest() != state["data"]["tokenizer_sha256"]:
            raise ValueError("Tokenizer does not match the checkpoint")
        # Meta initialization avoids allocating and randomly initializing another model.
        with torch.device("meta"):
            model = Astheral(Config(**state["config"]))
        # Nonpersistent rotary buffers need real CPU initialization.
        model.to_empty(device="cpu")
        model.load_state_dict(state["model"], assign=True)
        for block in model.blocks:
            dim = model.cfg.width // model.cfg.heads
            block.inv_freq = 1 / (10000 ** (torch.arange(0, dim, 2).float() / dim))
        self.model = model.eval()
        if history_tokens is not None and history_tokens < 32:
            raise ValueError("history_tokens must be at least 32")
        self.history_tokens = history_tokens
        self.tokenizer = Tokenizer.from_file(str(tokenizer))
        self.step = state["step"]
        self.tokens_seen = state["tokens_seen"]
        self.validation_loss = state["validation_loss"]
        del state

    @torch.inference_mode()
    def reply(self, messages, max_tokens=64, temperature=0, seed=42):
        if not 1 <= max_tokens <= 512 or not 0 <= temperature <= 2:
            raise ValueError("max_tokens must be 1..512; temperature must be 0..2")
        tokenizer = self.tokenizer
        budget = self.model.cfg.context - max_tokens
        if self.history_tokens is not None:
            budget = min(budget, self.history_tokens)
        ids, removed = build_prompt(tokenizer, messages, budget)
        generator = torch.Generator().manual_seed(seed)
        result = []
        end = tokenizer.token_to_id("<|end|>")
        cache = None
        with torch.autocast("cpu", dtype=torch.bfloat16):
            for _ in range(max_tokens):
                if cache is None or cache[0][0].shape[-2] >= self.model.cfg.context:
                    x, cache = torch.tensor([ids[-self.model.cfg.context:]], dtype=torch.long), None
                else:
                    x = torch.tensor([[ids[-1]]], dtype=torch.long)
                logits, cache = self.model.forward_cached(x, cache)
                scores = logits[0, -1].float()
                for marker in ("<|pad|>", "<|system|>", "<|user|>", "<|assistant|>"):
                    scores[tokenizer.token_to_id(marker)] = -torch.inf
                if temperature == 0:
                    token = int(scores.argmax())
                else:
                    scores /= temperature
                    cutoff = torch.topk(scores, min(50, scores.numel())).values[-1]
                    scores[scores < cutoff] = -torch.inf
                    token = int(torch.multinomial(scores.softmax(-1), 1, generator=generator))
                if token == end:
                    break
                ids.append(token)
                result.append(token)
        return {"response": tokenizer.decode(result, skip_special_tokens=True), "generated_tokens": len(result), "checkpoint_step": self.step, "tokens_seen": self.tokens_seen, "history_messages_dropped": removed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", help="Defaults to the reviewed conversation checkpoint when present")
    parser.add_argument("--tokenizer", default="data/processed/tokenizer.json")
    parser.add_argument("--prompt")
    parser.add_argument("--max-tokens", type=int, default=64)
    args = parser.parse_args()
    assistant = Assistant(args.checkpoint, args.tokenizer)
    if args.prompt:
        print(json.dumps(assistant.reply([{"role": "user", "content": args.prompt}], args.max_tokens)))
        return
    messages = []
    print(f"Astheral | checkpoint step {assistant.step} | /quit to exit")
    while True:
        try:
            prompt = input("You: ")
        except (EOFError, KeyboardInterrupt):
            break
        if prompt.strip() == "/quit":
            break
        messages.append({"role": "user", "content": prompt})
        answer = assistant.reply(messages, args.max_tokens)["response"]
        print(f"Astheral: {answer}")
        messages.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
