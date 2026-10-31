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


def running_pid(filename="train.lock"):
    path = RUN / filename
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
    parser.add_argument("--sequence", type=int, default=512)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--save-every", type=int, default=25)
    parser.add_argument("--data", default="data/combined" if (ROOT / "data/combined/metadata.json").exists() else "data/processed")
    parser.add_argument("--allow-data-change", action="store_true")
    args = parser.parse_args()
    RUN.mkdir(parents=True, exist_ok=True)
    pid = running_pid()
    if args.action == "start" and pid is None:
        with (RUN / "training.log").open("ab", buffering=0) as log:
            command = [sys.executable, "-u", "-m", "astheral.train", "--sequence", str(args.sequence), "--batch", str(args.batch), "--accumulate", "1", "--save-every", str(args.save_every), "--eval-batches", "2", "--data", args.data]
            if args.allow_data_change:
                command.append("--allow-data-change")
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        for _ in range(50):
            if process.poll() is not None:
                raise SystemExit("Trainer exited; inspect runs/astheral/training.log")
            pid = running_pid()
            if pid is not None:
                break
            time.sleep(0.2)
        if pid is None:
            raise SystemExit("Trainer launched but lock is not yet visible; inspect training.log before retrying")
    assessment_pid = running_pid("assessment.lock")
    if args.action == "start" and assessment_pid is None:
        with (RUN / "assessments.log").open("ab", buffering=0) as log:
            assessor = subprocess.Popen([sys.executable, "-u", "-m", "astheral.watch"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        for _ in range(50):
            if assessor.poll() is not None:
                raise SystemExit("Recurring evaluator exited; inspect assessments.log")
            assessment_pid = running_pid("assessment.lock")
            if assessment_pid is not None:
                break
            time.sleep(0.2)
    status = {"running": pid is not None, "pid": pid, "assessment_running": assessment_pid is not None, "assessment_pid": assessment_pid}
    checkpoint_status = RUN / "status.json"
    if checkpoint_status.exists():
        status["checkpoint"] = json.loads(checkpoint_status.read_text())
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
