"""Shared-machine headroom checks. Pauses only this job, never other applications."""
import json
import os
from pathlib import Path
import subprocess
import time
import psutil

ROOT = Path(__file__).resolve().parent
GIB = 1024**3

def policy():
    return json.loads((ROOT/"resource_policy.json").read_text())

def configure_torch():
    p = policy()
    threads = max(1,min(int(p["cpu_threads"]),os.cpu_count() or 1))
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["OMP_NUM_THREADS"] = str(threads)
    os.environ["MKL_NUM_THREADS"] = str(threads)
    import torch
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    if os.name == "nt":
        try:
            psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        except psutil.AccessDenied:
            pass
    return torch

def configure_gpu(torch):
    torch.cuda.set_per_process_memory_fraction(float(policy()["gpu_memory_fraction"]))

def snapshot(torch=None, device="cpu"):
    result = {"ram_available_gib":round(psutil.virtual_memory().available/GIB,3),
        "process_ram_gib":round(psutil.Process().memory_info().rss/GIB,3),
        "host_cpu_percent":psutil.cpu_percent(interval=0.2),
        "gpu_free_gib":None,"gpu_temperature_c":None}
    if device == "cuda" and torch is not None:
        free, total = torch.cuda.mem_get_info()
        result.update(gpu_free_gib=round(free/GIB,3),gpu_total_gib=round(total/GIB,3),
            process_cuda_allocated_gib=round(torch.cuda.memory_allocated()/GIB,3),
            process_cuda_reserved_gib=round(torch.cuda.memory_reserved()/GIB,3))
        try:
            r = subprocess.run(["nvidia-smi","--query-gpu=temperature.gpu","--format=csv,noheader,nounits","--id=0"],
                capture_output=True,text=True,timeout=3,check=True)
            result["gpu_temperature_c"] = float(r.stdout.strip())
        except (OSError,ValueError,subprocess.SubprocessError):
            pass
    return result

def wait_for_headroom(torch=None, device="cpu", required_ram_bytes=0, required_vram_bytes=0):
    p = policy()
    while True:
        s = snapshot(torch,device)
        if s["process_ram_gib"] > p["max_process_ram_gib"]:
            raise MemoryError("This job exceeded its process RAM budget; stopping it")
        reasons = []
        if s["ram_available_gib"] - required_ram_bytes/GIB < p["min_available_ram_gib"]:
            reasons.append("system RAM is busy")
        if s["host_cpu_percent"] > p["max_host_cpu_percent"]:
            reasons.append("system CPU is busy")
        if s["gpu_free_gib"] is not None and s["gpu_free_gib"] - required_vram_bytes/GIB < p["min_free_vram_gib"]:
            torch.cuda.empty_cache()
            free,_ = torch.cuda.mem_get_info()
            if (free-required_vram_bytes)/GIB < p["min_free_vram_gib"]:
                reasons.append("GPU memory is busy")
        if s["gpu_temperature_c"] is not None and s["gpu_temperature_c"] >= p["max_gpu_temperature_c"]:
            reasons.append("GPU needs to cool")
        if not reasons:
            return s
        print("Pausing this job: "+", ".join(reasons),flush=True)
        time.sleep(5)
