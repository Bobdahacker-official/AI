# Astheral

Astheral is a real decoder-only transformer with 419,496,960 trainable parameters: 32 layers, width 1024, 16 attention heads, SwiGLU, RMSNorm, rotary embeddings, and an original 8,192-token byte-level BPE tokenizer. Its weights began at random initialization. Inference uses those weights directly through PyTorch, with a key/value cache.

The model remains undertrained and has not demonstrated reliable conversation. Its pre-teacher checkpoint is step 565, after 494,336 input tokens. Restoring code does not reset that training progress. Teacher outputs now supply training targets, so the resulting model is independently initialized but is learning from another model's published responses.

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
