"""Resource-aware local SFT with assistant-only loss and resumable checkpoints."""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import random
import time
import uuid
import psutil
from common import ROOT,SYSTEM,configure
from resources import policy,configure_gpu,wait_for_headroom

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lock",type=Path,default=ROOT/"base_model.json")
    p.add_argument("--output",type=Path,default=ROOT)
    p.add_argument("--data",type=Path,default=ROOT/"data/train.jsonl")
    p.add_argument("--steps",type=int,default=128)
    p.add_argument("--learning-rate",type=float,default=2e-5)
    p.add_argument("--rank",type=int,default=8)
    p.add_argument("--targets",choices=["attention","all-linear"],default="attention")
    p.add_argument("--max-length",type=int,default=512)
    p.add_argument("--duty-cycle",type=float,default=None)
    p.add_argument("--device",choices=["cpu","cuda"],default="cuda")
    p.add_argument("--checkpoint-every",type=int,default=32)
    p.add_argument("--resume",action="store_true")
    p.add_argument("--gradient-checkpointing",action="store_true")
    a = p.parse_args()
    a.duty_cycle = policy()["duty_cycle"] if a.duty_cycle is None else a.duty_cycle
    if min(a.steps,a.rank,a.checkpoint_every,a.max_length)<1 or a.learning_rate<=0 or not 0<a.duty_cycle<=1:
        p.error("Training counts/rate must be positive and duty-cycle in (0,1]")
    output = a.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    lock = json.loads(a.lock.read_text())
    raw = a.data.read_bytes()
    canonical = hashlib.sha256(raw.replace(b"\r\n",b"\n")).hexdigest()
    signature = {"base":lock,"dataset_canonical_sha256":canonical,"rank":a.rank,"targets":a.targets,
        "learning_rate":a.learning_rate,"max_length":a.max_length,"gradient_checkpointing":a.gradient_checkpointing}
    checkpoint_root = output/".checkpoints"
    checkpoint = None
    if a.resume:
        latest = json.loads((checkpoint_root/"latest.json").read_text())
        checkpoint = (checkpoint_root/latest["path"]).resolve()
        if not checkpoint.is_relative_to(checkpoint_root.resolve()):
            raise ValueError("Invalid checkpoint path")
        if json.loads((checkpoint/"signature.json").read_text()) != signature:
            raise ValueError("Checkpoint configuration or dataset does not match")
    torch = configure()
    random.seed(42)
    torch.manual_seed(42)
    if a.device=="cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable")
        configure_gpu(torch)
    size = lock.get("weights_size_bytes",0)
    wait_for_headroom(torch,a.device,required_ram_bytes=size*(2 if a.device=="cpu" else 1),
        required_vram_bytes=size if a.device=="cuda" else 0)
    from transformers import AutoTokenizer,AutoModelForCausalLM
    from peft import LoraConfig,get_peft_model,PeftModel
    tok = AutoTokenizer.from_pretrained(lock["model"],revision=lock["revision"],local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(lock["model"],revision=lock["revision"],
        dtype=torch.float32 if a.device=="cpu" else torch.bfloat16,
        attn_implementation="sdpa",trust_remote_code=False,local_files_only=True).to(a.device)
    model.config.use_cache = False
    if a.gradient_checkpointing:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant":False})
        model.enable_input_require_grads()
    if checkpoint:
        model = PeftModel.from_pretrained(model,checkpoint,is_trainable=True)
    else:
        model = get_peft_model(model,LoraConfig(r=a.rank,lora_alpha=2*a.rank,lora_dropout=0.05,
            target_modules=["q_proj","v_proj"] if a.targets=="attention" else "all-linear",
            bias="none",task_type="CAUSAL_LM",revision=lock["revision"]))
    model.train()
    opt = torch.optim.AdamW((v for v in model.parameters() if v.requires_grad),lr=a.learning_rate)
    rows = [json.loads(s) for s in raw.decode("utf-8").splitlines()]
    batches = []
    for row in rows:
        messages = [{"role":"system","content":SYSTEM},{"role":"user","content":row["prompt"]}]
        prefix = tok.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,return_dict=False)
        full = tok.apply_chat_template(messages+[{"role":"assistant","content":row["answer"]}],tokenize=True,return_dict=False)
        if full[:len(prefix)] != prefix or len(full)>a.max_length:
            raise ValueError("Invalid chat prefix or oversized example; answers are never silently truncated")
        ids = torch.tensor([full])
        labels = ids.clone()
        labels[:,:len(prefix)] = -100
        batches.append((ids,labels))
    history,order,start,elapsed_before = [],list(range(len(batches))),0,0.0
    peak_rss,prior_cuda_allocated,prior_cuda_reserved = 0,0,0
    segments = []
    run_id = "run-"+uuid.uuid4().hex[:12]
    if checkpoint:
        state = torch.load(checkpoint/"optimizer.pt",map_location="cpu",weights_only=True)
        opt.load_state_dict(state["optimizer"])
        history,order,start = state["history"],state["order"],state["completed_steps"]
        random.setstate(state["python_rng"])
        torch.set_rng_state(state["torch_rng"])
        if a.device=="cuda" and state["cuda_rng"] is not None:
            torch.cuda.set_rng_state(state["cuda_rng"])
        elapsed_before,run_id,segments = state["elapsed_seconds"],state["run_id"],state["segments"]
        peak_rss,prior_cuda_allocated,prior_cuda_reserved = state["peak_rss"],state["peak_cuda_allocated"],state["peak_cuda_reserved"]
        del state
    if start>=a.steps:
        raise ValueError("Requested total steps must exceed the checkpoint step")
    segments.append({"start_step":start,"device":a.device,"cpu_threads":torch.get_num_threads(),
        "resource_policy":policy(),"started_at_utc":datetime.now(timezone.utc).isoformat()})
    started = time.monotonic()
    def cuda_peaks():
        return (max(prior_cuda_allocated,torch.cuda.max_memory_allocated()),
            max(prior_cuda_reserved,torch.cuda.max_memory_reserved())) if a.device=="cuda" else (0,0)
    def save_checkpoint(completed):
        folder = checkpoint_root/run_id/f"step-{completed:06d}"
        model.save_pretrained(folder,safe_serialization=True)
        segments[-1]["last_completed_step"] = completed
        allocated,reserved = cuda_peaks()
        state = {"optimizer":opt.state_dict(),"history":history,"order":order,"completed_steps":completed,
            "python_rng":random.getstate(),"torch_rng":torch.get_rng_state(),
            "cuda_rng":torch.cuda.get_rng_state() if a.device=="cuda" else None,
            "elapsed_seconds":elapsed_before+time.monotonic()-started,"run_id":run_id,"segments":segments,
            "peak_rss":peak_rss,"peak_cuda_allocated":allocated,"peak_cuda_reserved":reserved}
        torch.save(state,folder/"optimizer.pt")
        (folder/"signature.json").write_text(json.dumps(signature,indent=2)+"\n")
        pointer = checkpoint_root/"latest.tmp"
        pointer.write_text(json.dumps({"path":folder.relative_to(checkpoint_root).as_posix()})+"\n")
        pointer.replace(checkpoint_root/"latest.json")
    for step in range(start,a.steps):
        if step%8==0:
            wait_for_headroom(torch,a.device)
        if step%len(batches)==0:
            random.shuffle(order)
        tick = time.monotonic()
        ids,labels = (v.to(a.device) for v in batches[order[step%len(batches)]])
        opt.zero_grad(set_to_none=True)
        loss = model(input_ids=ids,attention_mask=torch.ones_like(ids),labels=labels).loss
        if not torch.isfinite(loss):
            raise RuntimeError("Nonfinite loss; refusing to publish weights")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
        opt.step()
        if a.device=="cuda":
            torch.cuda.synchronize()
        active = time.monotonic()-tick
        peak_rss = max(peak_rss,psutil.Process().memory_info().rss)
        entry = {"step":step+1,"loss":round(loss.item(),6),"active_seconds":round(active,3)}
        history.append(entry)
        print(json.dumps(entry),flush=True)
        time.sleep(active*(1/a.duty_cycle-1))
        if (step+1)%a.checkpoint_every==0 or step+1==a.steps:
            save_checkpoint(step+1)
    model.save_pretrained(output/"weights",safe_serialization=True)
    allocated,reserved = cuda_peaks()
    segments[-1]["last_completed_step"] = a.steps
    report = {"name":"Astheral Flint","status":"locally trained; commercial qualification requires evaluation",
        "completed_at_utc":datetime.now(timezone.utc).isoformat(),"base":lock,"steps":a.steps,"resumed_from_step":start,
        "examples":len(rows),"seed":42,"lora_rank":a.rank,"target_modules":a.targets,"learning_rate":a.learning_rate,
        "trainable_parameters":sum(v.numel() for v in model.parameters() if v.requires_grad),
        "device":a.device,"gpu":torch.cuda.get_device_name() if a.device=="cuda" else None,
        "cpu_threads":torch.get_num_threads(),"duty_cycle":a.duty_cycle,"resource_policy":policy(),"segments":segments,
        "elapsed_seconds":round(elapsed_before+time.monotonic()-started,2),"peak_rss_bytes":peak_rss,
        "peak_cuda_allocated_bytes":allocated,"peak_cuda_reserved_bytes":reserved,
        "dataset_sha256":hashlib.sha256(raw).hexdigest(),"dataset_canonical_sha256":canonical,"history":history,
        "software":{n:importlib.metadata.version(n) for n in ["torch","transformers","peft","accelerate","huggingface-hub","safetensors","psutil"]}}
    (output/"training_report.json").write_text(json.dumps(report,indent=2)+"\n")
    if output==ROOT.resolve():
        from verify_artifacts import write_manifest
        write_manifest()
    print("Saved trained weights, report, and resumable checkpoint",flush=True)
