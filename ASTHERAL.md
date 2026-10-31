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

Those original tested weights are preserved locally at `runs/astheral-conversation/selected-before-phrasing.pt`. The serving snapshot at `runs/astheral-conversation/selected.pt` has since advanced to step 3090; see [the recorded API reviews](reports/README.md). Chat, HTTP serving, and evaluation select that serving snapshot by default when it exists. Responses use greedy decoding by default. There is no response lookup, teacher call, or fallback in the inference path. `--checkpoint` still selects another explicit checkpoint.

This is a narrow learned capability. At that earlier checkpoint, `Please tell me your name.` elicited an unrelated cooking question, and an unfamiliar greeting introduced an incorrect name. Those failures are recorded in `runs/astheral-conversation/review.json`. The new step-3090 snapshot fixes those specific greeting/name and greeting/dinner exchanges and answers an introduction request; broad 25-turn coherence is still poor. The successful short exchanges do not establish broad competence.

Further training remains separate under `runs/astheral-short`, so it cannot overwrite the selected snapshot. To resume it after the machine stops:

```bash
.venv/bin/python -u -m astheral.conversation_train --output runs/astheral-short --source runs/astheral-conversation/latest.pt --lessons astheral/short_lessons.json --allow-lesson-change --lr 0.0003
```

The local checkpoint files are necessary to reproduce these answers; GitHub contains source and lessons, not these trained weights.

## Varied wording and 25-turn assessment

`astheral/phrasing_lessons.json` expands the synthetic teaching material to greetings, identity, food, music, books, hobbies, studying, writing, arithmetic, pets, and nearby conversation context. Previously reported failures such as `Please tell me your name.` are now teaching examples; they are regression cases, not unseen test data. Separate validation dialogues use different wording. Earlier short training dialogues are replayed; their old validation answers are not replayed.

The chat interface has no message-count cap. The expanded generation assessment runs **25 user turns (50 messages including replies)**. The model still has a 512-token context window: old complete user/assistant pairs are removed when necessary, while the system prompt, latest user message, and space for generation are preserved. The API reports `history_messages_dropped`; this is not a promise to remember all 25 turns at once. An individually oversized latest message produces a clear error rather than silent truncation.

```bash
.venv/bin/python -u -m astheral.conversation_train --output runs/astheral-general-chat --source runs/astheral-phrasing/latest.pt --lessons astheral/phrasing_lessons.json --replay astheral/short_lessons.json --context-replay --allow-lesson-change --reply-start-weight 5 --intent-weight 1 --lr 0.0003
.venv/bin/python -m astheral.conversation_eval --turns 25 --output runs/conversation-evaluation.json
.venv/bin/python -u -m astheral.conversation_watch
```

The evaluator uses each actual generated response as subsequent context and records all prompts, responses, timings, and context trimming. Keyword checks help locate failures but do not establish coherence. Read the actual transcript. Software tests use small models or explicit stubs only for unit testing; they are not conversational-capability evidence.

`--context-replay` adds a second view of self-contained training questions after other authored training histories. Only the final teacher answer is supervised; earlier context answers are masked. Validation dialogues are never used for these history examples. This addresses sensitivity to where a question occurs in a chat without changing inference into a scripted response system. Curriculum hashes, source data, and phase boundaries are retained in checkpoints.

`--reply-start-weight 5` assigns fivefold loss weight to the first three supervised answer tokens, focusing updates on reply selection as well as fluent continuation. This changes the objective, so its weighted loss must not be compared directly with the old unweighted loss. The earlier snapshot is preserved as `runs/astheral-general-chat/pre-weighted.pt`.

The watcher repeatedly assesses saved checkpoints in full 25-turn conversations and stores transcripts under `runs/astheral-general-chat/long-evaluations/`. It does not automatically select or publish a model based on keyword matches. A shorter rolling-history option is available to the evaluator as `--history-tokens`; experiments with that option do not change the chat default automatically.

An optional auxiliary topic head (`--intent-weight 1`) trains on coarse labels derived from teacher answers, such as identity, food, music, and books. Its input is the causal hidden state before the answer begins, so it cannot see the future teacher answer. The labels and head are used only during training; chat does not import the labeler, route by topic, or look up a response. The head and its optimizer state are retained for faithful training resumption. The generator remains the same 419,496,960-parameter Astheral model. The snapshot before this objective is retained as `pre-intent.pt`.

## Output-projection continuation

The cached training scheme freezes the input embeddings. In the original architecture those weights also perform output prediction, so the output projection is frozen too. The `--untie-output` trial copies Astheral's own embedding weights into a separate trainable output projection. It starts with identical logits and imports no external model weights. The resulting generator has 427,885,568 parameters and still uses the same input tokenizer and frozen-prefix cache. Old tied checkpoints remain readable.

```bash
.venv/bin/python -u -m astheral.conversation_train --source runs/astheral-general-chat/latest.pt --output runs/astheral-decoder --lessons astheral/phrasing_lessons.json --replay astheral/short_lessons.json --context-replay --allow-lesson-change --reply-start-weight 5 --intent-weight 1 --untie-output --lr 0.0003
.venv/bin/python -u -m astheral.conversation_watch --run runs/astheral-decoder
.venv/bin/python -m astheral.conversation_eval --url http://127.0.0.1:8000 --turns 25 --max-tokens 64 --output reports/astheral-25-turn-ui.json
```

This trial is separate from the selected serving checkpoint. Choosing a new checkpoint requires reviewing its actual exchanges. The HTTP test exercises the real server with the browser's 64-token reply budget. Keyword diagnostics use word boundaries and explicit stems; generic words such as `like` no longer count as evidence that a reply is about a cat. Raw responses remain the primary evidence.

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
