---
language: en
license: mit
library_name: peft
pipeline_tag: text-generation
base_model: Qwen/Qwen2.5-0.5B-Instruct
base_model_relation: adapter
---
# Astheral Flint

Locally trained security-assistant LoRA adapter from AstheralSec, intended for a broad commercial product. The original project and adapter contributions permit commercial use under MIT. The required Qwen base model remains separately licensed Apache-2.0; preserve its license and notices.

The revised training run completed on 2026-11-02 using an NVIDIA GeForce RTX 4060: 512 steps, 104 question forms covering 52 original answer intents, rank 4 on all linear layers, and 2,199,552 trained parameters. It kept two CPU threads, a 30% CUDA allocator cap, and a 20% active-step duty-cycle target. Peak PyTorch allocated VRAM was 1.99 GB (2.48 GB reserved); peak process RAM was 1.73 GB. Driver/context allocations and other applications are additional.

Normal chat merges this adapter into the frozen base weights during loading. Load with `chat.py` from the parent directory. The exact base revision, checksum, environment versions, dataset hash, and step losses are in `base_model.json` and `training_report.json`. This adapter requires the approximately 1 GB upstream base weights, which are not duplicated in this GitHub repository.

Intended tasks include secure coding, incident response, forensics, detection engineering, and authorized isolated-lab exercises. Chat does not execute generated commands. The separate fixed tool runner only accepts explicitly scoped loopback addresses and bounded connectivity/header checks.

The initial query/value-only run failed important development checks; its outputs and agent assessment remain under `reports/initial_*`. The revised run uses different development prompts. Release qualification remains pending the gates in `RELEASE.md`. This small corpus and development evaluation do not establish broad professional competence. Behavioral safeguards can fail; enforce lab isolation outside the model. No production certification or guarantee against abuse is claimed.

Current checkpoint status: the revised 0.5B model has 3 passes, 4 partial answers, and 5 failures in the development agent review. Commercial release is blocked by critical accuracy and authorization failures. See ../EVALUATION.md and ../reports/qwen05_all_linear_review.json. A user-authorized 1.5B replacement is being evaluated separately.
