"""Shared model configuration; never executes generated text."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = "Qwen/Qwen2.5-0.5B-Instruct"
SYSTEM = (
    "You are Astheral Flint, a security assistant. Help with secure coding, "
    "incident response, forensic analysis, CTFs, and bounded tests in explicitly authorized isolated labs. "
    "Give concrete, verifiable steps and explain expected results and cleanup. Ask for scope when unclear. "
    "Do not help attack third-party systems, steal credentials, deploy malware, evade detection, "
    "cause destruction, or make weapons. Offer harmless local simulations instead. "
    "A private IP address alone does not prove authorization. Never claim a test was executed."
)

def configure():
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("MKL_NUM_THREADS", "2")
    import torch
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    return torch

def load(adapter=True, device="cpu", offline=False):
    torch = configure()
    if device == "cuda":
        torch.cuda.set_per_process_memory_fraction(0.30)
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel
    import json
    lock = json.loads((ROOT / "base_model.json").read_text())
    tokenizer = AutoTokenizer.from_pretrained(BASE, revision=lock["revision"], local_files_only=offline)
    model = AutoModelForCausalLM.from_pretrained(
        BASE, revision=lock["revision"], dtype=torch.float32 if device == "cpu" else torch.bfloat16,
        attn_implementation="sdpa", trust_remote_code=False, local_files_only=offline,
    ).to(device)
    if adapter:
        model = PeftModel.from_pretrained(model, ROOT / "weights")
    return torch, tokenizer, model
