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
