# Astheral execution evidence

Recorded on 2026-10-31 in the actual cloud machine. This is an intermediate
training report, not a declaration that assistant training has converged.

## Real model and data

- Parameters: **419,496,960**, measured on both the allocated full model and an
  independent architecture instantiation.
- Initialization: random; no base-model weights or pretrained tokenizer loaded.
- Runtime: PyTorch 2.10.0+cpu, bfloat16 autocast, FP32 AdamW state.
- Hardware: four CPU cores, 32 GiB memory, no exposed NVIDIA accelerator.
- Dataset: the existing Databricks Dolly 15k release; attribution and exact source
  are in DATA_SOURCES.md. Tokenizer fitted only on its training partition.

## Observed full-size training

The real trainer completed backward passes and optimizer steps on the full
419-million-parameter model. Two fixed held-out 128-token windows were measured
at each validation; this small sample is not a broad assistant evaluation.

| Step | Tokens processed | Held-out cross-entropy |
| ---: | ---: | ---: |
| 0 | 0 | 9.2280015945 |
| 10 | 1,280 | 8.5501079559 |
| 20 | 2,560 | 8.1836743355 |
| 30 | 3,840 | 8.0502421856 |
| 40 | 5,120 | 7.8370041847 |
| 43 | 5,504 | 7.8192706108 |
| 50 | 6,400 | 8.0855827332 |

Training remains active with no configured step/time limit. Live evidence is in
`runs/astheral/metrics.jsonl`, `runs/astheral/training.log`, and
`runs/astheral/status.json`. The last file describes the latest durable checkpoint,
which may lag current optimizer steps. Loss fluctuates; this report does not
claim monotonic improvement.

A graceful checkpoint/restart was exercised on the full-size model at step 43.
The new detached process loaded model, optimizer, and RNG state, reported the
same held-out loss, and continued at step 44. The manager's actual process lock
confirmed the resumed process remained active after its launcher exited.

## Exported weights

`exports/astheral/weights.pt` contains real trained FP32 tensors from step 43,
approximately 1.6 GiB, without optimizer state. Its SHA-256 is:

`5ef5b790871f1381b46efa9de2c5a92e4d4879f1fa7c035bf3e4748009193652`

The tokenizer checksum is:
`c4bc708c6efb1c202707ad2836ab8f35f9d643cfa0cd910765bd40ee5b9cfcbd`.
The adjacent manifest captures its dataset provenance and exact measured step.
The ongoing trainer writes the separate full checkpoint, approximately 4.7 GiB.
These binary artifacts are retained on the workspace filesystem and intentionally
excluded from the source Git commit; preserve the filesystem to retain them.

## Validation and remaining quality gap

All seven tests passed. They exercise causal attention, every small-model
parameter's gradients, measured optimization, checkpoint/optimizer round trip,
context limits, exact full-size parameter count, conversation serialization, and
Unicode tokenizer round trip.

The live HTTP server loaded the full-size trained checkpoint. Its health route
reported the correct parameter count and step. POST /chat generated actual tokens;
an invalid request returned HTTP 400. Standalone CLI inference and exported-weight
inference also completed. Example greedy generation from the step-20 checkpoint
for “Hello, Astheral!” was `,,,,,,,,`. This demonstrates inference execution and
also demonstrates that conversational quality has **not** been achieved at this
stage. No canned replacement answer was substituted.

The implementation, dataset processing, full-size training, checkpoint recovery,
export, CLI, and local web interface are working. Training toward a useful
friendly assistant remains ongoing. Runtime processes end if the cloud machine
is shut down; resume from disk with `python -m astheral.manage start` using the
prepared virtual environment.
