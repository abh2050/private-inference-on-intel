#!/usr/bin/env bash
# PAID. Creates: 1 VPC, 1 subnet, 1 SSH key, 1 VSI ($IBM_PROFILE), 1 floating IP. Only SSH from your IP is allowed in.
# Refuses to run unless you pass CONFIRM=yes. Starts a watchdog that runs 99-teardown.sh after $MAX_HOURS.
set -euo pipefail
source "$(dirname "$0")/env.sh"

if [[ "${CONFIRM:-}" != "yes" ]]; then
  echo "This creates PAID resources (~\$$EST_USD_PER_HOUR/hour, auto-deleted after $MAX_HOURS h)."
  echo "Re-run as:  CONFIRM=yes ./02-provision.sh"; exit 1
fi
[[ -f "$SSH_PUBKEY" ]] || { echo "No SSH public key at $SSH_PUBKEY (make one with: ssh-keygen -t ed25519)"; exit 1; }
ibmcloud target -r "$IBM_REGION" -g "$IBM_RG" >/dev/null

MYIP=$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')
IMAGE_ID=$(ibmcloud is images --visibility public --output json \
  | jq -r '[.[] | select(.name|test("^ibm-ubuntu-24-04.*amd64")) | select(.status=="available")] | sort_by(.created_at) | last | .id')
echo "Your IP: $MYIP   Image: $IMAGE_ID   Profile: $IBM_PROFILE   Zone: $IBM_ZONE"
date -u +%s > "$STATE_DIR/started_at"

j() { "$@" --output json; }   # run an ibmcloud command and return JSON

VPC_ID=$(j ibmcloud is vpc-create "$PREFIX-vpc" --resource-group-name "$IBM_RG" | jq -r .id)
echo "$VPC_ID" > "$STATE_DIR/vpc_id"
SUBNET_ID=$(j ibmcloud is subnet-create "$PREFIX-subnet" "$VPC_ID" --zone "$IBM_ZONE" --ipv4-address-count 16 | jq -r .id)
echo "$SUBNET_ID" > "$STATE_DIR/subnet_id"

# Use the VPC's default security group (it already allows all outbound). Add SSH from your IP only.
SG_ID=$(j ibmcloud is vpc "$VPC_ID" | jq -r .default_security_group.id)
ibmcloud is security-group-rule-add "$SG_ID" inbound tcp --port-min 22 --port-max 22 --remote "$MYIP" >/dev/null

KEY_ID=$(j ibmcloud is key-create "$PREFIX-key" @"$SSH_PUBKEY" --key-type ed25519 | jq -r .id)
echo "$KEY_ID" > "$STATE_DIR/key_id"

BOOT_JSON=$(jq -nc --arg n "$PREFIX-boot" --argjson c "$BOOT_GB" \
  '{name:($n+"-att"), delete_volume_on_instance_delete:true, volume:{name:$n, capacity:$c, profile:{name:"general-purpose"}}}')
INSTANCE_ID=$(j ibmcloud is instance-create "$PREFIX-node" "$VPC_ID" "$IBM_ZONE" "$IBM_PROFILE" "$SUBNET_ID" \
  --image "$IMAGE_ID" --keys "$KEY_ID" --boot-volume "$BOOT_JSON" | jq -r .id)
echo "$INSTANCE_ID" > "$STATE_DIR/instance_id"

# Start the watchdog right away, so the server gets deleted even if a later step fails.
nohup bash -c "sleep $((MAX_HOURS*3600)); cd '$(pwd)'; CONFIRM=yes ./99-teardown.sh" \
  > "$STATE_DIR/watchdog.log" 2>&1 &
echo $! > "$STATE_DIR/watchdog_pid"
echo "Watchdog PID $(cat "$STATE_DIR/watchdog_pid"): deletes everything at $(date -v+${MAX_HOURS}H 2>/dev/null || date -d "+$MAX_HOURS hour")"
echo "  (The watchdog only works while this Mac is awake. Also set a spending alert in the IBM console, see RUNBOOK.md.)"

echo "Waiting for the instance to start..."
for _ in $(seq 1 60); do
  st=$(j ibmcloud is instance "$INSTANCE_ID" | jq -r .status); [[ "$st" == running ]] && break; sleep 10
done
[[ "$st" == running ]] || { echo "Instance status is '$st'. Check it, then run ./99-teardown.sh"; exit 1; }

INST=$(j ibmcloud is instance "$INSTANCE_ID")
VNI=$(echo "$INST" | jq -r '.primary_network_attachment.virtual_network_interface.id // empty')
if [[ -n "$VNI" ]]; then BIND=(--vni "$VNI"); else BIND=(--nic "$(echo "$INST" | jq -r .primary_network_interface.id)"); fi
FIP=$(j ibmcloud is floating-ip-reserve "$PREFIX-fip" "${BIND[@]}" | jq -r .address)
[[ "$FIP" =~ ^[0-9.]+$ ]] || { echo "Floating IP failed. Run CONFIRM=yes ./99-teardown.sh"; exit 1; }
echo "$FIP" > "$STATE_DIR/fip"
echo
echo "Ready:  ssh -i ${SSH_PUBKEY%.pub} ubuntu@$FIP   (wait about 1 minute for cloud-init to finish)"
echo "Next:   ./03-run-remote.sh"
