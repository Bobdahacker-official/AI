"""Verify release file hashes before loading locally cached weights."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def verify():
    manifest = json.loads((ROOT/"manifest.json").read_text())
    for name, expected in manifest["sha256"].items():
        path = (ROOT/name).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise ValueError("Manifest contains an invalid path")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            raise ValueError(f"Integrity check failed: {name}")
    print(f"Verified {len(manifest['sha256'])} files")

if __name__ == "__main__":
    verify()
