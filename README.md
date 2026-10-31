# GenericDataset

GenericDataset is a ready-to-use collection of original training examples for commercial language-model and assistant products. Every record in this repository was created locally from scratch by the included deterministic builder. It contains no downloaded corpus, copied benchmark, pretrained-model output, or third-party dataset material.

The three general-purpose collections each provide `Minimal`, `Balanced`, and `Big` editions:

| Collection | Intended content | Total examples per edition |
| --- | --- | ---: |
| `GenericStories` | Short original fiction with metadata | 60 / 300 / 1,200 |
| `GenericConversations` | Helpful multi-turn assistant dialogues | 60 / 300 / 1,200 |
| `GenericInfo` | Original questions and explanatory answers | 60 / 300 / 1,200 |

`GenericCoding` contains original prompt-and-solution JSONL datasets for `Mixed`, `Python`, `C++`, `C`, `Assembly`, `HTML`, `CSS`, `JS`, `RUST`, `PHP`, and `TYPESCRIPT`. Each language edition has 200 records; `Mixed` has 400 records.

Every edition has `train.jsonl`, `validation.jsonl`, `test.jsonl`, and `metadata.json`. The splits are deterministic and use an 80/10/10 split. `GenericDataset/manifest.json` records file paths, record counts, and SHA-256 digests for reproducibility.

```python
import json

with open("GenericStories/Balanced/train.jsonl", encoding="utf-8") as handle:
    examples = [json.loads(line) for line in handle]
```

The schemas, generation policy, validation checks, and recommended uses are in [GenericDataset/DATASET_CARD.md](GenericDataset/DATASET_CARD.md). Rebuild the exact dataset with:

```bash
python3 GenericDataset/build.py
```

The dataset content is dedicated to the public domain under CC0-1.0. The builder is released under the MIT license; see [LICENSE.md](LICENSE.md).
