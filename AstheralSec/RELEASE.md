# Commercial release gates

Target product: a broad local security assistant for professional users. Commercially compatible licensing is a distribution property, not evidence of professional capability.

The first local training run is a development checkpoint for this commercial product. Do not market it as production-qualified until the following work has evidence and an accountable reviewer has approved it:

- A representative, independently reviewed evaluation across secure coding, lab testing, response, forensics, and detection engineering. Use materially more than the twelve included prompts and evaluate tasks with executable correctness checks where possible.
- Human grading of harmful request refusals, legitimate dual-use assistance, prompt injection, scope ambiguity, and false refusals. Require no critical harmful completions in the release suite; also report uncertainty and known gaps rather than claiming this proves safety.
- Comparison with the unchanged base model on held-out tasks. Require no material regression and evidence that the adapter improves the intended tasks. Publish the rubric, sample sizes, outputs, and failure cases.
- A larger reviewed corpus with documented provenance, redistribution rights, deduplication, and no customer secrets. Revalidate resource use and quality after every dataset or base-model change.
- Sandbox and egress review for any future execution feature. Model text must never authorize tools, widen target scope, or invoke an unrestricted shell.
- Dependency and artifact integrity review, privacy and retention documentation, packaging and clean-machine recovery testing, model/base license notices, and incident/update ownership.
- Explicit deployment-specific risk acceptance by the product owner and qualified security reviewers.

Status must be determined from actual evidence. No certification, independently verified expertise, or guaranteed non-abusability is implied by the product name or commercial-use license.
