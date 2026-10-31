"""Real 25-user-turn conversation assessment, with explicit lexical diagnostics."""
import argparse
import json
import re
from pathlib import Path
import time
import urllib.request
from .chat import Assistant


CASES = [
    ("Hello there!", "greeting", ["hello", "hi", "welcome"]),
    ("Please tell me your name.", "identity_regression", ["astheral"]),
    ("What name do you answer to?", "identity_unseen", ["astheral"]),
    ("Are you human or an AI?", "identity", ["ai", "software"]),
    ("Could we have a chat about songs?", "music", ["music", "song", "listen"]),
    ("I mostly listen to jazz.", "music_followup", ["jazz", "piano", "song", "instrumental", "vocal"]),
    ("Let's switch to food.", "topic_change", ["food", "cook", "eat", "meal"]),
    ("What could I make for dinner this evening?", "dinner", ["pasta", "meal", "cook", "ingredient", "food"]),
    ("I've got pasta and some tomatoes.", "ingredients", ["pasta", "sauce", "tomato", "boil"]),
    ("How would I cook that?", "recipe", ["boil", "sauce", "cook", "warm", "combine"]),
    ("Thanks for the suggestion.", "thanks", ["welcome", "glad", "help"]),
    ("Could we discuss novels instead?", "books", ["book", "read", "novel", "story"]),
    ("I enjoy mysteries.", "books_followup", ["myster*", "cozy", "thriller", "puzzle"]),
    ("Any ideas for a creative pastime?", "hobby", ["draw*", "sketch*", "writ*", "creative", "hobby"]),
    ("I'd like to draw.", "drawing", ["draw", "sketch", "mug", "object", "plant", "outline"]),
    ("Can you give me a hand with studying?", "study", ["subject", "study", "studying", "math"]),
    ("Math is the subject.", "math", ["math", "question", "part", "arithmetic"]),
    ("What's two plus two?", "arithmetic", ["four", "4"]),
    ("Help me draft a thank-you message.", "writing", ["thank", "message", "writing", "who"]),
    ("It is for a friend who helped me.", "writing_followup", ["thank*", "appreciate", "meant", "message", "note"]),
    ("Could we chat about pets?", "pets", ["pet", "animal", "dog", "cat"]),
    ("I've got a cat.", "pets_followup", ["cat", "pet*", "nap*"]),
    ("You can call me Emma.", "user_name", ["emma"]),
    ("Do you remember what I'm called?", "recent_context", ["emma"]),
    ("Thanks, bye for now.", "goodbye", ["bye", "care", "later", "welcome", "day"]),
]


def keyword_match(text, keywords):
    text = text.casefold()
    return any(re.search(r"\b" + re.escape(word.rstrip("*")) + (r"\w*" if word.endswith("*") else r"\b"), text) for word in keywords)


def assess(assistant, turns=25, max_tokens=32):
    if not 1 <= turns <= 25:
        raise ValueError("Assessment supports 1 through 25 user turns")
    messages, reports = [], []
    for number, (prompt, category, keywords) in enumerate(CASES[:turns], 1):
        messages.append({"role": "user", "content": prompt})
        started = time.monotonic()
        answer = assistant.reply(messages, max_tokens=max_tokens, temperature=0)
        messages.append({"role": "assistant", "content": answer["response"]})
        report = {"turn": number, "category": category, "prompt": prompt, **answer, "seconds": time.monotonic() - started, "lexical_proxy_match": keyword_match(answer["response"], keywords)}
        reports.append(report)
        print(json.dumps(report), flush=True)
    return {"checkpoint_step": assistant.step, "user_turns": turns, "total_messages": len(messages), "lexical_proxy_matches": sum(r["lexical_proxy_match"] for r in reports), "lexical_proxy_version": 2, "interpretation": "Keyword matches are weak diagnostics. Read every response for relevance and coherence; this is not a readiness certificate.", "results": reports}


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--checkpoint")
    source.add_argument("--url", help="Assess a running Astheral HTTP server instead of loading weights")
    parser.add_argument("--turns", type=int, default=25)
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--history-tokens", type=int, help="Compare shorter rolling context without changing weights")
    parser.add_argument("--output", default="runs/conversation-evaluation.json")
    args = parser.parse_args()
    if args.url:
        if args.history_tokens is not None:
            parser.error("history-tokens is local-model-only; HTTP uses the server's history policy")
        class Endpoint:
            def __init__(self):
                self.health = json.load(urllib.request.urlopen(args.url.rstrip("/") + "/health", timeout=30))
                self.step = self.health["checkpoint_step"]
            def reply(self, messages, max_tokens, temperature):
                request = urllib.request.Request(args.url.rstrip("/") + "/chat", data=json.dumps({"messages": messages, "max_tokens": max_tokens, "temperature": temperature}).encode(), headers={"Content-Type": "application/json"})
                return json.load(urllib.request.urlopen(request, timeout=180))
        assistant = Endpoint()
    else:
        assistant = Assistant(args.checkpoint, threads=1, history_tokens=args.history_tokens)
    report = assess(assistant, args.turns, args.max_tokens)
    report["transport"] = args.url or "Local model inference"
    report["history_tokens"] = args.history_tokens
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(output)


if __name__ == "__main__":
    main()
