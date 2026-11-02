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
    from resources import configure_torch
    return configure_torch()

def load(adapter=True, device="cpu", offline=False, merge=True, lock_path=None):
    torch = configure()
    from resources import configure_gpu, wait_for_headroom
    if device == "cuda":
        configure_gpu(torch)
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel
    import json
    lock = json.loads(Path(lock_path or ROOT / "base_model.json").read_text())
    name = lock["model"]
    size = lock.get("weights_size_bytes",0)
    wait_for_headroom(torch,device,required_ram_bytes=size*(2 if device=="cpu" else 1),
        required_vram_bytes=size if device=="cuda" else 0)
    tokenizer = AutoTokenizer.from_pretrained(name, revision=lock["revision"], local_files_only=offline)
    model = AutoModelForCausalLM.from_pretrained(
        name, revision=lock["revision"], dtype=torch.float32 if device == "cpu" else torch.bfloat16,
        attn_implementation="sdpa", trust_remote_code=False, local_files_only=offline,
    ).to(device)
    if adapter:
        model = PeftModel.from_pretrained(model, ROOT / "weights")
        if merge:
            model = model.merge_and_unload(safe_merge=True)
    return torch, tokenizer, model
