# Astheral Flint

AstheralSec's local security assistant, intended for a broad commercial product: secure coding, incident response, forensics, detection engineering, and authorized isolated-lab testing.

The software and original training examples are free under the MIT license. The base model is Qwen2.5-0.5B-Instruct, licensed Apache-2.0. Commercial use is permitted under these licenses; this does not establish production readiness, safety certification, trademark clearance, or fitness for a specific deployment. Preserve the applicable notices when distributing components.

## Install and run on Windows

Requires Python 3.13 and at least 12 GB free disk during the first CUDA setup and parallel download. The first run downloads the pinned base model, approximately 1 GB. Internet is unnecessary for subsequent inference once cached.

```powershell
cd AstheralSec
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.11.0+cu128 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe chat.py --device cuda "Show a safe SQLite parameterized lookup."
```

CPU inference is also available with `--device cpu`; no paid API or account is required. Never pipe model output into a shell. This chat client does not execute commands or connect generated text to tools.

## Resource limits and training

```powershell
.\.venv\Scripts\python.exe build_data.py
.\.venv\Scripts\python.exe train.py --device cuda --steps 256 --duty-cycle 0.20
.\.venv\Scripts\python.exe evaluate.py --device cuda
.\.venv\Scripts\python.exe -m unittest -v test_project.py
```

Training uses batch size 1, at most 384 tokens, rank-4 query/value LoRA, two CPU intra-operation threads, and one inter-operation thread. The CUDA allocator is capped at 30% of device memory (approximately 2.4 GB on an 8 GB GPU). This cap excludes driver/context and other processes. Training sleeps for four times each active step's duration at a duty cycle of 0.20. This reduces average activity, but does not cap instantaneous GPU utilization. Stop with Ctrl+C; completed training writes the adapter and report. This script starts a fresh run rather than resuming optimizer state.

The dataset contains 52 original synthetic instruction pairs. The evaluation set contains 12 separate prompts and review criteria. These are a starting corpus, not sufficient evidence of broad professional competence. The fine-tune adapts an existing pretrained model; it does not train a foundation model from scratch. Public web sources informed architecture and scope; their contents were not scraped into training data.

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
