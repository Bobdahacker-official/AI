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

## Continued training and direct quality assessment

The requested conversational outcome remains **unachieved**. Further work after
the initial implementation increased CPU training windows to 512 tokens with
batch size 2, preserved the original trained tokenizer, and added existing human
multi-turn conversations from Google Taskmaster-1. See DATA_SOURCES.md for
verified official revisions, licenses, filtering and counts. The combined corpus
contains 8,285,208 training tokens. No pretrained model was introduced.

The original run saved at step 102 (20,224 processed tokens). Continuing that
same model and optimizer on the verified new corpus recorded the old corpus in
checkpoint `data_history`. Its first combined-corpus validation loss was
6.6445560455; at durable step 125 it was 6.1851220131, with 43,776 total processed
tokens. These combined-corpus validation numbers use different records and
window sizes from the initial report and cannot be directly compared to its
Dolly-only validation values.

The step-125 checkpoint contains AdamW state for all 226 parameter tensors,
including optimizer step counters of 125. Measured full-model CPU throughput
increased from roughly 38 tokens/second to roughly 54 tokens/second before
validation/checkpoint overhead. All 11 software tests passed, including exact
full-prefix versus incremental attention-cache comparisons and protection of
the running trainer's process lock. No passing software test certifies assistant
quality.

Actual five-case generation assessments were completed at steps 100 and 125.
Both fail conversational evaluation. For example, the step-125 answer to
“What is your name?” begins `I, a friendly, a a a...` and devolves into repeated
words. Greeting, arithmetic, explanation and context-retention checks also
produce irrelevant/repetitive answers. The complete actual outputs remain in
`runs/astheral/evaluations/step-100.json` and `step-125.json`.

Training continues without a step or time cap. A separately running recurring
evaluator assesses later saved checkpoints every 25 steps and records answers
without manufacturing a success verdict. Both processes are visible through
`python -m astheral.manage status`. They continue independently of a chat reply
while the machine remains running. Their startup instructions were saved in
the environment draft; this does not establish publication or a new-machine
restoration test.

A separate real step-125 weight export is retained at
`exports/astheral-step125/weights.pt`, with SHA-256:
`3f93659e66aafae83f00b3bb8fa90fc7642599e55f21ce0991fac2fef1768639`.
The original step-43 export described above remains intact. Model exports and
resumable checkpoints remain filesystem artifacts, not source Git objects.
