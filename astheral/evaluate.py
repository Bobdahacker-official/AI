"""Record real conversational generations for inspection; never infer readiness from execution alone."""
import argparse
import json
from pathlib import Path
import time
from collections import Counter

from .chat import Assistant
from .heldout import assess_references

CASES = [
    {"name": "greeting", "messages": [{"role": "user", "content": "Hello! How are you?"}]},
    {"name": "identity", "messages": [{"role": "user", "content": "What is your name?"}]},
    {"name": "arithmetic", "messages": [{"role": "user", "content": "What is 2 plus 2?"}]},
    {"name": "explanation", "messages": [{"role": "user", "content": "Explain why the sky looks blue in simple terms."}]},
    {"name": "context", "messages": [{"role": "user", "content": "My name is Mira."}, {"role": "assistant", "content": "Hello, Mira."}, {"role": "user", "content": "What is my name?"}]},
]


def response_diagnostics(reports):
    responses = [report["response"].strip() for report in reports]
    counts = Counter(responses)
    return {"cases": len(responses), "unique_responses": len(counts), "empty_responses": counts.get("", 0), "largest_identical_response_group": max(counts.values(), default=0), "interpretation": "Identical answers to unrelated prompts can reveal failure to condition on the question; this is a diagnostic, not a readiness verdict."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", help="Defaults to the reviewed conversation checkpoint when present")
    parser.add_argument("--tokenizer", default="data/processed/tokenizer.json")
    parser.add_argument("--output", default="runs/astheral/evaluations")
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--reference-per-category", type=int, default=1)
    args = parser.parse_args()
    if args.reference_per_category < 1:
        parser.error("reference-per-category must be positive")
    assistant = Assistant(args.checkpoint, args.tokenizer, threads=1)
    reports = []
    for case in CASES:
        start = time.monotonic()
        result = assistant.reply(case["messages"], max_tokens=args.max_tokens, temperature=0)
        report = {**case, **result, "seconds": time.monotonic() - start}
        reports.append(report)
        print(json.dumps(report), flush=True)
    reference_evaluation = assess_references(assistant, per_category=args.reference_per_category)
    print(json.dumps({"event": "heldout_answer_assessment", "checkpoint_step": assistant.step, **reference_evaluation}), flush=True)
    diagnostics = response_diagnostics(reports)
    print(json.dumps({"event": "response_diagnostics", "checkpoint_step": assistant.step, **diagnostics}), flush=True)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    (output / f"step-{assistant.step}.json").write_text(json.dumps({"checkpoint_step": assistant.step, "tokens_seen": assistant.tokens_seen, "results": reports, "reference_evaluation": reference_evaluation, "response_diagnostics": diagnostics, "assessment": "Inspect answers for relevance, coherence, factual accuracy, and context retention. Successful inference is not a readiness verdict."}, indent=2) + "\n")


if __name__ == "__main__":
    main()
