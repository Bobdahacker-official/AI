# GenericDataset card

## Editorial policy

Each JSONL record in this release is fixed text written individually for this repository. New records must be written as new content, reviewed for wording and technical correctness, and added directly to the relevant JSONL file. Automated expansion, templated permutations, copied public corpora, and model-generated bulk text are not part of this dataset.

The collections are licensed for commercial use under CC0-1.0. They are concise, curated seeds for product teams that want clear provenance and can extend the files with their own reviewed material.

## Schemas

Stories: `id`, `title`, `text`, `tags`, `license`.

Conversations: `id`, `messages`, `tags`, `license`; messages alternate `user` and `assistant`.

Info: `id`, `domain`, `question`, `answer`, `license`.

Coding: `id`, `language`, `prompt`, `code`, `tags`, `license`.

Assembly examples use NASM x86-64 syntax. `JS` is ECMAScript, and `TYPESCRIPT` uses TypeScript syntax.
