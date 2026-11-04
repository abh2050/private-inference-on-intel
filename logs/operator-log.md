# Operator log: run 1 (2026-11-04)

Every action taken from the operator workstation, in order, including failures and fixes. Times are UTC. Times before 02:57 were reconstructed afterwards and are accurate to a few minutes; later times come from logs. Server-side detail is in `results/<run>/logs/`:

| File | Contents |
|---|---|
| `session.log` | Every line the install and experiments printed, timestamped |
| `session-backfill.log` | Terminal scrollback from before session logging started (03:29) |
| `cluster-snapshots.log` | Pods, recent events, load, memory, and disk every 60 seconds |
| `steps.log` | One line per experiment step: deploy, smoke test, benchmark, undeploy |
| `experiments.log` | Full experiments output, timestamped |
| `../install.log`, `../timeline.csv`, `../friction.txt` | Ansible output, phase timings, friction counts |

## Before the server existed

| Time (UTC) | Step | Result |
|---|---|---|
| 02:35 | Inspected `opea-project/Enterprise-Inference` | Archived, with a README saying the project moved to `intel/enterprise-inference` |
| 02:37 | Inspected `intel/enterprise-inference` and `intel/enterprise-ai-solutions` | Inference layer is installed through the solutions repo. Pinned solutions `v1.1.0`, which pins inference `v1.0.1` (`5d92bef`). |
| 02:40 | Installed the IBM Cloud CLI 2.48.1 | The Homebrew cask needs an admin password. Unpacked the official `.pkg` instead, after checking its SHA-256 against the cask. |
| 02:42 | `ibmcloud login` | Failed: DNS lookup timeout from the CLI's built-in resolver while the system resolver worked. Fixed with `GODEBUG=netdns=cgo`, now set in `env.sh`. |
| 02:45 | `01-preflight.sh` (read-only) | `bx3d-32x160` available in us-east; Ubuntu 24.04 minimal image found; no leftover resources |
| 02:55 | `02-provision.sh`, first attempt | Failed at `key-create`: an Ed25519 key needs `--key-type ed25519`. The VPC and subnet were already created. |
| 02:56 | `99-teardown.sh` | Deleted the partial VPC and subnet. Leftovers check: 0. |
| 02:57 | `02-provision.sh`, second attempt | Server running. Floating IP attached through the server's virtual network interface. Watchdog set to delete everything 4 hours later. |

## On the server

| Time (UTC) | Step | Result |
|---|---|---|
| 02:58 | `hwcheck.sh` | `Intel Xeon Processor (SapphireRapids)`, 2 sockets × 8 cores × 2 threads, 2 NUMA nodes; `amx_tile`, `amx_bf16`, and `amx_int8` present |
| 03:01 | `install.sh`: OS packages, clone `v1.1.0` | 8 s |
| 03:01 | `es_auto_installer.sh configure` | Waited at an interactive `[y/N]` prompt with no one to answer it |
| 03:14 | Answered the prompt over tmux | `configure` finished. Added `--force` to `install.sh` for future runs. About 12 minutes of E1 time is this wait. |
| 03:14 | `init inference` | 1 s |
| 03:14 | `install inference` started | Kubespray brought up Kubernetes **v1.34.3** (the docs say v1.35.4) |
| 03:27 | Status check | Node `Ready`. Running: cert-manager, Istio, MetalLB, Envoy Gateway, Keycloak, PostgreSQL, Prometheus and Grafana, local-path storage. SeaweedFS deploying. |
| 03:29 | Logging turned on | Per-minute cluster snapshots, plus step logging for `experiments.sh` (pushed before it started) |
| 03:30 | Session log fixed | The first session log recorded only epoch numbers, because `tmux pipe-pane` expands `%` date codes itself. Moved the timestamping into `node/ts-log.sh`. The scrollback was re-captured, so nothing was lost. |
| 03:39 | `install inference` finished | 24.9 min, exit 0. Ansible: ok=468, changed=147, failed=0. 49 pods Running or Completed, 0 restarts. |
| 03:39 | `validate inference` | **Failed**, though not because of the cluster: 13 components passed, then the run aborted at `nfd` because `playbooks/validate.yaml` is missing for that role in v1.1.0. The components after it were never checked. |
| 03:40 | Validated `kserve`, `envoy_ai_gateway`, `keycloak_config`, `llm_services` one by one | All passed, failed=0 |
| 03:41 | `experiments.sh`, first start | Exited after 1 s. Intel's `get-keycloak-token.sh` leaves a `RETURN` trap that references an unset variable, which aborts any script running with `set -u`. Fixed with `trap - RETURN` after sourcing. |
| 03:42 | `experiments.sh`, second start | Token OK; model download Job started. Stopped after 1 min: our script built the host as `inference.$GATEWAY_DOMAIN`, but the helper's value already includes `inference.`. Our bug, fixed. |
| 03:43 | `experiments.sh`, third start | Deploy of `qwen3-0-6b` restarted; already-downloaded weights are reused |
| 03:49 | `qwen3-0-6b` deployed | 366 s, including the weight download. Smoke test: "Paris" (PASS). Request without a token: HTTP 401 (PASS). |
| 03:50–03:52 | **E2 benchmark** | 32/32 requests succeeded at every level (1, 2, 4, 8, 16 concurrent) |
| 03:52 | E3 and E4 deploys, attempt 1 | Both failed NRI pre-flight within 2 s, reporting free per-NUMA balloon CPUs of [6, 6] against 8 needed. The script carried on and benchmarked nothing. |
| 03:56 | Diagnosis | A dry-run of the same deploy passed once the namespace was empty. `model-manager undeploy` returns before the pod releases its pinned cores, so a deploy issued 1 s later sees them as busy. |
| 03:57 | Fix and rerun | `experiments.sh` now waits for the pods to disappear after each undeploy, aborts on a failed deploy, and accepts `STAGES`. Failed outputs moved to `results/failed-attempt-1/`. Restarted with `STAGES="E3 E4"`. |
| 03:59 | E3 deployed (AMX off) | 280 s. Smoke test PASS. oneDNN probe in the pod: `avx512_core_bf16`, no AMX. |
| 04:05 | E3 benchmark finished | 32/32 at every level. Undeploy waited 36 s for the pod to go. |
| 04:12 | E4 deployed (Qwen2.5-3B) | 404 s, including the download. Smoke test PASS. |
| 04:18 | E4 benchmark finished | 16/16 at every level |
| 04:20 | Added E2X (24, 32, 48 users) | E2 still met the target at 16, so the limit had not been found |
| 04:25 | E2X finished | Passes at 24 users, fails at 32 (TTFT p95 2.31 s). Throughput levels off near 217 tok/s. |
| 04:26 | Collected results (1.5 MB) | Scanned for tokens, credentials, and personal data; only task names and cluster-internal IPs found |
| 04:27 | `99-teardown.sh` | Server, floating IP, volume, subnet, VPC, and key deleted. Leftovers check: all 0. Server time 1.49 h, about $2.83 at the estimated rate. |
