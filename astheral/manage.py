"""Start/resume continuous training as a logged background process, or report it."""
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "runs" / "astheral"


def running_pid():
    path = RUN / "train.lock"
    if not path.exists():
        return None
    with path.open("r+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            value = handle.read().strip()
            return int(value) if value.isdigit() else None
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "status"])
    args = parser.parse_args()
    RUN.mkdir(parents=True, exist_ok=True)
    pid = running_pid()
    if args.action == "start" and pid is None:
        with (RUN / "training.log").open("ab", buffering=0) as log:
            process = subprocess.Popen([sys.executable, "-u", "-m", "astheral.train", "--sequence", "128", "--accumulate", "1", "--save-every", "10", "--eval-batches", "2"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        for _ in range(50):
            if process.poll() is not None:
                raise SystemExit("Trainer exited; inspect runs/astheral/training.log")
            pid = running_pid()
            if pid is not None:
                break
            time.sleep(0.2)
        if pid is None:
            raise SystemExit("Trainer launched but lock is not yet visible; inspect training.log before retrying")
    status = {"running": pid is not None, "pid": pid}
    checkpoint_status = RUN / "status.json"
    if checkpoint_status.exists():
        status["checkpoint"] = json.loads(checkpoint_status.read_text())
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
