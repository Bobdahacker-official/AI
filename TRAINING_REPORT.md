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

Further uninterrupted training reached durable step 150 (69,376 processed
tokens), with combined-corpus validation cross-entropy 5.9013044834. The live
trainer process was kept running while evaluation was improved. A stale
step-20 inference server was shut down to release its old weight mappings;
the trainer and recurring evaluator were not stopped.

Answer-only evaluation was added using eight existing held-out Dolly records,
one per category, with 634 labeled answer tokens in total. Prompt and system
tokens are excluded, and truncation is disclosed for each record. Results:

| Checkpoint | Answer cross-entropy | Answer perplexity | Answer-token accuracy |
| ---: | ---: | ---: | ---: |
| 125 | 7.4242120496 | 1676.0784 | 5.5205% |
| 150 | 7.1254100619 | 1243.1578 | 4.7319% |

The step-150 answers remain unsuitable. It answers several unrelated questions
with `Yes, a friendly, a friendly, helpful and honest AI assistant.` Lower
answer loss alongside lower token accuracy is mixed evidence, not a passed
conversational assessment. Later assessments also report identical-response
counts to make failure to condition on questions visible. All 13 software tests
passed after adding answer-label masking and context-cropping checks. No canned
responses, pretrained weights, or externally generated training records were
introduced. Training continues toward the still-unmet conversational goal.

## Uninterrupted main run and response-supervision pilot

The original trainer, PID 2716, was kept running during subsequent work, including
the reported environment reconnection. It reached durable step 200 with 120,576
processed tokens and combined-corpus validation loss 5.6596539021. Its direct
conversation answers still fail: for example, the arithmetic answer is
`H, how you like you like you?`. Its eight-record answer-only cross-entropy was
6.9396332942 and token accuracy 4.7319%. This is not a capable assistant.

A concrete alternative was implemented and exercised without stopping that
run. Existing role delimiters produce assistant-only loss masks, with source
array and tokenizer verification. These masks label 3,785,395 existing training
tokens and 70,809 validation tokens; they do not invent responses. All 15 tests
passed, including exclusion of system/user text and correct assistant-end labels.

Two separate full-size continuations started from Astheral's own pinned step-175
checkpoint. Each took ten optimizer updates on the same ten 512-token windows,
using batch 1, two CPU threads and the same learning rate. Their final checkpoint
RNG states, dataset fingerprints, architecture, step 185 and 100,096 inherited-plus-
processed token counters match. Deterministic replay found no resampling and
2,113 assistant answer labels across those windows. The two runs are independent;
their step counts must not be added together or added to the main run's count.

The same 634 answer tokens from eight existing held-out human records were scored:

| Model | Answer cross-entropy | Answer-token accuracy |
| --- | ---: | ---: |
| Shared source, step 175 | 6.9203478696 | 5.9937% |
| All-target control, step 185 | 6.9723233485 | 4.8896% |
| Assistant-target trial, step 185 | 7.0029915410 | 7.7287% |

The trial's accuracy increased, but its loss worsened and its actual answers were
still wrong or repetitive. This small pilot does not establish a conversational
improvement. The ongoing main run was therefore left on its existing strategy.
The optional supervised-response implementation and real trial artifacts are
retained for later experiments, not presented as a successful trained assistant.
Trial checkpoints and full answer reports are under
`runs/astheral-assistant-trial/` and `runs/astheral-all-targets-control/`.

## Later checkpoints and the broader-corpus access blocker

The same main trainer remained active through durable step 250, with 171,776
processed tokens and combined-corpus validation loss 5.4402513504. Its answer-only
reference loss was 6.8170437016. Actual generation still fails: it answered the
arithmetic question with `TheYou are Astheral, a friendly, helpful and honest AI assistant.`
This is recorded failure evidence, not conversational readiness.

Broader assistant-dialogue data was researched to address the narrow ordering
style emerging from Taskmaster. The official HH-RLHF repository was cloned, its
license inspected, and its Git LFS pointer files rejected as non-data. LFS access
failed at the integration endpoint. Diagnostic HEAD requests confirmed that the
official public download redirected to `media.githubusercontent.com` and the
proxy rejected that destination with HTTP 403. The live environment policy
remained revision 1, enforced, without that hostname after a draft-only addition
was saved. The broader corpus is not downloaded, verified, tokenized or trained
on. DATA_SOURCES.md records exact provenance and the observed blocker.

The current verified-data trainer and recurring evaluator continue running with
no configured step/time limit. A dataset-access problem did not terminate the
run, reset its weights, or cause placeholder data to be substituted. The saved
network draft is separate from runtime application and publication.

## Broader data downloaded, verified, and used for actual training

The environment's network policy later advanced to revision 2 with the media
hostname allowed. The former trainer/evaluator processes had ended during that
update. Its log reached step 275, but only step 250 was durable; those 25 unsaved
updates were lost. Recovery resumed the real step-250 checkpoint and recomputed
subsequent updates. Duplicate metric step numbers across that recovery must not
be summed as additional model progress.

The official public GitHub download route then delivered all six HH helpful
train/test objects. Their actual byte lengths and SHA-256 hashes match the pinned
publisher's LFS declarations. Gzip records were decoded and parsed; pointer files
were never substituted for data. The MIT notice is retained with the source.

The actual prepared corpus now has 119,692 training records / 34,343,893 tokens
and 6,503 validation records / 1,912,231 tokens, using Astheral's original tokenizer.
Root grouping, protected evaluation prompts, exclusion of previously trained
validation roots and source hashes are documented in DATA_SOURCES.md. The corpus
builder asserted zero shared train/validation prompt roots, and the real packed
arrays were checked for expected lengths, uint16 dtype and vocabulary bounds.

The original-data continuation saved all progress through step 302 / 225,024
processed tokens. A normal checkpoint handoff then continued those exact model
weights and AdamW state on the broader corpus. The previous phase is recorded
through step 302 in `data_history`. The new corpus baseline loss was 5.8876216412;
at step 310 it was 5.7366209030, and at step 330 it was 5.5860638618. These scores
are comparable within this new phase, not against earlier-corpus losses.

Answer-only loss on the fixed eight Dolly references was 6.6708998815 at step 310
and 6.5065301360 at step 330. Actual generated answers still fail conversational
checks. The model is **not** claimed capable or finished. Training continues with
all 419,496,960 parameters, batch 2, context 512, four CPU threads and BF16 autocast.

Checkpoint intervals are now ten steps to reduce unsaved-work loss. Manager
startup restores the corpus and training settings from the actual checkpoint,
excluding transient data-change permissions and finite experiment limits.
Corpus transitions save their new baseline before subsequent updates. All 22
software tests passed after parser, root grouping and corpus-resume checks were
added. Downloader repeatability was exercised against all six verified cached
objects without fetching model weights or re-creating training answers.

A separate real step-125 weight export is retained at
`exports/astheral-step125/weights.pt`, with SHA-256:
`3f93659e66aafae83f00b3bb8fa90fc7642599e55f21ce0991fac2fef1768639`.
The original step-43 export described above remains intact. Model exports and
resumable checkpoints remain filesystem artifacts, not source Git objects.
