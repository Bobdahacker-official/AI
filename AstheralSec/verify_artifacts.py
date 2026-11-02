"""Verify release file hashes before loading locally cached weights."""
import hashlib
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def digest_file(path):
    raw = path.read_bytes()
    if path.suffix != ".safetensors":
        raw = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()

def write_manifest():
    names = ["weights/adapter_model.safetensors", "weights/adapter_config.json", "base_model.json",
        "data/train.jsonl", "training_report.json", "common.py", "chat.py", "lab_tools.py", "train.py", "build_data.py",
        "resources.py", "resource_policy.json", "trainer.py"]
    manifest = {"hash_mode":"SHA256 raw binary; LF-normalized UTF-8 text",
        "sha256":{name:digest_file(ROOT/name) for name in names}}
    (ROOT/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")

def verify():
    manifest = json.loads((ROOT/"manifest.json").read_text())
    for name, expected in manifest["sha256"].items():
        path = (ROOT/name).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise ValueError("Manifest contains an invalid path")
        digest = digest_file(path)
        if digest != expected:
            raise ValueError(f"Integrity check failed: {name}")
    print(f"Verified {len(manifest['sha256'])} files")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Refresh hashes after intentional local training or source edits")
    if parser.parse_args().refresh:
        write_manifest()
    verify()
