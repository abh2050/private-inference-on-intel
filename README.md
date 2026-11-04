# Private LLM inference on Intel Xeon: how hard is it, and what do you get?

**Results page with charts: https://abh2050.github.io/private-inference-on-intel/**

I installed [Intel AI for Enterprise Inference](https://github.com/intel/enterprise-inference) on one IBM Cloud Xeon server, served open models through its OpenAI-compatible gateway, and measured four things: the effort to deploy it, the number of users one node serves within a latency target, the cost per token, and how much Intel AMX contributes. Every step is scripted and pinned to exact versions, and the raw data and logs from the run are in this repository.

| Result (run 1, 2026-11-04) | Value |
|---|---|
| Bare server to first correct answer | **32.9 min** of automation; 48.8 min wall clock, including 3 manual interventions |
| Concurrent users within the latency target, one 8-core Xeon node, Qwen3-0.6B | **24** |
| Cost per 1M output tokens at that load | **$2.50**\* |
| Users within target with AMX vs. without it, same cores | **24 vs. 2**, with up to **3.1×** throughput |
| Qwen2.5-3B on the same 8 cores | Correct answers, but no load level meets the target |

\*At an estimated $1.90 per server-hour; IBM's partial billing data so far implies about $2. Ratios between configurations do not depend on the rate.

## The problem

A team moving LLM inference onto its own infrastructure, for cost, data privacy, or air-gap reasons, has to answer four questions before it commits hardware:

1. **Effort.** How long from an empty machine to an authenticated, OpenAI-compatible endpoint, and where does the process break?
2. **Capacity.** How many concurrent users can one node serve before latency becomes unacceptable?
3. **Economics.** What does a million output tokens cost at that load, and what does a node cost per month?
4. **Hardware value.** How much of the CPU result comes from Intel AMX, the matrix unit in 4th Gen Xeon and newer?

Vendor documentation explains how to install the stack but gives no numbers for any of these. This repository measures them on real hardware, with a latency target fixed before the run:

- p95 time to first token (TTFT) of at most 2 seconds;
- at least 10 output tokens per second for each user;
- no failed requests.

## From request to token

| Step | Where | What happens | What it sets |
|---|---|---|---|
| 1 | Envoy Gateway | TLS termination and Keycloak JWT check; no token returns HTTP 401 | Access control |
| 2 | Envoy AI Gateway | Reads `"model"` from the JSON body and selects that model's route | Multi-model routing |
| 3 | EPP scheduler | Picks a serving endpoint for the `LLMInferenceService` | Load spreading |
| 4 | vLLM | Tokenizes the prompt and adds it to the running batch (continuous batching) | Queueing |
| 5 | vLLM prefill | Processes all prompt tokens at once; compute-bound bf16 matrix multiplies on AMX | **Time to first token** |
| 6 | vLLM decode | One token per step per request, reading weights and the paged KV cache; memory-bandwidth-bound | **Tokens/s per user** |
| 7 | Gateways | Tokens stream back as server-sent events | OpenAI compatibility |
| 8 | NRI balloons (underneath) | Pin the pod to whole cores on one NUMA node, keeping memory local | Predictable latency |

This is why AMX moves TTFT far more than per-user speed, and why 8 cores saturate near 217 tokens/s: past that point, new users queue for prefill.

## Results

Every model ran on the same 8 physical cores (one NUMA node) with a ~600-token prompt and 128 output tokens. All traffic went through the authenticated gateway, and every request succeeded at every load level. Full tables are in [`results/20261103-2026/summary.md`](results/20261103-2026/summary.md).

### Capacity and cost, Qwen3-0.6B with AMX

| Concurrent users | Output tok/s | TTFT p95 | Tok/s per user | $ per 1M output tokens | Meets target |
|---|---|---|---|---|---|
| 1 | 21.0 | 0.16 s | 22.0 | 25.13 | yes |
| 4 | 59.8 | 0.43 s | 16.6 | 8.83 | yes |
| 8 | 119.9 | 0.69 s | 18.5 | 4.40 | yes |
| 16 | 182.4 | 1.21 s | 15.6 | 2.89 | yes |
| **24** | **210.7** | **1.76 s** | **12.6** | **2.50** | **yes** |
| 32 | 216.7 | 2.31 s | 10.3 | 2.44 | no |
| 48 | 218.2 | 3.39 s | 5.5 | 2.42 | no |

Throughput levels off near 217 tokens/s at about 30 users. Beyond that, extra users wait longer rather than adding throughput, and TTFT is the first limit to break.

The cost per token falls 10× between 1 and 24 users, because the server costs the same per hour however busy it is. Run continuously at the estimated rate, the node costs about $1,390 a month and can produce up to about 550 million output tokens at its 24-user operating point. Utilization, not hardware, sets the effective cost.

### What AMX contributes

The comparison used the same model on the same cores. The only change was capping oneDNN below AMX with `ONEDNN_MAX_CPU_ISA=AVX512_CORE_BF16`. A oneDNN probe inside each pod confirms the kernel that actually ran: `brg_matmul:avx10_1_512_amx` in one, `brg_matmul:avx512_core_bf16` in the other.

| Concurrent users | Tok/s, AMX on | Tok/s, AMX off | Ratio | TTFT p95, on → off |
|---|---|---|---|---|
| 1 | 21.0 | 18.0 | 1.2× | 0.16 → 0.62 s |
| 4 | 59.8 | 39.6 | 1.5× | 0.43 → 2.15 s |
| 8 | 119.9 | 55.4 | 2.2× | 0.69 → 4.40 s |
| 16 | 182.4 | 59.0 | 3.1× | 1.21 → 8.39 s |

With one user, AMX adds little, because generating tokens (decode) is limited by memory bandwidth. Under load, processing prompts (prefill) dominates, and prefill is compute-bound, so the matrix unit matters. At the target, AMX turns a node that serves 2 users at $18.58 per million tokens into one that serves 24 at $2.50.

### A larger model

Qwen2.5-3B-Instruct answered correctly but delivered 5.2 tokens/s to a single user, half the target, and peaked at 29.7 tokens/s across 8 users ($17.77 per million tokens). A model this size needs more cores per replica, tensor parallelism across both sockets, or an accelerator to serve interactive traffic.

### Routing (calculated, not measured)

Using the measured peak throughputs, sending 70% of requests to the 0.6B model and 30% to the 3B model would cost $7.03 per million tokens, against $17.77 for all-3B: a 60% saving. Before claiming that saving, an evaluation set would have to show that the small model handles that share of real traffic acceptably.

## Deployment experience

The install itself was solid: 468 Ansible tasks with none failed, and 49 pods healthy with no restarts. The friction sat around it. Each item below happened during the run and is logged with a timestamp in [`logs/operator-log.md`](logs/operator-log.md).

| # | Issue | What happened | Suggested fix |
|---|---|---|---|
| 1 | Unclear entry point | The OPEA repo is archived with a "moved" notice. The new `intel/enterprise-inference` cannot be installed on its own; a third repo, `intel/enterprise-ai-solutions`, drives it. | Point every README at one quick start |
| 2 | `configure` waits at a `[y/N]` prompt | Over SSH or in CI it waits indefinitely; here it sat for 11.4 minutes. `--force` skips the prompt but is not in the quick start. | Document `--force`, or detect a non-terminal and name the flag |
| 3 | `validate` fails on a healthy cluster | It aborts at `nfd`, whose `validate.yaml` is missing in v1.1.0, so the inference components after it are never checked | Skip components that have no validate task, and report per component |
| 4 | Token helper breaks callers | `get-keycloak-token.sh` leaves a `RETURN` trap that aborts any calling script that uses `set -u` | Clear the trap, or add a command that prints the token |
| 5 | `undeploy` returns early | The next deploy failed the NRI pre-flight check ("not enough physical cores") on an empty node, because the old pod still held its cores | Add `undeploy --wait`, or make pre-flight wait for terminating pods |
| 6 | No built-in SLA benchmark | TTFT, per-user tokens/s, and cost per token had to be measured with a separate load generator | A `model-manager bench` command that reports against a stated target |
| 7 | No Intel accelerator path yet | The release automates Xeon and NVIDIA GPU nodes, and its docs place Intel GPU support in a later milestone. Gaudi support exists only in the archived OPEA version. | — |

The hardware-aware parts worked as designed. NRI balloons pinned each model to whole cores on one NUMA node. Pre-flight refused placements that would have spilled onto hyperthread siblings. KServe and the Envoy AI Gateway routed by the `model` field with no per-model gateway configuration.

## Where Xeon fits, from this data

The case for CPU inference is not raw speed. It is serving a known load within a target, on hardware that is already approved, owned, and allowed to see the data.

| Good fit | Evidence |
|---|---|
| Small models at interactive load | Measured: 0.6B served 24 users within target on 8 cores |
| Prefill-heavy traffic (RAG, summarization, classification) | Measured: AMX gives up to 3.1× under load |
| Private and air-gapped deployments | Measured: one authenticated OpenAI-compatible endpoint; the model runs on the server |
| Fleets that already run Xeon | Judgment: capacity without a new accelerator procurement |

| Poor fit, or needs more hardware | Evidence |
|---|---|
| 3B+ models for interactive users on a few cores | Measured: 5.2 tokens/s for one user, target 10 |
| Loads past saturation | Measured: beyond ~30 users on 8 cores, throughput stops rising |
| Large models at high throughput | Judgment: accelerator memory bandwidth decides it |
| More cores per replica, cross-socket tensor parallelism, INT8 / OpenVINO INT4 | Not yet tested |

## What to build next

Ranked by how much each would cut the time and expertise a new team needs to reach a trusted, measured endpoint.

1. **A one-command evaluation path.** A single-node install that never prompts, validates each component without aborting, and ends by printing a working `curl`. This removes friction items 1–3, which cost about 15 minutes of this run. *Measure:* time to first answer, 49 minutes today, target under 15.
2. **An SLA report built into model-manager.** `model-manager bench --sla ttft=2s,tps=10` would sweep concurrency, report capacity, TTFT, TPOT, and cost per million tokens, and export to the existing Grafana. *Measure:* the share of deployments with a recorded SLA capacity.
3. **A capacity planner.** Given a model and an SLA, recommend cores, replicas, and tensor parallelism. NRI pre-flight already knows the free cores per NUMA node, and benchmark data supplies tokens/s per core. *Measure:* predicted vs. measured capacity, within 15%.
4. **SLA-aware routing in the AI gateway.** The gateway already routes on the `model` field. Add a policy that sends each request to the smallest model that passes an evaluation set for its task, and report the realized saving. *Measure:* blended cost per million tokens at equal evaluation score.

## Architecture

![Architecture: an operator workstation provisions an IBM Cloud VPC with one bx3d Xeon virtual server running single-node Kubernetes. Requests pass through Envoy Gateway (TLS and Keycloak JWT check), Envoy AI Gateway (model routing), an EPP scheduler, and a vLLM CPU pod pinned to 8 cores, whose bf16 matrix math runs on AMX through oneDNN.](docs/architecture.png)

The draw.io source is [`docs/architecture.drawio`](docs/architecture.drawio). It uses IBM's architecture shapes and is regenerated by [`docs/gen_drawio.py`](docs/gen_drawio.py).

| Layer | Components | Job |
|---|---|---|
| Infrastructure | IBM Cloud VPC, `bx3d-32x160` (4th Gen Xeon Sapphire Rapids, AMX; 2 sockets × 8 cores; 160 GB), Ubuntu 24.04 | One server. SSH is allowed only from the operator's IP. |
| Cluster | Kubernetes v1.34.3 via Kubespray (the docs say v1.35.4), local-path storage | Single-node cluster |
| Edge | Envoy Gateway, MetalLB, cert-manager, Keycloak | TLS termination; JWT validation (a request with no token gets HTTP 401) |
| Routing | Envoy AI Gateway, EPP scheduler, KServe `LLMInferenceService` | Selects the backend from the request's `model` field |
| Serving | vLLM CPU 0.24 (OpenVINO Model Server is also available) | OpenAI-compatible `/v1/chat/completions` |
| CPU placement | NRI balloons | Pins each model to whole cores on one NUMA node |
| Math | PyTorch and oneDNN | Runs bf16 matrix multiplies on AMX tiles |
| Platform | Istio, PostgreSQL, SeaweedFS, Prometheus, Grafana | Service mesh, Keycloak database, object store, metrics |

Versions are pinned to `intel/enterprise-ai-solutions` v1.1.0, which pins `intel/enterprise-inference` v1.0.1 (`5d92bef`).

## Experiments

| ID | What was done | Question |
|---|---|---|
| E1 | Timed each install phase on a fresh server and logged every retry, error, and manual step | How hard is deployment? |
| E2 | Served Qwen3-0.6B at 1, 2, 4, 8, and 16 concurrent users; E2X extended this to 24, 32, and 48 | How many users fit within the target, and at what cost? |
| E3 | Repeated E2 with AMX disabled in oneDNN | What does AMX contribute? |
| E4 | Served Qwen2.5-3B-Instruct at 1, 2, 4, and 8 users | Does a CPU hold up at a larger model size? |
| E5 | Calculated blended cost for 50%, 70%, and 90% of traffic routed to the small model | Is routing worth building? |

Cost per million output tokens = hourly price ÷ (output tokens/s × 3600) × 1,000,000.

### Limits of this run

- One server and one run per configuration, so run-to-run variance has not been measured.
- The load generator ran on the same server. The model's cores were pinned; the client's were not.
- Costs use an estimated hourly rate. To use the invoiced rate, rerun `analyze.py --usd-per-hour <rate>`.
- No Intel accelerator was tested. IBM Cloud offers Intel Gaudi 3 (an 8-accelerator `gx3d-160x1792x8gaudi3` profile) but no Intel Arc or Data Center GPU instances. The current Enterprise Inference release serves on Xeon only; Gaudi support exists in the archived OPEA version.

## Reproduce it

You need an IBM Cloud account that can create VPC virtual servers, plus `jq`, `bc`, and the IBM Cloud CLI. A full run uses about two hours of server time, roughly $3.

```bash
ibmcloud login --sso
./01-preflight.sh                  # read-only: account, credit, profiles, image, leftovers
CONFIRM=yes ./02-provision.sh      # creates the VPC and server, starts a cost watchdog
./03-run-remote.sh                 # checks AMX, then runs the install and E1-E4 in tmux
./03-run-remote.sh attach          # watch progress
./03-run-remote.sh collect         # copy results and logs to results/<timestamp>/
python3 analyze.py results/<timestamp> --usd-per-hour <rate>
python3 docs/build_site.py results/<timestamp>   # rebuild the results page
CONFIRM=yes ./99-teardown.sh       # delete everything and confirm nothing is left
```

Cost safeguards:
- `02-provision.sh` refuses to run without `CONFIRM=yes`.
- A watchdog deletes every `opea-ei-*` resource after `MAX_HOURS` (default 4).
- `99-teardown.sh` ends with a leftovers check that must report zero.
- `bx3d` servers keep billing while stopped, so the scripts delete them rather than stop them.

[RUNBOOK.md](RUNBOOK.md) has step-by-step instructions and pass criteria for each output file.

## Repository layout

```text
README.md                this page
docs/index.html          results page published with GitHub Pages
docs/architecture.*      draw.io diagram and PNG export
results/20261103-2026/   run 1: benchmarks, oneDNN probes, pod specs, install log, timestamped logs
logs/operator-log.md     every action taken during run 1, including failures and fixes
env.sh                   region, profile, pinned versions, cost limits
01-preflight.sh          read-only account and capacity checks
02-provision.sh          VPC, subnet, key, server, floating IP, watchdog
03-run-remote.sh         run, attach, or collect on the server
99-teardown.sh           delete all resources and verify
node/                    on-server scripts: hardware check, timed install, experiments, load generator
analyze.py               SLA capacity, cost per token, AMX ratio, routing calculation
```

The scripts are provided as-is. The Intel components are Apache 2.0, and model weights come from Hugging Face under their own licenses.
