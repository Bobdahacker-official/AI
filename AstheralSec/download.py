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
    pieces = parts / "pieces"
    pieces.mkdir(exist_ok=True)
    chunk = 16 * 1024 * 1024
    count = (a.size + chunk - 1) // chunk
    started = time.monotonic()
    def fetch(i):
        start, end = i * chunk, min((i+1)*chunk, a.size)-1
        target = parts / str(i)
        if target.exists() and target.stat().st_size == end-start+1:
            return target.stat().st_size, False
        temp = parts / f"{i}.partial"
        segments = []
        for first in range(start,end+1,4*1024*1024):
            last = min(first+4*1024*1024-1,end)
            piece = pieces / f"{first}-{last}"
            headers = pieces / f"{first}.headers"
            segments.append(piece)
            if piece.exists() and piece.stat().st_size == last-first+1:
                continue
            for attempt in range(4):
                partial = piece.with_suffix(".partial")
                offset = partial.stat().st_size if partial.exists() else 0
                if offset == last-first+1:
                    partial.replace(piece)
                    break
                if offset > last-first+1:
                    raise RuntimeError("Unexpected oversized partial range")
                resume_start = first + offset
                tail = piece.with_suffix(".tail")
                result = subprocess.run(["curl.exe", "--fail", "--location", "--silent", "--show-error",
                    "--connect-timeout", "15", "--max-time", "120", "--range", f"{resume_start}-{last}",
                    "--dump-header", str(headers), "--output", str(tail), a.url], capture_output=True, text=True)
                raw = headers.read_text(errors="replace") if headers.exists() else ""
                ranges = re.findall(r"content-range:\s*bytes (\d+)-(\d+)/(\d+)", raw, re.I)
                valid_range = ranges and tuple(map(int,ranges[-1])) == (resume_start,last,a.size)
                if valid_range and tail.exists() and tail.stat().st_size <= last-resume_start+1:
                    with partial.open("ab") as output, tail.open("rb") as source:
                        while block := source.read(1024*1024):
                            output.write(block)
                if result.returncode == 0 and valid_range and partial.stat().st_size == last-first+1:
                    partial.replace(piece)
                    break
                print(f"retry range {first}-{last}: {result.stderr[:150]}", flush=True)
                time.sleep(1+attempt)
            else:
                raise RuntimeError(f"Unable to fetch verified byte range {first}-{last}")
        with temp.open("wb") as output:
            for piece in segments:
                with piece.open("rb") as source:
                    while block := source.read(1024*1024):
                        output.write(block)
        temp.replace(target)
        return target.stat().st_size, True
    complete = 0
    transferred = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(16,max(1,a.workers))) as pool:
        for n, future in enumerate(concurrent.futures.as_completed([pool.submit(fetch,i) for i in range(count)]),1):
            size, fresh = future.result()
            complete += size
            if fresh:
                transferred += size
            elapsed = time.monotonic()-started
            if fresh:
                print(f"{n}/{count} parts; {complete/1e6:.1f} MB; new transfer {transferred/max(elapsed,.001)/1e6:.2f} MB/s", flush=True)
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
