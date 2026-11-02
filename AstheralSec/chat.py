"""Local chat only: no network tools, shell, or command execution."""
import argparse
from common import load, SYSTEM
from resources import wait_for_headroom

def main():
    p = argparse.ArgumentParser()
    p.add_argument("prompt", nargs="?")
    p.add_argument("--device", choices=["cpu", "cuda"], default="cuda")
    p.add_argument("--max-new-tokens", type=int, default=192)
    p.add_argument("--offline", action="store_true", help="Use only cached base-model files")
    a = p.parse_args()
    torch, tok, model = load(device=a.device, offline=a.offline)
    model.eval()
    while True:
        question = a.prompt or input("You (exit to quit): ")
        if question.strip().lower() in {"exit", "quit"}:
            return
        wait_for_headroom(torch,a.device)
        messages = [{"role":"system", "content":SYSTEM}, {"role":"user", "content":question}]
        text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        batch = tok(text, return_tensors="pt").to(a.device)
        if batch.input_ids.shape[1] > 2048:
            raise ValueError("Keep the prompt under 2048 tokens")
        with torch.inference_mode():
            output = model.generate(**batch, max_new_tokens=min(512, max(1,a.max_new_tokens)), do_sample=False,
                pad_token_id=tok.eos_token_id)
        print(tok.decode(output[0, batch.input_ids.shape[1]:], skip_special_tokens=True))
        if a.prompt:
            return

if __name__ == "__main__":
    main()
