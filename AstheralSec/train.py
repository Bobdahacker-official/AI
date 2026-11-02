"""Low-duty-cycle LoRA training. Only assistant response tokens contribute loss."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import random
import time
from common import ROOT, BASE, SYSTEM, configure

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--steps", type=int, default=256)
    p.add_argument("--duty-cycle", type=float, default=0.20)
    p.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    a = p.parse_args()
    if a.steps < 1 or not 0 < a.duty_cycle <= 1:
        p.error("steps must be positive and duty-cycle in (0,1]")
    torch = configure()
    import psutil
    from huggingface_hub import model_info
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import LoraConfig, get_peft_model
    random.seed(42)
    torch.manual_seed(42)
    if a.device == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; use --device cpu")
        torch.cuda.set_per_process_memory_fraction(0.30)
    lockpath = ROOT / "base_model.json"
    lock = json.loads(lockpath.read_text()) if lockpath.exists() else {"model": BASE, "revision": model_info(BASE).sha}
    lockpath.write_text(json.dumps(lock, indent=2) + "\n")
    tok = AutoTokenizer.from_pretrained(BASE, revision=lock["revision"])
    model = AutoModelForCausalLM.from_pretrained(BASE, revision=lock["revision"],
        dtype=torch.float32 if a.device == "cpu" else torch.bfloat16,
        attn_implementation="sdpa", trust_remote_code=False).to(a.device)
    model.config.use_cache = False
    model = get_peft_model(model, LoraConfig(r=4, lora_alpha=8, lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"], bias="none", task_type="CAUSAL_LM"))
    model.train()
    opt = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=1e-4)
    raw = (ROOT / "data/train.jsonl").read_bytes()
    rows = [json.loads(line) for line in raw.decode().splitlines()]
    batches = []
    for row in rows:
        msgs = [{"role":"system", "content":SYSTEM}, {"role":"user", "content":row["prompt"]}]
        prefix = tok.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, return_dict=False)
        full = tok.apply_chat_template(msgs + [{"role":"assistant", "content":row["answer"]}], tokenize=True, return_dict=False)
        if full[:len(prefix)] != prefix:
            raise ValueError("Chat template prefix mismatch; assistant loss mask would be incorrect")
        if len(full) > 384:
            raise ValueError("Training example exceeds 384 tokens; shorten it instead of truncating the answer")
        ids = torch.tensor([full], device=a.device)
        labels = ids.clone()
        labels[:, :len(prefix)] = -100
        batches.append((ids, labels))
    started = time.monotonic()
    history = []
    peak_rss = 0
    for step in range(a.steps):
        if step % len(batches) == 0:
            random.shuffle(batches)
        tick = time.monotonic()
        ids, labels = batches[step % len(batches)]
        opt.zero_grad(set_to_none=True)
        loss = model(input_ids=ids, attention_mask=torch.ones_like(ids), labels=labels).loss
        if not torch.isfinite(loss):
            raise RuntimeError("Nonfinite loss; refusing to publish weights")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if a.device == "cuda":
            torch.cuda.synchronize()
        active = time.monotonic() - tick
        peak_rss = max(peak_rss, psutil.Process().memory_info().rss)
        entry = {"step":step+1, "loss":round(loss.item(), 6), "active_seconds":round(active, 3)}
        history.append(entry)
        print(json.dumps(entry), flush=True)
        time.sleep(active * (1 / a.duty_cycle - 1))
    out = ROOT / "weights"
    model.save_pretrained(out, safe_serialization=True)
    report = {"name":"Astheral Flint", "status":"locally trained; commercial release qualification pending",
        "completed_at_utc":datetime.now(timezone.utc).isoformat(),
        "software":{name:importlib.metadata.version(name) for name in ["torch","transformers","peft","accelerate","huggingface-hub","safetensors","psutil"]},
        "base":lock, "steps":a.steps, "examples":len(rows), "seed":42,
        "trainable_parameters":sum(p.numel() for p in model.parameters() if p.requires_grad),
        "device":a.device, "cpu_threads":2, "duty_cycle":a.duty_cycle,
        "elapsed_seconds":round(time.monotonic()-started,2), "peak_rss_bytes":peak_rss,
        "peak_cuda_allocated_bytes":torch.cuda.max_memory_allocated() if a.device=="cuda" else 0,
        "peak_cuda_reserved_bytes":torch.cuda.max_memory_reserved() if a.device=="cuda" else 0,
        "gpu":torch.cuda.get_device_name() if a.device=="cuda" else None,
        "dataset_sha256":hashlib.sha256(raw).hexdigest(), "history":history,
        "limitations":"Small synthetic corpus; training loss is not a capability or safety benchmark."}
    (ROOT / "training_report.json").write_text(json.dumps(report, indent=2)+"\n")
    print("Saved trained adapter and training_report.json", flush=True)

if __name__ == "__main__":
    main()
