"""Repeat real 25-turn assessments while the focused trainer runs."""
import argparse
import fcntl
import json
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="runs/astheral-general-chat")
    parser.add_argument("--every", type=int, default=250, help="Minimum checkpoint-step gap")
    args = parser.parse_args()
    if args.every < 1:
        parser.error("every must be positive")
    run = Path(args.run)
    run.mkdir(parents=True, exist_ok=True)
    lock = (run / "conversation-assessment.lock").open("a+")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    folder = run / "long-evaluations"
    folder.mkdir(exist_ok=True)
    steps = []
    for path in folder.glob("step-*.json"):
        try:
            steps.append(int(json.loads(path.read_text())["checkpoint_step"]))
        except (ValueError, KeyError):
            continue
    last = max(steps, default=-args.every)
    stopped = False
    def stop(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopped:
        status = run / "status.json"
        try:
            step = int(json.loads(status.read_text())["step"])
        except (OSError, ValueError, KeyError):
            step = last
        if step - last >= args.every and (run / "latest.pt").exists():
            pending = folder / "pending.json"
            result = subprocess.run([sys.executable, "-u", "-m", "astheral.conversation_eval", "--checkpoint", str(run / "latest.pt"), "--turns", "25", "--output", str(pending)], timeout=900)
            if result.returncode == 0:
                report = json.loads(pending.read_text())
                last = int(report["checkpoint_step"])
                pending.replace(folder / f"step-{last}.json")
                print(json.dumps({"event": "completed_25_turn_assessment", "checkpoint_step": last, "lexical_proxy_matches": report["lexical_proxy_matches"]}), flush=True)
            else:
                print(json.dumps({"event": "assessment_failed", "returncode": result.returncode}), flush=True)
        for _ in range(30):
            if stopped:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
