#!/usr/bin/env bash
# Deletes EVERYTHING this experiment created (any resource whose name starts with $PREFIX), then checks that nothing is left.
# Safe to run more than once. Needs CONFIRM=yes.
set -uo pipefail
source "$(dirname "$0")/env.sh"
[[ "${CONFIRM:-}" == "yes" ]] || { echo "Run as:  CONFIRM=yes ./99-teardown.sh"; exit 1; }
ibmcloud target -r "$IBM_REGION" -g "$IBM_RG" >/dev/null

ids() { ibmcloud is "$1" --output json 2>/dev/null | jq -r ".[] | select(.name|startswith(\"$PREFIX\")) | .id"; }

for id in $(ids floating-ips); do ibmcloud is floating-ip-release "$id" -f; done
for id in $(ids instances);    do ibmcloud is instance-delete "$id" -f; done   # its boot volume is deleted too

echo "Waiting for instances to finish deleting..."
for _ in $(seq 1 60); do [[ -z "$(ids instances)" ]] && break; sleep 10; done

for id in $(ids volumes);  do ibmcloud is volume-delete "$id" -f; done          # catches a boot volume left behind
for id in $(ids subnets);  do ibmcloud is subnet-delete "$id" -f; done
for _ in $(seq 1 30); do [[ -z "$(ids subnets)" ]] && break; sleep 5; done
for id in $(ids vpcs);     do ibmcloud is vpc-delete "$id" -f; done
for id in $(ids keys);     do ibmcloud is key-delete "$id" -f; done

# Stop the watchdog if this is a manual teardown
[[ -f "$STATE_DIR/watchdog_pid" ]] && kill "$(cat "$STATE_DIR/watchdog_pid")" 2>/dev/null

if [[ -f "$STATE_DIR/started_at" ]]; then
  hrs=$(echo "scale=2; ($(date -u +%s) - $(cat "$STATE_DIR/started_at"))/3600" | bc)
  echo "Ran for $hrs h  ->  estimated cost ~\$$(echo "$hrs * $EST_USD_PER_HOUR" | bc)" | tee -a "$STATE_DIR/session-costs.log"
  rm -f "$STATE_DIR/started_at"
fi

echo "== Leftovers check (every line should say 0)"
left=0
for t in instances floating-ips volumes subnets vpcs keys; do
  n=$(ids "$t" | grep -c . || true); echo "  $t: $n"; left=$((left+n))
done
[[ $left -eq 0 ]] && echo "CLEAN: nothing left that bills." || { echo "WARNING: $left resources left. Run this script again."; exit 1; }
