# Runbook

Step-by-step instructions for reproducing run 1, with what to check at each step. For the findings, see the [README](README.md) or the [results page](https://abh2050.github.io/private-inference-on-intel/).

## Versions

| Component | Version |
|---|---|
| `intel/enterprise-ai-solutions` | v1.1.0 |
| `intel/enterprise-inference` | v1.0.1 (`5d92bef`), pinned by the line above |
| vLLM CPU | 0.24.0 (from the model catalog) |
| Models | `Qwen/Qwen3-0.6B` (catalog name `qwen3-0-6b`) and `Qwen/Qwen2.5-3B-Instruct`; both public, no Hugging Face token needed |
| Server | IBM Cloud `bx3d-32x160`, us-east-1, Ubuntu 24.04 |

## Cost safeguards

1. `02-provision.sh` refuses to run without `CONFIRM=yes`.
2. A watchdog deletes every `opea-ei-*` resource after `MAX_HOURS` (default 4, set in `env.sh`). It runs on the operator's workstation, so it stops if that machine sleeps.
3. `bx3d` profiles include local instance storage, and IBM keeps billing them while stopped. Delete the server; do not just stop it.
4. `99-teardown.sh` ends with a leftovers check that must report zero for every resource type.
5. Set spending notifications in the IBM console under Manage → Billing and usage.

Run 1 used 1.49 server-hours, about $3.

## Steps

```bash
# One-time setup
curl -fsSL https://clis.cloud.ibm.com/install/osx | sh     # or the Linux installer
ibmcloud login --sso
ibmcloud plugin install vpc-infrastructure -f

./01-preflight.sh                   # 1. read-only checks
CONFIRM=yes ./02-provision.sh       # 2. create the server
./03-run-remote.sh                  # 3. AMX check, then install and experiments in tmux
./03-run-remote.sh attach           #    watch; finishes with "ALL-DONE exit=0"
./03-run-remote.sh collect          # 4. copy results to results/<timestamp>/
python3 analyze.py results/<timestamp> --usd-per-hour <rate>
python3 docs/build_site.py results/<timestamp>
CONFIRM=yes ./99-teardown.sh        # 5. delete everything; must end with "CLEAN"
```

To rerun only some experiments on a running server: `STAGES="E3 E4" ~/node/experiments.sh` (stages: `E2`, `E3`, `E4`, `E2X`).

If the macOS IBM Cloud CLI times out on DNS during login, `env.sh` already sets `GODEBUG=netdns=cgo`, which fixes it.

## What to check

| Check | File in `results/<run>/` | Pass |
|---|---|---|
| Hardware | `hwcheck.txt` | `amx_tile`, `amx_bf16`, and `amx_int8` present |
| Versions | `versions.txt` | solutions v1.1.0, inference `5d92bef` |
| Install | `install.log`, `timeline.csv` | Ansible `failed=0` |
| Platform health | `validate.log`, `validate-components.log` | Each component passes (see the README on `nfd`) |
| Correctness | `smoke.txt` | Each model answers "Paris" |
| Authentication | `smoke-auth.txt` | A request without a token gets HTTP 401 |
| Performance | `bench-*.json` | 0 failed requests at every level |
| AMX in use | `onednn-*.txt` | `avx10_1_512_amx` with AMX on; `avx512_core_bf16` with it off |
| Step log | `logs/steps.log` | One line per deploy, smoke test, benchmark, and undeploy |

## Experiments

| ID | Stage | What runs |
|---|---|---|
| E1 | install | Timed install from a bare server to the first correct answer |
| E2 | `E2` | Qwen3-0.6B, AMX on, 1, 2, 4, 8, and 16 users, 32 requests each |
| E2X | `E2X` | The same at 24, 32, and 48 users, 48 requests each |
| E3 | `E3` | E2 with `ONEDNN_MAX_CPU_ISA=AVX512_CORE_BF16` (AMX off) |
| E4 | `E4` | Qwen2.5-3B-Instruct, AMX on, 1, 2, 4, and 8 users, 16 requests each |
| E5 | analysis | Blended cost from E2 and E4 throughput |

Every model gets 8 cores, a ~600-token prompt, 128 output tokens, and temperature 0. All requests go through the authenticated gateway.
