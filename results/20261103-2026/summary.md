# Results summary
Server cost assumed: $1.9/h. SLA: p95 TTFT ≤ 2.0 s, ≥ 10.0 tok/s per user, 0 errors.

## E1: time to first request
| phase | start (UTC) | seconds | exit |
|---|---|---|---|
| os_packages | 03:01:23 | 8 | 0 |
| clone | 03:01:31 | 0 | 0 |
| configure | 03:01:31 | 758 | 0 |
| init | 03:14:09 | 1 | 0 |
| install_inference | 03:14:10 | 1491 | 0 |
| validate | 03:39:01 | 37 | 1 |
| deploy_qwen3-0-6b | 03:42:49 | 59 | 141 |
| deploy_qwen3-0-6b | 03:43:53 | 366 | 0 |
| deploy_qwen3-noamx | 03:54:54 | 280 | 0 |
| deploy_qwen2-5-3b | 04:05:33 | 404 | 0 |
| deploy_qwen3-0-6b | 04:20:29 | 208 | 0 |

**Wall clock, start of install to first correct answer: 48.8 min.** Time the automation needed (install phases minus the 11.4 min the `[y/N]` prompt sat unanswered, plus the 6.1 min first model deploy): **32.9 min**. The difference is waiting on prompts and diagnosing failures by hand.

Ansible retries during install: 36.

Friction notes from the run:
```
configure waited at an interactive [y/N] prompt from 03:01:31 to 03:12:58 UTC; answered manually. Fix: pass --force. Subtract this wait from E1.
PHASE validate FAILED (exit 1)
validate inference: 13 components passed; aborted at nfd because playbooks/validate.yaml is missing for that role in v1.1.0 (installer bug). kserve, envoy_ai_gateway, keycloak_config, llm_services were not checked by the aborted run; validated individually instead.
get-keycloak-token.sh (inference v1.0.1) leaves a RETURN trap referencing an unset variable; sourcing it from a script with set -u aborts that script. Worked around with trap - RETURN.
Run restarted at 03:43:52: GATEWAY_DOMAIN from get-keycloak-token.sh already includes the inference. prefix (script bug on our side, fixed). Model download job had started at 03:42:49; deploy restarted, weights reused.
E3/E4 attempt 1 (03:52): model-manager undeploy returned before the pod released its NRI-balloon cores; next deploy 1 s later failed pre-flight (free [6,6] < 8). Not a capacity limit: dry-run at 03:56 passed. Fix: wait until llm-inference has no pods after undeploy. Failed outputs kept in failed-attempt-1/.
```

## E2 Qwen3-0.6B, AMX on
| users | ok/total | req/s | out tok/s | TTFT p50 | TTFT p95 | tok/s per user | $/1M out tok | SLA |
|---|---|---|---|---|---|---|---|---|
| 1 | 32/32 | 0.447 | 21.0 | 0.1494 | 0.1599 | 22.0 | 25.13 | ✅ |
| 2 | 32/32 | 0.755 | 35.5 | 0.2473 | 0.2839 | 18.9 | 14.87 | ✅ |
| 4 | 32/32 | 1.272 | 59.8 | 0.3721 | 0.4252 | 16.6 | 8.83 | ✅ |
| 8 | 32/32 | 2.55 | 119.9 | 0.659 | 0.6884 | 18.5 | 4.4 | ✅ |
| 16 | 32/32 | 3.873 | 182.4 | 1.108 | 1.2072 | 15.6 | 2.89 | ✅ |
| 24 | 48/48 | 4.483 | 210.7 | 1.6949 | 1.7573 | 12.6 | 2.5 | ✅ |
| 32 | 48/48 | 4.604 | 216.7 | 1.7511 | 2.3109 | 10.3 | 2.44 | ❌ |
| 48 | 48/48 | 4.643 | 218.2 | 1.8298 | 3.3862 | 5.5 | 2.42 | ❌ |

**SLA capacity: 24 concurrent users, $2.5 per 1M output tokens at that load.**

## E3 Qwen3-0.6B, AMX off
| users | ok/total | req/s | out tok/s | TTFT p50 | TTFT p95 | tok/s per user | $/1M out tok | SLA |
|---|---|---|---|---|---|---|---|---|
| 1 | 32/32 | 0.294 | 18.0 | 0.6069 | 0.6179 | 21.4 | 29.32 | ✅ |
| 2 | 32/32 | 0.411 | 28.4 | 1.143 | 1.1999 | 16.8 | 18.58 | ✅ |
| 4 | 32/32 | 0.628 | 39.6 | 0.6758 | 2.1465 | 11.3 | 13.33 | ❌ |
| 8 | 32/32 | 0.916 | 55.4 | 2.7801 | 4.4009 | 10.1 | 9.53 | ❌ |
| 16 | 32/32 | 0.986 | 59.0 | 7.4442 | 8.3893 | 6.6 | 8.95 | ❌ |

**SLA capacity: 2 concurrent users, $18.58 per 1M output tokens at that load.**

## E4 Qwen2.5-3B, AMX on
| users | ok/total | req/s | out tok/s | TTFT p50 | TTFT p95 | tok/s per user | $/1M out tok | SLA |
|---|---|---|---|---|---|---|---|---|
| 1 | 16/16 | 0.095 | 4.9 | 0.7001 | 0.7583 | 5.2 | 107.71 | ❌ |
| 2 | 16/16 | 0.163 | 8.5 | 1.3004 | 1.4458 | 4.6 | 62.09 | ❌ |
| 4 | 16/16 | 0.266 | 13.8 | 2.18 | 2.2829 | 3.9 | 38.24 | ❌ |
| 8 | 16/16 | 0.571 | 29.7 | 3.6212 | 3.6821 | 4.9 | 17.77 | ❌ |

**SLA capacity: 0 concurrent users, $n/a per 1M output tokens at that load.**

## AMX on vs off (same model, same 8 cores)
| users | tok/s AMX on | tok/s AMX off | gain | TTFT p50 on/off |
|---|---|---|---|---|
| 1 | 21.0 | 18.0 | 1.17× | 0.1494 / 0.6069 |
| 2 | 35.5 | 28.4 | 1.25× | 0.2473 / 1.143 |
| 4 | 59.8 | 39.6 | 1.51× | 0.3721 / 0.6758 |
| 8 | 119.9 | 55.4 | 2.16× | 0.659 / 2.7801 |
| 16 | 182.4 | 59.0 | 3.09× | 1.108 / 7.4442 |

oneDNN probe `qwen3-0-6b`:
```
onednn_verbose,v1,info,cpu,isa:Intel AVX-512 with float16, Intel DL Boost and bfloat16 support and Intel AMX with bfloat16 and 8-bit integer support
onednn_verbose,v1,primitive,exec,cpu,matmul,brg_matmul:avx10_1_512_amx,undef,src:bf16::blocked:ab::f0 wei:bf16::blocked:ba::f0 dst:bf16::blocked:ab::f0,attr-scratchpad:user,,256x256:256x256,0.826172
```

oneDNN probe `qwen3-noamx`:
```
onednn_verbose,v1,info,cpu,isa:Intel AVX-512 with Intel DL Boost and bfloat16 support
onednn_verbose,v1,primitive,exec,cpu,matmul,brg_matmul:avx512_core_bf16,undef,src:bf16::blocked:ab::f0 wei:bf16::blocked:ba::f0 dst:bf16::blocked:ab::f0,attr-scratchpad:user,,256x256:256x256,0.606201
```

## E5: routing what-if (calculated from measured peak throughput)
All traffic on 3B: $17.77/1M tokens. All on 0.6B: $2.42/1M tokens.
| share routed to small model | blended $/1M | saving vs all-3B |
|---|---|---|
| 50% | $10.09 | 43% |
| 70% | $7.03 | 60% |
| 90% | $3.95 | 78% |

The 3B figure uses its peak measured throughput (8 users), where it already misses the latency target on 8 cores.

This is a calculation, not a measured router. Quality on the routed share has to be checked with an eval set before claiming the saving.
