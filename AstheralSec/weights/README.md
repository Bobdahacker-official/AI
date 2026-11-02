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

Training completed on 2026-11-02 using an NVIDIA GeForce RTX 4060: 256 steps, 52 original synthetic examples, rank 4 on query/value projections, and 270,336 trained parameters. Training used two CPU threads and a 20% active-step duty-cycle target. Peak measured PyTorch allocated VRAM was 1.71 GB (2.47 GB reserved); peak process RAM was 1.73 GB. Driver/context allocations and other applications are additional.

Load with `chat.py` from the parent directory. The exact base revision, checksum, environment versions, dataset hash, and step losses are in `base_model.json` and `training_report.json`. This adapter requires the approximately 1 GB upstream base weights, which are not duplicated in this GitHub repository.

Intended tasks include secure coding, incident response, forensics, detection engineering, and authorized isolated-lab exercises. The chat client does not execute generated commands. The separate fixed tool runner only accepts explicitly scoped loopback addresses and bounded connectivity/header checks.

The small training corpus and a successful training run do not establish broad professional competence. Release qualification is pending the gates in `RELEASE.md`. Behavioral safeguards can fail; enforce lab isolation outside the model. No production certification or guarantee against abuse is claimed.
