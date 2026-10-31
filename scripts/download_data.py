"""Fetch the immutable official release and enforce its recorded SHA-256."""
import hashlib
from pathlib import Path
import subprocess
import tempfile

REVISION = "5f9bfba300181fb35854d64c8bf1180ea75105f7"
URL = f"https://raw.githubusercontent.com/databrickslabs/dolly/{REVISION}/data/databricks-dolly-15k.jsonl"
SHA256 = "e442d96b320010510c67a6cc0a86ea988a2a6f71c7570d1afbdf4fa631896e58"


def main():
    destination = Path("data/raw/databricks-dolly-15k.jsonl")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() == SHA256:
        print(f"Verified existing dataset: {destination}")
        return
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error", "--retry", "2", "--max-time", "180", URL, "-o", str(temporary)], check=True)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != SHA256:
            raise ValueError("Dataset checksum mismatch; refusing to use it")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Downloaded and verified {destination}")


if __name__ == "__main__":
    main()
