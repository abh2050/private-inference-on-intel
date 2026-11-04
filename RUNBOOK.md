# Intel AI for Enterprise Inference on IBM Cloud: reproducible Xeon (AMX) run

Checked 2026-11-03.

## What changed since the earlier chat
- `opea-project/Enterprise-Inference` is **archived**. Its README now says "PROJECT MOVED" to
  [intel/enterprise-inference](https://github.com/intel/enterprise-inference).
- The maintained stack is **Xeon-only** (vLLM CPU + OpenVINO Model Server on KServe). None of its files mention Gaudi.
  Gaudi support exists only in the archived OPEA repo.
- It is no longer standalone. You install it through
  [intel/enterprise-ai-solutions](https://github.com/intel/enterprise-ai-solutions) (`es_auto_installer.sh`).
- Pinned here: solutions **v1.1.0**, which pins enterprise-inference **v1.0.1** (`5d92bef`), vLLM CPU **0.24.0**,
  model **Qwen/Qwen3-0.6B** (`qwen3-0-6b` in the catalog). It is public, so you need no Hugging Face token.

## Hardware decision
| Option | Verdict |
|---|---|
| IBM VPC `bx3d-32x160` (4th Gen Xeon, AMX, 32 vCPU / 160 GB) | **Use this.** Meets the "3B model" minimum (32 cores, 64 GB). Roughly $1.6–2/h, an estimate you should confirm. |
| IBM `bx2`/`cx2`/`mx2` (gen 2) | No AMX. Avoid. |
| IBM Gaudi 3 (`gx3d-…gaudi3`) | Tens of $/h, and the current stack does not support Gaudi. Out of scope. |
| AWS us-east-2 control plane | **Not needed.** It is a single node, and the installer runs on the server itself. Adding AWS would add cost and cross-cloud traffic for no gain. |

## Cost guards
1. `02-provision.sh` refuses to run without `CONFIRM=yes`.
2. A watchdog deletes everything after `MAX_HOURS` (default 6 h, about $11). It only runs while your Mac is awake.
3. **bx3d keeps billing while stopped** because it has local instance storage. Delete the server, don't just stop it.
4. Every resource name starts with `opea-ei`. `99-teardown.sh` deletes them all and prints a leftovers check that should show 0.
5. Set this in the console: **Manage → Billing and usage → Spending notifications**, with an alert at $50 and $100.
6. Budget: $150/month ÷ ~$1.9/h ≈ 75 server-hours. One full run is about 1 hour.

## Steps
```bash
cd ~/Desktop/inteldv && chmod +x *.sh node/*.sh

# 0. One-time setup (free)
curl -fsSL https://clis.cloud.ibm.com/install/osx | sh
ibmcloud login --sso
ibmcloud plugin install vpc-infrastructure -f

# 1. Read-only check: account, credits, whether bx3d exists in us-east, Ubuntu image
./01-preflight.sh
#    -> Put the real hourly price from cloud.ibm.com/estimator into EST_USD_PER_HOUR in env.sh

# 2. PAID: create the server (needs your approval)
CONFIRM=yes ./02-provision.sh

# 3. Check AMX, then run install + deploy + smoke test + benchmark (about 45 min)
./03-run-remote.sh
./03-run-remote.sh attach        # watch; wait for "ALL-DONE exit=0"
./03-run-remote.sh collect       # copies results into ./results/<timestamp>/

# 4. Teardown (always)
CONFIRM=yes ./99-teardown.sh     # must end with "CLEAN"
```

## Experiment design (E1–E5)
| ID | Experiment | Question it answers |
|---|---|---|
| E1 | Timed install from bare server to first correct answer, with retries and errors logged | "What was hard?", "How does it compare with NIM?", adoption |
| E2 | Qwen3-0.6B at 1, 2, 4, 8 and 16 concurrent users | SLA definition, cost per token |
| E3 | Same as E2 with AMX disabled in oneDNN (`ONEDNN_MAX_CPU_ISA=AVX512_CORE_BF16`) | "Why run inference on Xeon?" |
| E4 | Qwen2.5-3B-Instruct at 1, 2, 4 and 8 concurrent users | Does a CPU hold up at enterprise model sizes? |
| E5 | Routing what-if, calculated from E2 and E4 data | "What would you build next?" |

SLA, fixed before the run: p95 TTFT ≤ 2 s, at least 10 tokens/s per user, 0 errors. All tests use 8 cores, the same prompt, 128 output tokens and temperature 0.
After collecting results: `python3 analyze.py results/<run> --usd-per-hour <real rate>` writes `summary.md`.

## What counts as a pass
| Check | File in results/ | Pass |
|---|---|---|
| Hardware | `hwcheck.txt` | `amx_tile`, `amx_bf16`, `amx_int8` are YES |
| Versions | `versions.txt` | solutions v1.1.0, inference 5d92bef… |
| Platform | `validate.log`, `unhealthy-pods.txt` | validate passes and the unhealthy-pods file is empty |
| Serving | `served.txt` | model READY |
| Correctness | `smoke.json` | the answer contains "Paris" |
| Auth | `smoke-auth.txt` | a request without a token gets 401/403 |
| Performance | `bench.json` / `bench.txt` | 0 failures at concurrency 1/4/8, plus TTFT, TPOT and tokens/s |
| AMX in use | `vllm-cpu-log.txt`, `pod-spec.json` | bf16 dtype or oneDNN/AMX lines, and CPU pinning visible |

The benchmark sends 32 requests per level with a fixed ~500-token prompt and 128 output tokens at temperature 0, through the real gateway with auth.
It is small on purpose, and every model call runs on your server, so no paid API is used.

## Optional next experiment, in the same session
Compare engines with the catalog's OpenVINO model (Qwen3.5-2B INT4, so it is a different model and not a like-for-like comparison):
`./model-manager deploy qwen3-5-2b-ovms --wait`, then re-run `node/bench.py` with `--model qwen3-5-2b-ovms`.
