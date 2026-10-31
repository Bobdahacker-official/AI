# Astheral

Astheral is a real decoder-only transformer with 419,496,960 trainable parameters: 32 layers, width 1024, 16 attention heads, SwiGLU, RMSNorm, rotary embeddings, and an original 8,192-token byte-level BPE tokenizer. Its weights began at random initialization. Inference uses those weights directly through PyTorch, with a key/value cache.

The model now completes the short exchanges documented below, but remains undertrained for general conversation. Its pre-teacher checkpoint is step 565, after 494,336 input tokens. Restoring code did not reset that training progress. Teacher outputs supply training targets, so the resulting model is independently initialized but is learning from other models' responses.

## Focused short-conversation continuation

The broad teacher run reached step 590 and was saved before the focused trial. `astheral/conversation_lessons.json` contains 48 explicitly synthetic training dialogues and four reserved validation dialogues, authored by the assistant in this session. They are separate from Anthropic's published data and from `Generic/`. Every assistant turn is learned with its preceding dialogue as context; previous answers are not counted again as targets in later prefixes.

```bash
.venv/bin/python -u -m astheral.conversation_train
.venv/bin/python -m astheral.chat --checkpoint runs/astheral-conversation/latest.pt --prompt Hello
```

This trainer updates the last four blocks and final normalization of the existing model. Earlier blocks and embeddings remain frozen, so their outputs can be cached exactly once per lesson. All 32 layers are still used for ordinary inference. This saves repeated computation while fitting a small dialogue curriculum; it does not turn the assistant into a lookup table. The full model weights and the focused optimizer are saved separately under `runs/astheral-conversation/`; resume that directory using `conversation_train`, not the broad-corpus trainer.

Training continues until interrupted by default. Every 50 updates it saves weights, validation loss, and actual two-turn generated exchanges in `status.json` and `training.log`. These are evidence for review, not an automatic declaration of conversational capability. The focused curriculum can overfit, so unseen wording and generated follow-up history must also be checked.

## Reviewed short-conversation checkpoint

The initial focused run completed 520 updates and was preserved. The narrower continuation uses `astheral/short_lessons.json`: 16 synthetic three-turn dialogues with two reserved validation dialogues. Its checkpoint at 600 cumulative focused updates (overall step 1190, 616,386 input-token exposures including repeated lessons) generated these actual exchanges:

```text
You: Hello
Astheral: Hello! What would you like to chat about?
You: What is your name?
Astheral: My name is Astheral.
You: Can we talk about music?
Astheral: Sure. What music do you enjoy?

You: Hi Astheral!
Astheral: Hello! How can I help?
You: I want to discuss cooking.
Astheral: What do you like to cook?
You: Pasta.
Astheral: Would you like a simple pasta recipe?
```

The tested weights are preserved locally at `runs/astheral-conversation/selected.pt`. Chat, HTTP serving, and evaluation select this snapshot by default when it exists. Responses use greedy decoding by default. There is no response lookup, teacher call, or fallback in the inference path. `--checkpoint` still selects another explicit checkpoint.

This is a narrow learned capability. In review, `Please tell me your name.` elicited an unrelated cooking question, and an unfamiliar greeting introduced an incorrect name. These failures are recorded in `runs/astheral-conversation/review.json`; the two successful exchanges do not establish broad competence.

Further training remains separate under `runs/astheral-short`, so it cannot overwrite the selected snapshot. To resume it after the machine stops:

```bash
.venv/bin/python -u -m astheral.conversation_train --output runs/astheral-short --source runs/astheral-conversation/latest.pt --lessons astheral/short_lessons.json --allow-lesson-change --lr 0.0003
```

The local checkpoint files are necessary to reproduce these answers; GitHub contains source and lessons, not these trained weights.

## Local setup and training

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/download_data.py
.venv/bin/python -m astheral.data
.venv/bin/python -m astheral.dialogue --download-only
TOKENIZERS_PARALLELISM=false .venv/bin/python -m astheral.distill
.venv/bin/python -m pytest -q
.venv/bin/python -m astheral.manage start --data data/teacher --sequence 256 --batch 2 --accumulate 1 --loss-scope assistant --complete-examples yes --lr 0.0001 --save-every 10 --allow-data-change
```

The first run needs Internet access to the official GitHub sources, including `media.githubusercontent.com` for Git LFS downloads. The downloader verifies source size and SHA-256. Preserve an existing `data/processed/tokenizer.json`; replacing its vocabulary invalidates the checkpoint. Without an existing checkpoint the command initializes new weights; it does not download trained Astheral weights.

`manage start` runs training and recurring evaluation as background processes. Calling it again preserves an active run. Once a teacher checkpoint is saved, `manage start` without overrides resumes the saved corpus and settings. Training continues while the machine remains active; machine shutdown ends the processes.

```bash
.venv/bin/python -m astheral.manage status
.venv/bin/python -m astheral.chat --prompt Hello --max-tokens 32
.venv/bin/python -m astheral.evaluate
.venv/bin/python -m astheral.serve
```

Checkpoints and data are ignored by Git. A code checkout alone does not contain the locally trained weights. The earlier checkpoint, full optimizer state, and tokenizer are preserved locally. `Generic/` remains a separate project and is not training data for this phase.
