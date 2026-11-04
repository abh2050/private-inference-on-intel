#!/usr/bin/env bash
# Runs ON THE SERVER. E1: timed install of single-node Kubernetes + Intel AI for Enterprise Inference (pinned release).
# Writes ~/results/timeline.csv (phase,start,end,seconds,exit) and ~/results/friction.txt.
set -uo pipefail
SOLUTIONS_REPO="${SOLUTIONS_REPO:-https://github.com/intel/enterprise-ai-solutions.git}"
SOLUTIONS_REF="${SOLUTIONS_REF:-v1.1.0}"
mkdir -p ~/results; TL=~/results/timeline.csv
[[ -f $TL ]] || echo "phase,start_utc,end_utc,seconds,exit" > $TL

phase() {  # phase <name> <command...>   time one step and record whether it worked
  local name=$1; shift; local s e rc; s=$(date -u +%s)
  echo; echo "### PHASE $name  $(date -u +%T)"
  "$@"; rc=$?
  e=$(date -u +%s); echo "$name,$(date -u -d @$s +%T),$(date -u -d @$e +%T),$((e-s)),$rc" >> $TL
  [[ $rc -eq 0 ]] || { echo "PHASE $name FAILED (exit $rc)" | tee -a ~/results/friction.txt; exit $rc; }
}

phase os_packages bash -c 'sudo apt-get update -qq && sudo apt-get install -y -qq git jq curl tmux bc python3-yaml >/dev/null'
phase clone bash -c "[[ -d ~/eas ]] || git clone -q '$SOLUTIONS_REPO' ~/eas; cd ~/eas && git fetch --tags -q && git checkout -q '$SOLUTIONS_REF'"
cd ~/eas
echo "solutions: $(git describe --tags) $(git rev-parse HEAD)" | tee ~/results/versions.txt
phase configure ./es_auto_installer.sh configure --force   # without --force it waits at an interactive [y/N] prompt
phase init bash -c '[[ -d env/local ]] || ./es_auto_installer.sh init inference --env local'
echo "inference: $(git -C ext/enterprise.ai-inference rev-parse HEAD)" | tee -a ~/results/versions.txt
phase install_inference bash -c './es_auto_installer.sh install inference --env local 2>&1 | tee ~/results/install.log; exit ${PIPESTATUS[0]}'
phase validate bash -c './es_auto_installer.sh validate inference --env local 2>&1 | tee ~/results/validate.log; exit ${PIPESTATUS[0]}'

export KUBECONFIG=~/eas/env/local/kubeconfig.yaml
kubectl get nodes -o wide > ~/results/nodes.txt
kubectl get pods -A --no-headers | awk '$4!="Running" && $4!="Completed"' > ~/results/unhealthy-pods.txt

# Friction evidence from the Ansible log: retried steps, ignored errors, warnings
{
  echo "== Ansible retries:            $(grep -c 'FAILED - RETRYING' ~/results/install.log)"
  echo "== Ansible ignored failures:   $(grep -c '\.\.\.ignoring' ~/results/install.log)"
  echo "== Ansible fatal lines:        $(grep -c '^fatal:' ~/results/install.log)"
  echo "== Warnings:                   $(grep -c '\[WARNING\]' ~/results/install.log)"
  echo "== Top retried tasks:"; grep -B1 'FAILED - RETRYING' ~/results/install.log | grep -oE 'TASK \[[^]]+\]' | sort | uniq -c | sort -rn | head
  echo "== Unhealthy pods after install:"; cat ~/results/unhealthy-pods.txt
} | tee -a ~/results/friction.txt
