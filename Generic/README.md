# GenericDataset

GenericDataset is an original, fixed editorial dataset for commercial language-model and assistant products. Every record is individually authored in its JSONL file. There is no generation script, source corpus, scraped material, benchmark answer, or third-party dataset behind these files.

`GenericStories`, `GenericConversations`, and `GenericInfo` each have `Minimal`, `Balanced`, and `Big` folders. `GenericCoding` has `Mixed`, `Python`, `C++`, `C`, `Assembly`, `HTML`, `CSS`, `JS`, `RUST`, `PHP`, and `TYPESCRIPT` folders. Each folder is directly usable JSONL, with no preprocessing required.

```python
import json

with open("GenericStories/Balanced/records.jsonl", encoding="utf-8") as handle:
    examples = [json.loads(line) for line in handle]
```

The schemas, commercial-use policy, and editorial rules are in [GenericDataset/DATASET_CARD.md](GenericDataset/DATASET_CARD.md).

The dataset content is dedicated to the public domain under CC0-1.0. The builder is released under the MIT license; see [LICENSE.md](LICENSE.md).
