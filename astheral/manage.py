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
RESUME_OPTIONS = ("sequence", "batch", "accumulate", "threads", "save_every", "eval_batches", "lr", "seed", "device", "precision", "loss_scope", "data")


def resume_defaults(run):
    checkpoint = Path(run) / "latest.pt"
    if not checkpoint.exists():
        return {}
    import torch
    state = torch.load(checkpoint, map_location="cpu", weights_only=True, mmap=True)
    saved = state.get("training_args", {})
    return {key: saved[key] for key in RESUME_OPTIONS if key in saved}


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
    defaults = resume_defaults(RUN) if "start" in sys.argv[1:2] and running_pid() is None else {}
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "status"])
    numeric = {"sequence": (int, 512), "batch": (int, 2), "accumulate": (int, 1), "threads": (int, 4), "save_every": (int, 25), "eval_batches": (int, 2), "lr": (float, 0.0003), "seed": (int, 42)}
    for name, (kind, value) in numeric.items():
        parser.add_argument("--" + name.replace("_", "-"), type=kind, default=defaults.get(name, value))
    parser.add_argument("--device", choices=["cpu", "cuda"], default=defaults.get("device", "cpu"))
    parser.add_argument("--precision", choices=["bf16", "fp32"], default=defaults.get("precision", "bf16"))
    parser.add_argument("--loss-scope", choices=["all", "assistant"], default=defaults.get("loss_scope", "all"))
    fallback_data = next((name for name in ("data/general-dialogue", "data/combined", "data/processed") if (ROOT / name / "metadata.json").exists()), "data/processed")
    parser.add_argument("--data", default=defaults.get("data", fallback_data))
    parser.add_argument("--allow-data-change", action="store_true")
    args = parser.parse_args()
    RUN.mkdir(parents=True, exist_ok=True)
    pid = running_pid()
    if args.action == "start" and pid is None:
        with (RUN / "training.log").open("ab", buffering=0) as log:
            command = [sys.executable, "-u", "-m", "astheral.train"]
            for name in RESUME_OPTIONS:
                command.extend(["--" + name.replace("_", "-"), str(getattr(args, name))])
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
