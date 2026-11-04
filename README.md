# How hard is it to run private LLM inference on Intel hardware?

This repository installs Intel AI for Enterprise Inference on a single Intel Xeon server in IBM Cloud, serves open models through it, and measures two things:

- the deployment effort, from a bare server to the first correct answer;
- what one CPU node delivers at that point: latency, throughput, users served within a latency target, and cost per million tokens.

Everything here is scripted and pinned to exact versions, so another person can rerun it and compare.

## The problem

Teams that want to run models on their own infrastructure, for cost, data privacy, or air-gap reasons, need answers that vendor documentation does not give:

- How long does it take to go from an empty machine to a working, authenticated, OpenAI-compatible endpoint?
- Where does the install break, and how much expertise does a fix take?
- How many concurrent users can one node serve before latency becomes unacceptable?
- What does a million output tokens cost at that load?
- How much of the CPU result comes from Intel AMX, the matrix unit in 4th Gen Xeon and newer?

The scope is Intel hardware only: Xeon CPUs now, and Intel GPUs next (see [Intel GPU](#intel-gpu)).

## What runs where

![Architecture: an operator workstation provisions an IBM Cloud VPC with one bx3d Xeon virtual server running single-node Kubernetes. Requests pass through Envoy Gateway (TLS and Keycloak JWT check), Envoy AI Gateway (model routing), an EPP scheduler, and a vLLM CPU pod pinned to 8 cores, whose bf16 matrix math runs on AMX through oneDNN.](docs/architecture.png)

Source: [docs/architecture.drawio](docs/architecture.drawio), which opens in draw.io and uses IBM's architecture shapes. `docs/gen_drawio.py` regenerates it.

### Infrastructure (IBM Cloud)

| Piece | Choice | Reason |
|---|---|---|
| Region / zone | us-east / us-east-1 | Any region that offers `bx3d` profiles works |
| Server | `bx3d-32x160`: 32 vCPU (2 sockets × 8 cores × 2 threads), 160 GB RAM | 4th Gen Xeon (Sapphire Rapids) with AMX. The Gen 2 `bx2` profiles lack AMX. |
| OS | Ubuntu 24.04, 250 GB boot volume | Supported by the installer |
| Network | One VPC and subnet, a floating IP, and a security group that allows SSH only from the operator's IP | Nothing in the cluster is exposed to the internet |

`hwcheck.sh` confirms the CPU on the server before anything is installed. On the first run it reported `Intel Xeon Processor (SapphireRapids)` with the `amx_tile`, `amx_bf16`, and `amx_int8` flags.

### Software stack

The stack comes from two Intel repositories. [intel/enterprise-ai-solutions](https://github.com/intel/enterprise-ai-solutions) `v1.1.0` provides the installer and platform layer. That release pins [intel/enterprise-inference](https://github.com/intel/enterprise-inference) `v1.0.1`, the serving layer.

| Layer | Components | Job |
|---|---|---|
| Cluster | Kubernetes v1.34.3 (Kubespray; the docs say v1.35.4), local-path storage | Single-node cluster on the VM |
| Edge | Envoy Gateway, MetalLB, cert-manager, Keycloak | TLS termination, a LoadBalancer IP, and JWT validation against Keycloak |
| Routing | Envoy AI Gateway, EPP scheduler, KServe `LLMInferenceService` | Reads `"model"` from the request body and picks a serving endpoint |
| Serving | vLLM CPU `v0.24.0` (OpenVINO Model Server is also available) | OpenAI-compatible `/v1/chat/completions` |
| CPU placement | NRI balloons | Pins each model to whole cores on one NUMA node |
| Math | PyTorch and oneDNN | bf16 matrix multiplies run on AMX tiles |
| Platform | Istio, PostgreSQL, SeaweedFS, Prometheus, Grafana | Mesh, Keycloak's database, object storage, metrics |

### Request path

1. The client sends `POST https://inference.<domain>/v1/chat/completions` with a Keycloak bearer token.
2. `eg-gateway` terminates TLS and validates the token. A missing or invalid token gets HTTP 401.
3. `ai-gateway` reads the `model` field and routes to that model's backend.
4. The EPP scheduler picks a vLLM endpoint.
5. vLLM runs prefill (processing the prompt, compute-bound) and decode (generating tokens, memory-bandwidth-bound) on its pinned cores and streams tokens back.

## Experiments

All runs share the same conditions:

- 8 physical cores per model, one model at a time;
- the same ~500-token prompt, 128 output tokens, and temperature 0;
- traffic that goes through the real gateway with authentication.

The benchmark client runs on the same server, so the numbers exclude internet latency.

| ID | What we do | Question it answers | Measured |
|---|---|---|---|
| E1 | Time each install phase on a fresh server, and log every retry, ignored error, and manual fix | How hard is deployment? | Minutes per phase, minutes to first correct answer, friction log |
| E2 | Serve Qwen3-0.6B at 1, 2, 4, 8, and 16 concurrent streams, then 24, 32, and 48 (E2X) to find the limit | What does one node deliver? | TTFT p50/p95, time per output token, output tokens/s, errors |
| E3 | Repeat E2 with oneDNN capped below AMX (`ONEDNN_MAX_CPU_ISA=AVX512_CORE_BF16`) | What does AMX contribute? | E2 metrics, plus a oneDNN probe showing which instruction set ran |
| E4 | Serve Qwen2.5-3B-Instruct at 1, 2, 4, and 8 streams | Does a CPU hold up at a more realistic model size? | E2 metrics |
| E5 | Calculate the cost of routing some traffic to the small model and the rest to the 3B model | Is routing worth building? | Blended cost per million tokens at 50%, 70%, and 90% small-model share |

The latency target was fixed before the first run:

- p95 time to first token of at most 2 seconds;
- at least 10 output tokens per second per user;
- no failed requests.

"SLA capacity" means the highest concurrency that meets all three.

Cost per million output tokens = hourly server price ÷ (output tokens per second × 3600) × 1,000,000. The hourly price comes from IBM's estimator, entered when you run `analyze.py`.

E5 is arithmetic on the E2 and E4 throughput numbers, not a deployed router. Whether a small model can answer a given share of real traffic has to be tested with an evaluation set first.

## Deployment friction

The friction log is a result in its own right. Items 6 to 9 came up during run 1; the per-minute record is in [logs/operator-log.md](logs/operator-log.md).

| # | Where | What happened | Effect |
|---|---|---|---|
| 1 | Intel repos | `opea-project/Enterprise-Inference` is archived, and its README says the project moved. The new `intel/enterprise-inference` cannot be installed on its own; it is cloned and driven by `intel/enterprise-ai-solutions`. | A newcomer has to work out which of three repositories to start from |
| 2 | Intel repos | The current release documents Xeon serving and NVIDIA GPU nodes. Its rack-scale guide says Intel GPU support follows a later GPU-enablement milestone. Gaudi appears only in the archived repo. | No automated Intel accelerator path in this release |
| 3 | IBM Cloud CLI (macOS) | Login failed with a DNS timeout from the CLI's built-in resolver while the system resolver worked. Fixed with `GODEBUG=netdns=cgo`. | Not an Intel issue, but it blocks the first step |
| 4 | IBM Cloud CLI | `key-create` rejected an Ed25519 key until `--key-type ed25519` was passed | One failed provision, cleaned up by the teardown script |
| 5 | IBM Cloud billing | `bx3d` profiles include local instance storage, so IBM keeps billing while the server is stopped | Deleting the server is the only way to stop charges |
| 6 | Intel installer | `es_auto_installer.sh configure` stops at an interactive `[y/N]` prompt. Over SSH or in CI it waits forever, or refuses when no terminal is attached. The `--force` flag skips it, but the quick start does not mention it. | The first run sat idle for about 12 minutes until the prompt was answered by hand |
| 7 | Intel installer | `validate inference` aborts at `nfd` because the v1.1.0 release has no `validate.yaml` for that role. The 13 components before it pass; the inference components after it are never checked. | A healthy install reports failure. Each remaining component has to be validated by hand. |
| 8 | Intel helper script | `get-keycloak-token.sh` leaves a `RETURN` trap that references an unset variable. Sourcing it from a script that uses `set -u` aborts that script. | Automation around the token helper needs a workaround |
| 9 | Intel model-manager | `undeploy` returns while the pod still holds its pinned cores. A `deploy` issued straight afterwards fails the NRI pre-flight check with "not enough physical cores", even on an otherwise empty node. | Scripts that swap models have to poll until the pod is gone |


## Results

Run 1 took place on 2026-11-04 (UTC). The server ran for 1.5 hours. Raw data, logs, and the generated [summary](results/20261103-2026/summary.md) are in [`results/20261103-2026/`](results/20261103-2026/).

Costs use an assumed $1.90 per server-hour, an estimate rather than an IBM invoice. Rerun `analyze.py` with the real rate; the ratios between rows will not change.

### E1: deployment effort

| Measure | Value |
|---|---|
| Wall clock, start of install to first correct answer | **48.8 min** |
| Time the automation needed (excludes 11.4 min an unanswered `[y/N]` prompt sat idle) | **32.9 min** |
| `install inference` alone (Kubernetes, platform, and inference layers) | 24.9 min; 468 Ansible tasks, 0 failed |
| First model deploy (weight download, pod start, gateway registration) | 6.1 min |
| Manual interventions before the first answer | 3: the `[y/N]` prompt, the `validate` abort, and the token-helper trap |

The 36 Ansible retries during install were readiness polling, not errors. The most frequent were the KServe image pre-pull (9), the PostgreSQL cluster (5), and the Keycloak rollout (8 across two tasks).

### E2: one 8-core Xeon node serving Qwen3-0.6B, AMX on

| Concurrent users | Output tok/s | TTFT p95 | Tok/s per user | $ per 1M output tokens | Meets target |
|---|---|---|---|---|---|
| 1 | 21.0 | 0.16 s | 22.0 | 25.13 | yes |
| 4 | 59.8 | 0.43 s | 16.6 | 8.83 | yes |
| 8 | 119.9 | 0.69 s | 18.5 | 4.40 | yes |
| 16 | 182.4 | 1.21 s | 15.6 | 2.89 | yes |
| **24** | **210.7** | **1.76 s** | **12.6** | **2.50** | **yes** |
| 32 | 216.7 | 2.31 s | 10.3 | 2.44 | no (TTFT) |
| 48 | 218.2 | 3.39 s | 5.5 | 2.42 | no |

Every request succeeded at every level. Throughput levels off near 217 tokens/s at about 30 users. Past that point, extra users wait longer instead of getting more throughput. **Capacity within the target is 24 concurrent users, at $2.50 per million output tokens.**

### E3: what AMX contributes

The same model ran on the same 8 cores. The only change was `ONEDNN_MAX_CPU_ISA=AVX512_CORE_BF16` on the pod. A oneDNN probe inside each pod confirms what ran: `brg_matmul:avx10_1_512_amx` with AMX, and `brg_matmul:avx512_core_bf16` with it disabled.

| Concurrent users | Tok/s, AMX on | Tok/s, AMX off | Ratio | TTFT p95, on → off |
|---|---|---|---|---|
| 1 | 21.0 | 18.0 | 1.2× | 0.16 → 0.62 s |
| 4 | 59.8 | 39.6 | 1.5× | 0.43 → 2.15 s |
| 8 | 119.9 | 55.4 | 2.2× | 0.69 → 4.40 s |
| 16 | 182.4 | 59.0 | 3.1× | 1.21 → 8.39 s |

With one user, AMX adds little, because generating tokens is limited by memory bandwidth. The gap grows with load, because prompt processing (prefill) is compute-bound and AMX is a compute unit. Without AMX the node meets the target for 2 users ($18.58 per million tokens); with AMX it meets it for 24 ($2.50).

### E4: a 3B model on the same 8 cores

Qwen2.5-3B-Instruct answered correctly, but no load level met the target. A single user got 5.2 tokens/s, against the 10 required, and throughput peaked at 29.7 tokens/s with 8 users ($17.77 per million tokens). A model this size needs more cores per replica, or a different accelerator, to serve interactive traffic.

### E5: routing what-if

These figures are calculated from E2 and E4 peak throughput; no router was measured. Sending 70% of requests to the 0.6B model and 30% to the 3B model would cost $7.03 per million tokens, against $17.77 for all-3B, a 60% saving. Whether the small model can answer 70% of real traffic acceptably has to be shown with an evaluation set before that saving is real.

### Limits of this run

- One server, one run per configuration. The run-to-run variance has not been measured.
- The benchmark client ran on the same server, sharing it with the model. The model's 8 cores were pinned, but the client was not.
- The 6.1-minute first deploy may be slightly short: a stopped attempt a minute earlier had already started the weight download.
- 8 cores is one NUMA node's worth. Larger models and higher loads would use more cores, `--tp` across sockets, or more replicas.

## Intel GPU

The same experiments on an Intel GPU would answer whether a GPU node changes the cost per token enough to justify it. This has not been run, for two reasons:

- IBM Cloud does not offer Intel Arc Pro or Data Center GPU instances. Its Intel accelerator is Gaudi 3, at a price well beyond this project's budget.
- `enterprise-ai-solutions` v1.1.0 does not yet automate Intel GPU nodes (friction item 2).

A GPU run would need a machine with an Intel GPU, the Intel GPU device plugin for Kubernetes, and vLLM's XPU backend. The benchmark and analysis scripts work unchanged against any OpenAI-compatible endpoint.

## Reproduce it

Requirements:

- an IBM Cloud account that can create VPC virtual servers;
- macOS or Linux with `jq`, `bc`, and the IBM Cloud CLI.

A full run takes about two hours of server time.

```bash
ibmcloud login --sso
./01-preflight.sh                  # read-only: account, credit, profiles, image, leftovers
CONFIRM=yes ./02-provision.sh      # creates the VPC and server, starts the cost watchdog
./03-run-remote.sh                 # checks AMX, then runs the install and E1-E4 in tmux
./03-run-remote.sh attach          # watch progress
./03-run-remote.sh collect         # copy results to results/<timestamp>/
python3 analyze.py results/<timestamp> --usd-per-hour <rate from cloud.ibm.com/estimator>
CONFIRM=yes ./99-teardown.sh       # deletes everything and checks that nothing is left
```

Safety rails:

- `02-provision.sh` refuses to run without `CONFIRM=yes`.
- A watchdog process deletes every `opea-ei-*` resource after `MAX_HOURS` (default 4). It only runs while the workstation stays awake.
- `99-teardown.sh` finishes with a leftovers check that must show zero resources.

[RUNBOOK.md](RUNBOOK.md) has the step-by-step version with pass criteria for each artifact.

## Repository layout

```text
env.sh               shared settings: region, profile, versions, cost limits
01-preflight.sh      read-only account and capacity checks
02-provision.sh      VPC, subnet, key, server, floating IP, watchdog
03-run-remote.sh     copies node/ to the server; run / attach / collect
99-teardown.sh       deletes all opea-ei-* resources and verifies
node/hwcheck.sh      CPU model, AMX flags, NUMA layout
node/install.sh      E1: timed install with friction capture
node/experiments.sh  E1 (first request), E2, E3, E4
node/bench.py        streaming load generator (standard library only)
analyze.py           SLA capacity, cost per token, AMX ratio, E5
docs/                architecture diagram (draw.io source and PNG)
```

## License and versions

The scripts in this repository are provided as-is. The Intel components are Apache 2.0 and pinned to `enterprise-ai-solutions` v1.1.0 and `enterprise-inference` v1.0.1 (`5d92bef`), as checked on 2026-11-03. Model weights are downloaded from Hugging Face under their own licenses.
