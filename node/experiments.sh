#!/usr/bin/env bash
# Runs ON THE SERVER after install.sh. Experiments E1 (first request), E2 (SLA sweep), E3 (AMX off), E4 (3B model).
# Models run one at a time on the same 8 cores. Every result lands in ~/results/.
set -uo pipefail
cd ~/eas
export KUBECONFIG=~/eas/env/local/kubeconfig.yaml
source .venv/bin/activate 2>/dev/null || true
R=~/results; TL=$R/timeline.csv
CPU=8
mkdir -p $R/logs
# Full output of this script, every line timestamped, in addition to the terminal
exec > >(while IFS= read -r l; do printf '%s %s\n' "$(date -u +%FT%TZ)" "$l"; done | tee -a $R/logs/experiments.log) 2>&1
# One line per step in steps.log, so the run can be read at a glance
log() { echo; echo "### $*  $(date -u +%T)"; echo "$(date -u +%FT%TZ)  $*" >> $R/logs/steps.log; }
log "experiments.sh start (solutions $(git describe --tags 2>/dev/null))"
trap 'log "experiments.sh exit code $?"' EXIT

token() { source ./ext/enterprise.ai-inference/model_manager/scripts/get-keycloak-token.sh --lifespan 7200 >/dev/null; }
pod_of() { local p; p=$(kubectl get pods -n llm-inference -l "app.kubernetes.io/name=$1" -o name 2>/dev/null | head -1)
           [[ -n $p ]] || p=$(kubectl get pods -n llm-inference -o name | grep -i "$1" | grep -v download | head -1); echo "$p"; }

deploy() {  # deploy <served-name> <model-manager args...>   timed, so it adds to E1
  local name=$1; shift; local s; s=$(date -u +%s)
  log "DEPLOY $name"
  ./model-manager deploy "$@" --cpu $CPU --wait --wait-timeout 1800 2>&1 | tee "$R/deploy-$name.log"
  local rc=${PIPESTATUS[0]}
  echo "deploy_$name,$(date -u -d @$s +%T),$(date -u +%T),$(( $(date -u +%s)-s )),$rc" >> $TL
  log "DEPLOY $name finished: exit $rc after $(( $(date -u +%s)-s )) s"
  return $rc
}

ask() {  # ask <model> <question> <must-contain>   one correctness check
  local resp; resp=$(curl -sk --noproxy '*' -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "$(jq -nc --arg m "$1" --arg q "$2" '{model:$m,messages:[{role:"user",content:$q}],max_tokens:200,temperature:0,chat_template_kwargs:{enable_thinking:false}}')" \
    "https://inference.$GATEWAY_DOMAIN/v1/chat/completions")
  echo "$resp" > "$R/smoke-$1.json"
  if echo "$resp" | jq -e --arg w "$3" '.choices[0].message.content | test($w; "i")' >/dev/null; then
    echo "PASS $1: $(echo "$resp" | jq -r '.choices[0].message.content' | head -c 120)"
  else echo "FAIL $1: $(echo "$resp" | head -c 300)"; fi | tee -a "$R/smoke.txt"
  log "SMOKE $1: $(tail -1 "$R/smoke.txt" | cut -c1-80)"
}

evidence() {  # evidence <served-name>   what the pod got, plus which oneDNN instruction set it actually uses
  local p; p=$(pod_of "$1")
  kubectl get -n llm-inference "$p" -o json | jq '{node:.spec.nodeName, containers:[.spec.containers[]|{name,image,resources,env}]}' > "$R/pod-$1.json"
  kubectl exec -n llm-inference "$p" -- sh -c 'ONEDNN_VERBOSE=1 python3 -c "
import torch; a=torch.randn(256,256,dtype=torch.bfloat16); torch.nn.functional.linear(a,a)"' 2>&1 \
    | grep -m4 -iE 'isa|brg|amx|avx' > "$R/onednn-$1.txt" || echo "(oneDNN probe unavailable)" > "$R/onednn-$1.txt"
}

bench() {  # bench <served-name> <label> <requests> <levels...>
  local m=$1 label=$2 n=$3; shift 3
  log "BENCH $label"
  ( while sleep 5; do echo "$(date +%T) $(top -bn1 | awk '/Cpu\(s\)/{print 100-$8}')"; done ) > "$R/cpu-$label.txt" & local sp=$!
  python3 ~/node/bench.py --url "https://inference.$GATEWAY_DOMAIN" --model "$m" \
    --concurrency "$@" --requests "$n" --max-tokens 128 --out "$R/bench-$label.json" | tee "$R/bench-$label.txt"
  kill $sp 2>/dev/null
  log "BENCH $label finished: $(jq -c '[.levels[] | {c:.concurrency, ok:.succeeded, tok_s:.output_tok_per_s, ttft95:.ttft_p95_s}]' "$R/bench-$label.json" 2>/dev/null)"
}

token
grep -q "inference.$GATEWAY_DOMAIN" /etc/hosts || echo "$GATEWAY_IP inference.$GATEWAY_DOMAIN" | sudo tee -a /etc/hosts >/dev/null

# ---- E1 tail + E2: small model, AMX on ------------------------------------------------------
deploy qwen3-0-6b qwen3-0-6b
token
ask qwen3-0-6b "What is the capital of France? Answer in one word." "Paris"
echo "First correct answer at $(date -u +%T) UTC" >> $R/timeline-notes.txt
code=$(curl -sk -o /dev/null -w '%{http_code}' --noproxy '*' -H "Content-Type: application/json" \
  -d '{"model":"qwen3-0-6b","messages":[{"role":"user","content":"hi"}]}' "https://inference.$GATEWAY_DOMAIN/v1/chat/completions")
echo "No-token request -> HTTP $code (expect 401/403)" | tee $R/smoke-auth.txt
evidence qwen3-0-6b
bench qwen3-0-6b E2-qwen0.6b-amx 32 1 2 4 8 16
log "UNDEPLOY qwen3-0-6b"; ./model-manager undeploy qwen3-0-6b

# ---- E3: same model, AMX disabled in oneDNN ---------------------------------------------------
deploy qwen3-noamx qwen3-0-6b --as qwen3-noamx --env ONEDNN_MAX_CPU_ISA=AVX512_CORE_BF16
token
ask qwen3-noamx "What is the capital of France? Answer in one word." "Paris"
evidence qwen3-noamx
bench qwen3-noamx E3-qwen0.6b-noamx 32 1 2 4 8 16
log "UNDEPLOY qwen3-noamx"; ./model-manager undeploy qwen3-noamx

# ---- E4: realistic 3B model, AMX on -----------------------------------------------------------
deploy qwen2-5-3b --id Qwen/Qwen2.5-3B-Instruct --name qwen2-5-3b --memory 32Gi
token
ask qwen2-5-3b "What is the capital of France? Answer in one word." "Paris"
evidence qwen2-5-3b
bench qwen2-5-3b E4-qwen2.5-3b-amx 16 1 2 4 8
log "UNDEPLOY qwen2-5-3b"; ./model-manager undeploy qwen2-5-3b

kubectl get nodes -o json | jq '.items[0].status.capacity' > $R/node-capacity.json
log "EXPERIMENTS DONE"
