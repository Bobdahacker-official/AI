"""Inference directly from trained weights, with no canned response path."""
import argparse
import hashlib
import json
from pathlib import Path

from tokenizers import Tokenizer
import torch

from .data import SYSTEM
from .model import Astheral, Config


class Assistant:
    def __init__(self, checkpoint="runs/astheral/latest.pt", tokenizer="data/processed/tokenizer.json", threads=2):
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
        self.tokenizer = Tokenizer.from_file(str(tokenizer))
        self.step = state["step"]
        self.tokens_seen = state["tokens_seen"]
        self.validation_loss = state["validation_loss"]
        del state

    @torch.inference_mode()
    def reply(self, messages, max_tokens=64, temperature=0.8, seed=42):
        if not 1 <= max_tokens <= 512 or not 0 <= temperature <= 2:
            raise ValueError("max_tokens must be 1..512; temperature must be 0..2")
        if not messages or messages[-1].get("role") != "user":
            raise ValueError("Conversation must end with a user message")
        tokenizer = self.tokenizer
        ids = [tokenizer.token_to_id("<|system|>")] + tokenizer.encode(SYSTEM).ids + [tokenizer.token_to_id("<|end|>")]
        # Encode user content separately: text cannot insert structural role tokens.
        for message in messages:
            role = message.get("role")
            content = message.get("content")
            if role not in ("user", "assistant") or not isinstance(content, str):
                raise ValueError("Messages need a user/assistant role and string content")
            # Disallow literal control delimiters to preserve the serialization grammar.
            if any(marker in content for marker in ("<|user|>", "<|assistant|>", "<|system|>", "<|end|>", "<|pad|>")):
                raise ValueError("Reserved conversation delimiters in message")
            ids += tokenizer.encode("\n").ids + [tokenizer.token_to_id(f"<|{role}|>")]
            ids += tokenizer.encode(content).ids + [tokenizer.token_to_id("<|end|>")]
        ids += tokenizer.encode("\n").ids + [tokenizer.token_to_id("<|assistant|>")]
        generator = torch.Generator().manual_seed(seed)
        result = []
        end = tokenizer.token_to_id("<|end|>")
        for _ in range(max_tokens):
            x = torch.tensor([ids[-self.model.cfg.context:]], dtype=torch.long)
            with torch.autocast("cpu", dtype=torch.bfloat16):
                logits, _ = self.model(x)
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
        return {"response": tokenizer.decode(result, skip_special_tokens=True), "generated_tokens": len(result), "checkpoint_step": self.step, "tokens_seen": self.tokens_seen}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default="runs/astheral/latest.pt")
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
