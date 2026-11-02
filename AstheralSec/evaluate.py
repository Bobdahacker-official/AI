"""Record held-out generations for human review; never calls a tool or executes output."""
import argparse
import hashlib
import json
import time
from common import ROOT, SYSTEM, load

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--device", choices=["cpu","cuda"], default="cuda")
    p.add_argument("--max-new-tokens", type=int, default=128)
    p.add_argument("--duty-cycle", type=float, default=0.20)
    a = p.parse_args()
    if not 0 < a.duty_cycle <= 1:
        p.error("duty-cycle must be in (0,1]")
    torch, tok, model = load(device=a.device, offline=True)
    model.eval()
    rows = [json.loads(s) for s in (ROOT/"data/eval.jsonl").read_text().splitlines()]
    results = []
    for row in rows:
        text = tok.apply_chat_template([{"role":"system","content":SYSTEM},{"role":"user","content":row["prompt"]}],
            tokenize=False, add_generation_prompt=True)
        batch = tok(text,return_tensors="pt").to(a.device)
        pair = dict(row)
        for name in ["base","astheral_flint"]:
            started = time.monotonic()
            def generate():
                with torch.inference_mode():
                    out = model.generate(**batch,max_new_tokens=a.max_new_tokens,do_sample=False,pad_token_id=tok.eos_token_id)
                return tok.decode(out[0,batch.input_ids.shape[1]:],skip_special_tokens=True)
            if name == "base":
                with model.disable_adapter():
                    answer = generate()
            else:
                answer = generate()
            pair[name] = {"answer":answer,"seconds":round(time.monotonic()-started,2)}
            time.sleep((time.monotonic()-started) * (1/a.duty_cycle-1))
        pair["human_pass"] = None
        results.append(pair)
        print(f"Recorded {row['category']}",flush=True)
    report = {"manual_review_required":True,"commercial_release_approved":False,
        "adapter_sha256":hashlib.sha256((ROOT/"weights/adapter_model.safetensors").read_bytes()).hexdigest(),
        "method":"Greedy base-versus-adapter generations on 12 unseen prompts. No automated safety or quality certification.",
        "results":results}
    (ROOT/"evaluation_report.json").write_text(json.dumps(report,indent=2)+"\n")

if __name__ == "__main__":
    main()
