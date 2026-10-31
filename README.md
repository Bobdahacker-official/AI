# Astheral

Astheral is a real **419,496,960-parameter** causal transformer trained from random
initialization. Both its weights and byte-level BPE tokenizer start from scratch.
No pretrained weights, external AI APIs, retrieval responses, or scripted answers
are used in inference. Its intended personality is a friendly, helpful and honest
AI assistant.

The training program performs genuine forward passes, next-token cross-entropy,
backpropagation, gradient clipping and AdamW updates over the entire model. It
trains continuously by default, with atomic resumable checkpoints and measured
held-out loss. Early checkpoints can produce incoherent output; the implementation
does not claim a converged or capable assistant simply because it can generate.

## Setup

Run from `/workspace/AI`, or the repository root on another machine:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/download_data.py
.venv/bin/python -m astheral.data
.venv/bin/python -m astheral.corpus
.venv/bin/python -m pytest -q
```

On this cloud environment GitHub and package requests use inherited HTTPS proxy
and CA settings. If a command cannot reach `proxy:8080`, rerun that network command
using the execution tool's supported `require_escalated` route. This route has
been verified against GitHub using both HTTPS and `git ls-remote`. Keep TLS
verification enabled. Never unset proxy variables or copy credentials.

The actual training machine has four CPU cores and 32 GiB RAM, with AVX512 BF16.
The run uses CPU bfloat16 autocast, FP32 parameters and AdamW state, and four
threads. Checkpoints include optimizer state and occupy approximately 4.7 GiB;
reserve at least 12 GiB free disk for an atomic checkpoint replacement. Generated
weights, tokenized data and dependencies stay outside Git in ignored directories.

## Train continuously

```sh
.venv/bin/python -u -m astheral.train --sequence 128 --accumulate 1 --save-every 10 --eval-batches 2
```

There is no default step or time limit. Interrupt with SIGINT or SIGTERM for a
graceful checkpoint, or let it run while the machine remains available. A hard
termination/OOM cannot save in-progress work; the previous atomic checkpoint is
retained. Restart the same command to load `runs/astheral/latest.pt`, including
optimizer and CPU RNG state. Only one trainer may own a run directory. Keep the
same sampling arguments for exact CPU continuation. A finite `--steps N` selects
the absolute target step and is useful for controlled experiments.

To launch or resume a detached trainer with persistent console logs, use
`.venv/bin/python -m astheral.manage start`. It checks the actual process lock
and leaves an existing trainer running. Check it with
`.venv/bin/python -m astheral.manage status`. Detached output goes to
`runs/astheral/training.log`; the metrics and checkpoint files are the same.
No process survives shutdown of the cloud machine; saved checkpoints support
continuation on its next start.

The manager also starts a recurring evaluator. It checks for later durable
checkpoints and records actual conversation answers every 25 checkpoint steps.
Its PID is exposed in manager status; output is in `runs/astheral/assessments.log`
and `runs/astheral/evaluations/step-N.json`. It never fabricates a readiness verdict
or terminates training because inference merely succeeded.

The manager now uses 512-token windows and batch size 2 by default. It selects
`data/combined` when present, which contains existing Dolly instructions and
Google Taskmaster-1 multi-turn conversations. This increases observed token
throughput and dialogue coverage. Override `--sequence`, `--batch`, `--data`, or
`--save-every` explicitly for other experiments. A running trainer is left alone;
new options take effect when starting a new process.

To transition an existing Dolly-only checkpoint to the verified combined corpus,
use `.venv/bin/python -m astheral.manage start --allow-data-change` after its old
trainer has saved and exited. This explicit operation preserves weights and
optimizer and records old corpus provenance in `data_history`; a tokenizer or
architecture mismatch is always rejected. Ordinary resumes on the same corpus
do not need that flag.

`runs/astheral/metrics.jsonl` records actual optimizer steps, losses, gradient
norms, tokens processed and step durations. `runs/astheral/status.json` records
the last completed checkpoint. Checkpoint step 0 is initialization, not training.
The first trained checkpoint is written after step 1, then every 10 steps.
Validation uses fixed held-out samples; increase `--eval-batches` for a broader
estimate. The fixed sample is not a full-dataset benchmark.

For NVIDIA hardware install an appropriate official PyTorch build, then select
`--device cuda --precision bf16`. CPU execution is validated here; CUDA execution
is implemented but has not been exercised on this machine.

## Chat and local web interface

After a trained checkpoint exists:

```sh
.venv/bin/python -m astheral.chat --prompt 'Hello, Astheral!' --max-tokens 32
.venv/bin/python -m astheral.chat
.venv/bin/python -m astheral.serve
```

The server serves the chat interface at its root, `GET /health` for checkpoint
metadata, and `POST /chat` for generation. For example, from the same network
namespace as the server:

```sh
curl --fail --silent http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Hello!"}],"max_tokens":32}'
```

Inference reads the saved checkpoint, not the trainer's in-memory weights. Restart
the chat process to load a newer checkpoint. The server binds to loopback by
default, serializes inference, bounds request size, and is a local development
service. It does not claim production authentication or public hosting.

To export the actual weights without the optimizer:

```sh
.venv/bin/python -m astheral.export
.venv/bin/python -m astheral.chat --checkpoint exports/astheral/weights.pt --tokenizer exports/astheral/tokenizer.json --prompt 'Hello!'
```

The export contains `weights.pt`, the trained `tokenizer.json`, and a manifest
recording SHA-256 checksums, exact parameter count, training step and real dataset
provenance. Exported checkpoints are inference artifacts; resume training using
the full checkpoint in `runs/astheral/latest.pt` instead.

## Architecture and validation

32 decoder blocks; width 1,024; 16 causal attention heads; SwiGLU feedforward width
2,816; RMSNorm; rotary position embeddings; tied input/output embeddings; maximum
512-token context. All 419,496,960 parameters are trainable. The training run uses
128-token windows to keep CPU iterations practical.

Tests exercise causal masking, gradient flow through all parameters, actual
optimization on a small configuration, checkpoint/optimizer round trips, context
limits, tokenizer Unicode round trips and the full architecture's parameter count.
The small optimization test is a software test, not evidence of full-size model
quality. The real full-size training run and its metrics provide that evidence.

See [DATA_SOURCES.md](DATA_SOURCES.md) for the official human-authored dataset,
reproducible revision, checksum, split, attribution and license.

For actual conversational evaluation run `.venv/bin/python -m astheral.evaluate`.
It generates new answers for greeting, identity, arithmetic, explanation and
context retention checks and saves the full answers to `runs/astheral/evaluations`.
These prompts are evaluation only; they are never used as training examples.
Review the answers themselves. The evaluator does not mark a checkpoint capable
just because it produces tokens. Generation uses real attention KV caching,
verified against full-prefix computation, to make these evaluations practical.

Assessments also measure prediction of existing held-out human answers across
eight Dolly categories. Only answer tokens contribute to this loss and accuracy;
system/user prompt tokens are masked. Input and answer truncation is reported.
These reference scores and identical-response diagnostics expose failure modes
that a falling overall training loss can hide. They do not replace inspection
of the actual generated conversations. No network service or external model is
used to produce or judge answers.
