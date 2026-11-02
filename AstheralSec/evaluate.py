"""Record held-out generations for human review; never calls a tool or executes output."""
import argparse
import hashlib
import json
import time
from common import ROOT, SYSTEM, load
from resources import policy,wait_for_headroom

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--device", choices=["cpu","cuda"], default="cuda")
    p.add_argument("--max-new-tokens", type=int, default=128)
    p.add_argument("--duty-cycle", type=float, default=None)
    a = p.parse_args()
    a.duty_cycle = policy()["duty_cycle"] if a.duty_cycle is None else a.duty_cycle
    if not 0 < a.duty_cycle <= 1:
        p.error("duty-cycle must be in (0,1]")
    torch, tok, model = load(device=a.device, offline=True, merge=False)
    model.eval()
    rows = [json.loads(s) for s in (ROOT/"data/eval.jsonl").read_text().splitlines()]
    results = [dict(row, human_pass=None) for row in rows]
    report = {"manual_review_required":True,"commercial_release_approved":False,"completed":False,
        "adapter_sha256":hashlib.sha256((ROOT/"weights/adapter_model.safetensors").read_bytes()).hexdigest(),
        "max_new_tokens":a.max_new_tokens,
        "method":"Greedy base then merged-adapter generations on 12 new development prompts. Previous failures informed training changes. This is not an independent commercial benchmark.",
        "results":results}
    for name in ["base","astheral_flint"]:
        if name == "astheral_flint":
            model = model.merge_and_unload(safe_merge=True)
        for pair in results:
            wait_for_headroom(torch,a.device)
            text = tok.apply_chat_template([{"role":"system","content":SYSTEM},{"role":"user","content":pair["prompt"]}],
                tokenize=False, add_generation_prompt=True)
            batch = tok(text,return_tensors="pt").to(a.device)
            started = time.monotonic()
            def generate():
                with torch.inference_mode():
                    out = model.generate(**batch,max_new_tokens=a.max_new_tokens,do_sample=False,pad_token_id=tok.eos_token_id)
                tokens = out[0,batch.input_ids.shape[1]:]
                return tok.decode(tokens,skip_special_tokens=True), len(tokens), bool(len(tokens)>=a.max_new_tokens and tokens[-1].item()!=tok.eos_token_id)
            if name == "base":
                with model.disable_adapter():
                    answer, count, truncated = generate()
            else:
                answer, count, truncated = generate()
            pair[name] = {"answer":answer,"seconds":round(time.monotonic()-started,2),"tokens":count,"truncated":truncated}
            time.sleep((time.monotonic()-started) * (1/a.duty_cycle-1))
            (ROOT/"evaluation_report.json").write_text(json.dumps(report,indent=2)+"\n")
            print(f"Recorded {name}: {pair['category']}",flush=True)
    report["completed"] = True
    (ROOT/"evaluation_report.json").write_text(json.dumps(report,indent=2)+"\n")

if __name__ == "__main__":
    main()
