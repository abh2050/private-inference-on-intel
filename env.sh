# Shared settings. Source this file; do not run it directly.  ->  source ./env.sh
# Everything this experiment creates on IBM Cloud starts with $PREFIX, so teardown can find it.

export PATH="$HOME/.local/bin:$PATH"   # ibmcloud CLI was installed here (no sudo)
export GODEBUG=netdns=cgo              # the CLI's built-in DNS times out on this Mac, so use the system resolver
export PREFIX="${PREFIX:-opea-ei}"
export IBM_REGION="${IBM_REGION:-us-east}"          # Washington DC, the closest IBM region to AWS us-east-2 (Ohio)
export IBM_ZONE="${IBM_ZONE:-us-east-1}"
export IBM_RG="${IBM_RG:-Default}"                  # resource group name
# bx3d = IBM VPC gen-3 "balanced" profile on 4th Gen Xeon (Sapphire Rapids, has AMX).
# 32 vCPU / 160 GB. 01-preflight.sh confirms the CPU; 03-node-hwcheck.sh proves AMX on the box.
export IBM_PROFILE="${IBM_PROFILE:-bx3d-32x160}"
export BOOT_GB="${BOOT_GB:-250}"                    # 250 GB is the largest boot volume IBM allows
export SSH_PUBKEY="${SSH_PUBKEY:-$HOME/.ssh/opea_ei_ed25519.pub}"

# Cost guards
export MAX_HOURS="${MAX_HOURS:-4}"                  # watchdog deletes everything after this many hours
export EST_USD_PER_HOUR="${EST_USD_PER_HOUR:-1.90}" # ESTIMATE for bx3d-32x160 + volume + IP. Replace with the
                                                    # number from cloud.ibm.com/estimator before you provision.
export MONTHLY_CAP_USD="${MONTHLY_CAP_USD:-150}"

# Pinned, reproducible software versions (checked 2026-11-03)
export SOLUTIONS_REPO="https://github.com/intel/enterprise-ai-solutions.git"
export SOLUTIONS_REF="v1.1.0"                       # pins intel/enterprise-inference to v1.0.1 (5d92bef)
export MODEL_NAME="${MODEL_NAME:-qwen3-0-6b}"       # catalog entry: Qwen/Qwen3-0.6B, 8 cores, 16Gi, vLLM CPU 0.24.0

export STATE_DIR="${STATE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/.state}"
mkdir -p "$STATE_DIR"
