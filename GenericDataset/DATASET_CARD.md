# GenericDataset card

## Origin and scope

All dataset records are original local work. `build.py` does not connect to a network, read a source corpus, call a model, or import external data. It combines self-authored narrative, dialogue, information, and code components with a fixed seed, then writes complete JSONL files. The committed JSONL is therefore usable without running the builder.

The collections are designed for commercial model development, product prototyping, parser tests, curriculum exercises, and training workflows. They are not a substitute for independently verified factual, safety, legal, medical, or production-code sources.

## Record formats

`GenericStories` records contain `id`, `title`, `text`, `genre`, `themes`, `reading_level`, `word_count`, and `license`.

`GenericConversations` records contain `id`, `topic`, `skills`, `messages`, and `license`. `messages` is an ordered list of `{role, content}` objects and alternates user and assistant turns.

`GenericInfo` records contain `id`, `domain`, `difficulty`, `question`, `answer`, `keywords`, and `license`.

`GenericCoding` records contain `id`, `language`, `prompt`, `code`, `tags`, `difficulty`, and `license`. Assembly uses NASM x86-64 syntax. `HTML` and `CSS` are standalone markup and style snippets. `JS` is modern ECMAScript, and `TYPESCRIPT` uses standard TypeScript syntax.

## Splits and validation

Minimal, Balanced, and Big general collections contain 60, 300, and 1,200 records respectively. Each uses 80% training, 10% validation, and 10% test records. Language editions contain 200 records, while Mixed contains 400, with the same split ratio.

The builder validates JSON syntax, exact split counts, unique record IDs, required fields, absence of placeholders, and Python syntax for Python examples. It writes SHA-256 digests and record counts to `manifest.json` after validation.

## Content policy

The dialogue records model clear, respectful, bounded assistance. The information collection emphasizes arithmetic, unit reasoning, everyday science, algorithms, and practical explanations. Code examples focus on small, readable utilities with original identifiers and comments. No third-party source, scraped text, benchmark answer, or pretrained-model output was used.
