"""Evaluate a pinned base before deciding whether to fine-tune or adopt it."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import time
import psutil
from common import ROOT,SYSTEM,load
from resources import policy,wait_for_headroom

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--lock",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--data",type=Path,default=ROOT/"data/eval.jsonl")
    p.add_argument("--max-new-tokens",type=int,default=192)
    p.add_argument("--duty-cycle",type=float,default=None)
    a = p.parse_args()
    duty = policy()["duty_cycle"] if a.duty_cycle is None else a.duty_cycle
    if not 0 < duty <= 1:
        p.error("duty cycle must be in (0,1]")
    torch,tok,model = load(adapter=False,device="cuda",offline=True,lock_path=a.lock)
    model.eval()
    rows = [json.loads(s) for s in a.data.read_text().splitlines()]
    report = {"model":json.loads(a.lock.read_text()),"completed":False,"commercial_release_approved":False,
        "manual_review_required":True,"max_new_tokens":a.max_new_tokens,"resource_policy":policy(),"results":[]}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    for row in rows:
        status = wait_for_headroom(torch,"cuda")
        text = tok.apply_chat_template([{"role":"system","content":SYSTEM},{"role":"user","content":row["prompt"]}],
            tokenize=False,add_generation_prompt=True)
        batch = tok(text,return_tensors="pt",add_special_tokens=False).to("cuda")
        tick = time.monotonic()
        with torch.inference_mode():
            generated = model.generate(**batch,max_new_tokens=a.max_new_tokens,do_sample=False,pad_token_id=tok.eos_token_id)
        tokens = generated[0,batch.input_ids.shape[1]:]
        answer = tok.decode(tokens,skip_special_tokens=True)
        active = time.monotonic()-tick
        report["results"].append(dict(row,answer=answer,tokens=len(tokens),
            truncated=bool(len(tokens)>=a.max_new_tokens and tokens[-1].item()!=tok.eos_token_id),
            active_seconds=round(active,3),resources_before=status,human_pass=None))
        report["peak_cuda_allocated_bytes"] = torch.cuda.max_memory_allocated()
        report["peak_cuda_reserved_bytes"] = torch.cuda.max_memory_reserved()
        report["process_ram_bytes"] = psutil.Process().memory_info().rss
        a.output.write_text(json.dumps(report,indent=2)+"\n")
        print(f"Recorded candidate: {row['category']}",flush=True)
        time.sleep(active*(1/duty-1))
    report["completed"] = True
    report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    a.output.write_text(json.dumps(report,indent=2)+"\n")

if __name__ == "__main__":
    main()
