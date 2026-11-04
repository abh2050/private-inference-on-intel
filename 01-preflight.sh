#!/usr/bin/env bash
# READ-ONLY. Creates nothing and costs nothing.
# Checks the IBM Cloud login, the account, and which Xeon / Gaudi profiles your account can launch.
set -euo pipefail
source "$(dirname "$0")/env.sh"

command -v ibmcloud >/dev/null || { echo "Install the IBM Cloud CLI first:  curl -fsSL https://clis.cloud.ibm.com/install/osx | sh"; exit 1; }
command -v jq >/dev/null || { echo "Install jq:  brew install jq"; exit 1; }
ibmcloud plugin show vpc-infrastructure >/dev/null 2>&1 || ibmcloud plugin install vpc-infrastructure -f

ibmcloud target -r "$IBM_REGION" -g "$IBM_RG" >/dev/null || { echo "Not logged in. Run:  ibmcloud login --sso"; exit 1; }
echo "== Account"; ibmcloud target
echo
echo "== Spend so far this month (trial or promo credits show up here)"
ibmcloud billing account-usage 2>/dev/null | head -25 || echo "(no billing permission, so check the console: Manage > Billing and usage)"

echo
echo "== Xeon profiles in $IBM_REGION (gen 3 'x3' = 4th Gen Xeon Sapphire Rapids, with AMX; gen 2 'x2' = Cascade/Ice Lake, NO AMX)"
ibmcloud is instance-profiles --output json \
 | jq -r '.[] | select(.name|test("^(bx|cx|mx)3")) | [.name, (.vcpu_count.value // .vcpu_count.default), .memory.value, (.vcpu_manufacturer.value // "?")] | @tsv' \
 | sort -V | column -t | head -30

echo
echo "== Is $IBM_PROFILE available in $IBM_REGION?"
if ibmcloud is instance-profile "$IBM_PROFILE" --output json >/dev/null 2>&1; then
  ibmcloud is instance-profile "$IBM_PROFILE" --output json | jq '{name, vcpu:.vcpu_count.value, mem_gb:.memory.value, arch:.vcpu_architecture.value, mfr:.vcpu_manufacturer.value, disks:.disks}'
else
  echo "NOT available here. Try another region:  IBM_REGION=us-south IBM_ZONE=us-south-1 ./01-preflight.sh"
fi

echo
echo "== Gaudi profiles (listed only; the current Intel stack does not support Gaudi, and these cost far more than \$150/month)"
ibmcloud is instance-profiles --output json | jq -r '.[] | select(.name|test("gaudi")) | .name' || true

echo
echo "== Images: Ubuntu 24.04 amd64"
ibmcloud is images --visibility public --output json \
 | jq -r '[.[] | select(.name|test("^ibm-ubuntu-24-04.*amd64")) | select(.status=="available")] | sort_by(.created_at) | last | "\(.name)  \(.id)"'

echo
echo "== Leftover resources from earlier runs (should be empty)"
ibmcloud is instances --output json | jq -r ".[] | select(.name|startswith(\"$PREFIX\")) | .name" || true
ibmcloud is vpcs --output json      | jq -r ".[] | select(.name|startswith(\"$PREFIX\")) | .name" || true

echo
cat <<EOF
== Cost estimate (CHECK IT at https://cloud.ibm.com/estimator before provisioning)
   Assumed rate:  \$$EST_USD_PER_HOUR/hour for $IBM_PROFILE + ${BOOT_GB} GB volume + floating IP
   One session:   $MAX_HOURS h  ->  ~\$$(echo "$EST_USD_PER_HOUR * $MAX_HOURS" | bc)
   Monthly cap:   \$$MONTHLY_CAP_USD  ->  at most ~$(echo "$MONTHLY_CAP_USD / $EST_USD_PER_HOUR" | bc) hours of running time
   IMPORTANT: 'd' profiles (bx3d) have local instance storage, so IBM keeps billing them while they are STOPPED.
              Only DELETING the server stops the charge. Use ./99-teardown.sh, not 'stop'.
EOF
