# Astheral Flint

**Status:** The current 0.5B checkpoint failed accuracy and authorization checks. Commercial release is blocked. See EVALUATION.md. Qwen2.5-1.5B is being evaluated as a replacement.

AstheralSec's local security assistant, intended for a broad commercial product: secure coding, incident response, forensics, detection engineering, and authorized isolated-lab testing.

The software and original training examples are free under the MIT license. The base model is Qwen2.5-0.5B-Instruct, licensed Apache-2.0. Commercial use is permitted under these licenses; this does not establish production readiness, safety certification, trademark clearance, or fitness for a specific deployment. Preserve the applicable notices when distributing components.

## Install and run on Windows

Requires Python 3.13 and at least 16 GB free disk during the first CUDA setup and parallel download. The first run downloads the pinned base model, approximately 1 GB. Internet is unnecessary for subsequent inference once cached.

```powershell
cd AstheralSec
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.11.0+cu128 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe chat.py --device cuda "Show a safe SQLite parameterized lookup."
```

CPU inference is also available with `--device cpu`; no paid API or account is required. Never pipe model output into a shell. This chat client does not execute commands or connect generated text to tools.

## Resource limits and training

Current runtime settings are in resource_policy.json: four compute threads, a 65% CUDA allocator cap, and a 60% active-compute duty-cycle target. The job leaves at least 8 GiB available system RAM and 1.5 GiB free VRAM when sampled, pauses when host CPU load exceeds 85% or GPU temperature reaches 78 C, and stops if its sampled process RAM exceeds 8 GiB. Checks are periodic rather than operating-system isolation; driver allocations and other applications are additional. Windows compute processes run at below-normal priority.

The existing 0.5B training reports record the older two-thread, 20% duty-cycle settings actually used. Current defaults do not rewrite those historical measurements.

The training entry point accepts a pinned base lock, dataset, output folder, learning rate, rank, targets, and resume options. Defaults are 128 steps, rank-8 query/value LoRA, learning rate 0.00002, batch size 1, and at most 512 tokens. Oversized answers are rejected rather than silently truncated. Checkpoints preserve the adapter, optimizer, RNG state, and sample ordering; they remain local under .checkpoints/ and are excluded from Git. Successful root training refreshes artifact checksums.

Run python train.py --help for parameters. The existing root checkpoint remains unqualified. The authorized 1.5B candidate can be restored with python prepare_base.py --lock candidates/qwen15/base_model.json and evaluated with python evaluate_base.py --lock candidates/qwen15/base_model.json --output candidates/qwen15/baseline_evaluation.json before choosing a training run. Candidate outputs are kept separate from the existing checkpoint.

The dataset contains 104 question forms covering 52 original synthetic answer intents. It is too small to establish broad professional competence. The development evaluation contains separate prompts and review criteria; test-informed model selection is not an independent benchmark. The exact base revision, raw and canonical dataset hashes, runtime versions, and measured usage are recorded in reports. Text hashes normalize line endings for portable recovery; binary weights use their original bytes.

## Practical lab tools

The deterministic runner performs bounded TCP connectivity checks and HTTP HEAD inspection. It only accepts explicitly scoped loopback IP literals, checks at most eight approved ports, uses short timeouts, and never follows redirects. It has no shell execution or arbitrary plugin interface.

```powershell
Copy-Item lab.example.json lab.local.json
# Edit lab.local.json: confirm authorization and list your own local lab ports.
.\.venv\Scripts\python.exe lab_tools.py ports --scope lab.local.json --ports 8000
.\.venv\Scripts\python.exe lab_tools.py headers --scope lab.local.json --ports 8000
```

The model can also help design local CTF exercises, review code, write remediation tests, and interpret supplied logs. Tool results are evidence; model prose is advice. The tool runner is separate from chat and never executes generated instructions. Private network space is not automatically authorized. Broader automated network access requires a separately reviewed sandbox, verified scope, and egress enforcement.

## Safeguards and release qualification

Training and the system prompt discourage malware deployment, credential theft, evasion, destructive attacks, and weapons. These are behavioral measures, not an unbreakable control. Exported open weights can be modified, and generated code can be copied elsewhere. No open-weight model can guarantee that another person will not abuse it.

For executing lab exercises, use a disposable VM with denied external egress, invented accounts and data, no shared secrets, minimal privileges, and a clean snapshot. Loopback tools alone do not establish that a forwarded local service is an isolated lab.

Before selling this as a production security product, complete the documented release gates in RELEASE.md. `training_report.json` records the actual local training; `evaluation_report.json` records base-versus-adapter answers for human review. Loss reduction and unit tests do not establish capability or safety. No external certification is claimed.

## Recovery without this conversation

Clone the GitHub repository and enter `AstheralSec`. The source, dataset, pinned base revision, trained adapter files under `weights/`, and reports are the durable project record. The adapter stores the learned weight changes; inference also requires the exact base model in `base_model.json`.

The approximately 1 GB upstream base weights are downloaded from Hugging Face rather than duplicated in Git. Keep your local Hugging Face cache for offline recovery. This repository alone therefore does not provide an independent archive of the upstream base weights. The adapter must never be represented as a standalone foundation model.

See RESEARCH.md for source links and design choices.
