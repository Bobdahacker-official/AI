"""Keep measuring real checkpoint generations while continuous training progresses."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default="runs/astheral")
    parser.add_argument("--every", type=int, default=25)
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args()
    if min(args.every, args.poll_seconds) < 1:
        parser.error("Assessment intervals must be positive")
    run = Path(args.run)
    run.mkdir(parents=True, exist_ok=True)
    lock = (run / "assessment.lock").open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another recurring evaluator already owns this run")
    lock.seek(0)
    lock.truncate()
    lock.write(str(os.getpid()))
    lock.flush()
    stopped = False

    def stop(signum, frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    assessed = []
    for path in (run / "evaluations").glob("step-*.json"):
        assessed.append(int(path.stem.split("-")[-1]))
    last_assessed = max(assessed, default=0)
    print(json.dumps({"event": "assessment_watcher_started", "pid": os.getpid(), "last_assessed": last_assessed, "every_steps": args.every}), flush=True)
    while not stopped:
        status_path = run / "status.json"
        if status_path.exists():
            try:
                status = json.loads(status_path.read_text())
                step = status["step"]
                if step >= max(1, last_assessed + args.every):
                    print(json.dumps({"event": "assessing", "step": step}), flush=True)
                    # Each subprocess releases model mappings when it exits. Training continues.
                    result = subprocess.run([sys.executable, "-u", "-m", "astheral.evaluate", "--checkpoint", str(run / "latest.pt"), "--output", str(run / "evaluations")], timeout=300, check=False)
                    print(json.dumps({"event": "assessment_finished", "step": step, "exit_code": result.returncode, "readiness_claimed": False}), flush=True)
                    last_assessed = step
            except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
                print(json.dumps({"event": "assessment_error", "detail": str(error)}), flush=True)
        for _ in range(args.poll_seconds):
            if stopped:
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
