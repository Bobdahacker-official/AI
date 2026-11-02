"""Resumable bounded-memory parallel HTTP ranges; checks each range and final SHA256."""
import argparse
import concurrent.futures
import hashlib
from pathlib import Path
import re
import subprocess
import time

def main():
    p = argparse.ArgumentParser()
    p.add_argument("url")
    p.add_argument("output", type=Path)
    p.add_argument("--size", type=int, required=True)
    p.add_argument("--sha256", required=True)
    p.add_argument("--workers", type=int, default=6)
    a = p.parse_args()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    parts = a.output.with_name(a.output.name + ".parts")
    parts.mkdir(exist_ok=True)
    chunk = 16 * 1024 * 1024
    count = (a.size + chunk - 1) // chunk
    started = time.monotonic()
    def fetch(i):
        start, end = i * chunk, min((i+1)*chunk, a.size)-1
        target = parts / str(i)
        if target.exists() and target.stat().st_size == end-start+1:
            return target.stat().st_size
        temp = parts / f"{i}.partial"
        headers = parts / f"{i}.headers"
        for attempt in range(4):
            result = subprocess.run(["curl.exe", "--fail", "--location", "--silent", "--show-error",
                "--connect-timeout", "20", "--max-time", "240", "--range", f"{start}-{end}",
                "--dump-header", str(headers), "--output", str(temp), a.url], capture_output=True, text=True)
            raw = headers.read_text(errors="replace") if headers.exists() else ""
            ranges = re.findall(r"content-range:\s*bytes (\d+)-(\d+)/(\d+)", raw, re.I)
            if (result.returncode == 0 and temp.exists() and temp.stat().st_size == end-start+1
                and ranges and tuple(map(int,ranges[-1])) == (start,end,a.size)):
                temp.replace(target)
                return target.stat().st_size
            print(f"retry part {i}: {result.stderr[:150]}", flush=True)
            time.sleep(1+attempt)
        raise RuntimeError(f"Unable to fetch verified byte range {start}-{end}")
    complete = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8,max(1,a.workers))) as pool:
        for n, future in enumerate(concurrent.futures.as_completed([pool.submit(fetch,i) for i in range(count)]),1):
            complete += future.result()
            elapsed = time.monotonic()-started
            print(f"{n}/{count} parts; {complete/1e6:.1f} MB; {complete/max(elapsed,.001)/1e6:.2f} MB/s", flush=True)
    combined = a.output.with_name(a.output.name + ".assembling")
    digest = hashlib.sha256()
    with combined.open("wb") as output:
        for i in range(count):
            with (parts / str(i)).open("rb") as source:
                while block := source.read(1024*1024):
                    digest.update(block)
                    output.write(block)
    if digest.hexdigest() != a.sha256:
        raise RuntimeError("SHA256 mismatch: refusing to install")
    combined.replace(a.output)
    print(f"VERIFIED {a.output} SHA256={a.sha256}", flush=True)

if __name__ == "__main__":
    main()
