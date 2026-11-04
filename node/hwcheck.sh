#!/usr/bin/env bash
# Runs ON THE SERVER. Proves which Xeon generation this is and whether AMX is present. Writes ~/results/hwcheck.txt
set -uo pipefail
mkdir -p ~/results; out=~/results/hwcheck.txt
{
  echo "== date: $(date -u +%FT%TZ)"
  echo "== CPU"; lscpu | grep -E 'Model name|^CPU\(s\)|Thread|Core|Socket|NUMA node|L3'
  echo "== AMX / AVX-512 flags"
  for f in amx_tile amx_bf16 amx_int8 avx512f avx512_bf16 avx512_vnni; do
    grep -qw "$f" /proc/cpuinfo && echo "  $f: YES" || echo "  $f: no"
  done
  echo "== Memory"; free -g | head -2
  echo "== Disks"; lsblk -d -o NAME,SIZE,TYPE,MODEL
  echo "== OS"; . /etc/os-release; echo "  $PRETTY_NAME, kernel $(uname -r)"
  echo "== Gaudi devices"; ls /dev/accel* 2>/dev/null || echo "  none (expected on a Xeon VM)"
} | tee "$out"

if grep -qw amx_tile /proc/cpuinfo && grep -qw amx_bf16 /proc/cpuinfo; then
  echo "RESULT: AMX present. vLLM CPU will use AMX (oneDNN) for bf16 matmuls."
else
  echo "RESULT: NO AMX. This is not a 4th Gen Xeon or newer. The stack still runs, but results are not an AMX test." >&2
  exit 2
fi
