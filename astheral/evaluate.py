"""Record real conversational generations for inspection; never infer readiness from execution alone."""
import argparse
import json
from pathlib import Path
import time

from .chat import Assistant

CASES = [
    {"name": "greeting", "messages": [{"role": "user", "content": "Hello! How are you?"}]},
    {"name": "identity", "messages": [{"role": "user", "content": "What is your name?"}]},
    {"name": "arithmetic", "messages": [{"role": "user", "content": "What is 2 plus 2?"}]},
    {"name": "explanation", "messages": [{"role": "user", "content": "Explain why the sky looks blue in simple terms."}]},
    {"name": "context", "messages": [{"role": "user", "content": "My name is Mira."}, {"role": "assistant", "content": "Hello, Mira."}, {"role": "user", "content": "What is my name?"}]},
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default="runs/astheral/latest.pt")
    parser.add_argument("--tokenizer", default="data/processed/tokenizer.json")
    parser.add_argument("--output", default="runs/astheral/evaluations")
    parser.add_argument("--max-tokens", type=int, default=32)
    args = parser.parse_args()
    assistant = Assistant(args.checkpoint, args.tokenizer, threads=1)
    reports = []
    for case in CASES:
        start = time.monotonic()
        result = assistant.reply(case["messages"], max_tokens=args.max_tokens, temperature=0)
        report = {**case, **result, "seconds": time.monotonic() - start}
        reports.append(report)
        print(json.dumps(report), flush=True)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / f"step-{assistant.step}.json").write_text(json.dumps({"checkpoint_step": assistant.step, "tokens_seen": assistant.tokens_seen, "results": reports, "assessment": "Inspect answers for relevance, coherence, factual accuracy, and context retention. Successful inference is not a readiness verdict."}, indent=2) + "\n")


if __name__ == "__main__":
    main()
