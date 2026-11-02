"""Recover a pinned public base with resumable transfers and SHA256 verification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lock",type=Path,required=True)
    p.add_argument("--workers",type=int,default=4)
    a = p.parse_args()
    lock = json.loads(a.lock.read_text())
    name,rev,sha = lock["model"],lock["revision"],lock["weights_sha256"]
    filename = lock.get("weights_file","model.safetensors")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+",name) or not re.fullmatch(r"[0-9a-f]{40}",rev):
        raise ValueError("Invalid pinned public model identifier")
    if not re.fullmatch(r"[0-9a-f]{64}",sha) or Path(filename).name != filename:
        raise ValueError("Invalid weights filename or digest")
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    from huggingface_hub import snapshot_download,hf_hub_download
    from huggingface_hub.constants import HF_HUB_CACHE
    snapshot_download(name,revision=rev,allow_patterns=["*.json","*.txt","LICENSE"])
    blob = Path(HF_HUB_CACHE)/("models--"+name.replace("/","--"))/"blobs"/sha
    valid = False
    if blob.exists() and blob.stat().st_size == lock["weights_size_bytes"]:
        digest = hashlib.sha256()
        with blob.open("rb") as source:
            while block := source.read(1024*1024):
                digest.update(block)
        valid = digest.hexdigest() == sha
    if not valid:
        subprocess.run([sys.executable,str(Path(__file__).with_name("download.py")),
            f"https://huggingface.co/{name}/resolve/{rev}/{filename}",str(blob),
            "--size",str(lock["weights_size_bytes"]),"--sha256",sha,"--workers",str(a.workers)],check=True)
    print(hf_hub_download(name,filename,revision=rev),flush=True)

if __name__ == "__main__":
    main()
