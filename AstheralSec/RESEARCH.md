# Research and architecture record

Reviewed 2026-11-02. These are architecture and scope references; no scraped source text is included in the training corpus.

- Qwen model card: https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct — approximately 0.49 billion parameters, Apache-2.0, supported by Transformers. Chosen for the user's low-resource requirement. Larger models may be more capable, but no model change was made to shorten download time.
- LoRA documentation: https://huggingface.co/docs/peft/package_reference/lora — freeze base weights and train small low-rank updates. Rank 4 on query/value projections keeps learned artifacts small and directly archivable in GitHub.
- PEFT checkpoint format: https://huggingface.co/docs/peft/developer_guides/checkpoint — adapter checkpoints require the original base model. This is why the exact upstream revision is pinned and recovery instructions explicitly describe the dependency.
- PyTorch installation: https://pytorch.org/get-started/locally/ — CUDA support requires a CUDA-enabled build. The initially installed PyTorch was CPU-only, so a separate CUDA build is installed inside the project environment.
- OWASP Web Security Testing Guide: https://owasp.org/projects/web-security-testing-guide — a scope reference for practical web-security testing. Original synthetic examples cover access control, injection prevention, session handling, evidence, and regression testing. No OWASP guide text was copied into the dataset.

No claim is made that this small fine-tune exceeds its base model or commercial security assistants. The included evaluation records actual outputs for review instead of substituting training loss for a capability benchmark.

## Revision after observed failures

The initial query/value-only rank-4 run failed seven of twelve development cases, with four partial answers and one pass in an agent review. The raw outputs and review are retained under `reports/initial_*`; they are not an independent human assessment.

The revised run retains the exact base revision and resource caps, uses rank-4 adapters on all linear layers and a 0.0002 learning rate, and trains 104 question forms covering the same 52 original answer intents. This is broader adapter placement, not a change of foundation model. A different set of development prompts checks the same functional areas. The adapter is merged into the frozen base weights for normal chat inference; evaluation tests that same loading path after recording the unchanged-base outputs.

This iteration is informed by failed development tests. Neither lower training loss nor passing these small development checks would establish commercial production readiness.
