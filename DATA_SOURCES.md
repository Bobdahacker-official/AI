# Astheral training data

Astheral uses **Databricks Dolly 15k**, copyright 2023 Databricks, Inc.,
including Wikipedia material copyright Wikipedia editors and contributors.
The dataset is licensed under [CC BY-SA 3.0 Unported](https://creativecommons.org/licenses/by-sa/3.0/legalcode).
Preserve attribution and comply with the dataset license when redistributing
data or adaptations. Source code and dataset licensing are separate.

Research sources inspected during implementation:

- [Official project README](https://github.com/databrickslabs/dolly/blob/e2d664ddf06e0723d818dc56d6c522ead4bd881d/README.md).
- [Official dataset card and attribution](https://github.com/databrickslabs/dolly/blob/5f9bfba300181fb35854d64c8bf1180ea75105f7/data/README.md).
- [Pinned official dataset](https://raw.githubusercontent.com/databrickslabs/dolly/5f9bfba300181fb35854d64c8bf1180ea75105f7/data/databricks-dolly-15k.jsonl).

The current GitHub repository moved its data to Hugging Face. That host returned
HTTP 403 in this environment. The official historical GitHub release remains
accessible through the managed HTTPS proxy, using elevated execution when the
sandbox cannot connect to `proxy:8080`. No model weights were downloaded.

Expected dataset SHA-256:
`e442d96b320010510c67a6cc0a86ea988a2a6f71c7570d1afbdf4fa631896e58`.

The downloaded release has 15,014 records. We remove 15 exact duplicates and split
whole formatted records deterministically by SHA-256 before fitting the tokenizer.
There are 14,707 training records and 292 validation records. Byte-level BPE is
trained only on training records, with an 8,192-token vocabulary. Packing yields
3,412,886 training tokens and 57,903 validation tokens. Existing instruction,
context, and response content is retained. The Astheral identity system message
and role delimiters are serialization, not fabricated response examples.

This is an instruction dataset, not a broad language pretraining corpus. The
checkpoint's general language and assistant ability must be assessed from real
generation and held-out metrics. Parameter count alone does not establish either.

## Human multi-turn conversations

Continued training adds [Google Taskmaster-1](https://github.com/google-research-datasets/Taskmaster/blob/d92cb6af3005f1dc09c39e75e7daf4a04905e00b/TM-1-2019/README.md),
the work of Bill Byrne, Karthik Krishnamoorthi, Chinnadhurai Sankar, Arvind
Neelakantan, Amit Dubey, Kyu-Young Kim and Andy Cedilnik from Google LLC, released
under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

The actual existing `self-dialogs.json` and `woz-dialogs.json` files are pinned to
official revision `d92cb6af3005f1dc09c39e75e7daf4a04905e00b`. SHA-256 checksums:

- self-dialogs: `1e590ed0ccee279e40c2fb9e083d3b9417477c6bfe35ce5b2277167698dd858d`
- woz-dialogs: `cd3bc4e968487315d412c044d30af2bf0a4b33c3ef8b74c589f1e1fa832bf72f`

`python -m astheral.corpus` verifies those files, preserves existing utterances and
speaker roles, removes 10 duplicate conversations and excludes 13 conversations
with ambiguous speaker labels. It never invents missing roles or answers. Whole
conversations are split by content hash; individual turns do not cross partitions.
The combined corpus has 27,656 training records (8,285,208 tokens) and 535 validation
records (151,287 tokens). It reuses Astheral's independently trained original BPE
tokenizer so its existing model and optimizer can continue without remapping IDs.

Taskmaster contains task-oriented dialogue, including simulated bookings and
orders written by human contributors. Its text does not connect Astheral to
reservation, payment, or ordering systems. These examples improve dialogue
coverage but are not evidence of factual accuracy or useful assistant behavior.

## Broader dialogue source investigated, not ingested

The official [Anthropic HH-RLHF corpus](https://github.com/anthropics/hh-rlhf/tree/c72f5cee8eb7b4d2ea5617657f4430d5e333af07)
was inspected as a broader conversation source. Its repository license is MIT,
copyright 2022 Anthropic. Its preferred responses are **model-generated and
human-ranked**, unlike the human-written Dolly and Taskmaster records used so
far. Downloading this recorded text would not import any pretrained model weights
or invoke a teacher API.

The checked-out `.jsonl.gz` files are Git LFS pointers, not downloaded datasets.
They were detected and rejected rather than used as training data. `git lfs pull`
returned `Resource not accessible by integration`. The official public download
redirected to `media.githubusercontent.com`, where the managed proxy denied the
CONNECT request with HTTP 403. The live policy did not allow that hostname.

The exact hostname addition was saved in the environment configuration draft,
preserving the existing package-manager presets. It was not active in the running
instance at the last check. A real download and checksum verification remain
pending that network change; no HH-RLHF content has been added to Astheral's
training corpus. The pointer for `helpful-base/train.jsonl.gz` declares expected
object SHA-256 `518a5bf288456fc9f3b7c980c54116fba0c52f274d3f4d344675d83e4058f6f4`
and size 16,200,131 bytes. That object has **not** yet been downloaded or verified.

Stanford Alpaca's official documentation was also inspected. Its dataset is
research-only/noncommercial (CC BY-NC 4.0), so it was not introduced as a fallback
that would narrow Astheral's data-reuse options.
