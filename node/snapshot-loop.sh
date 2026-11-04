#!/usr/bin/env bash
export KUBECONFIG=~/eas/env/local/kubeconfig.yaml
while true; do
  {
    echo "===== $(date -u +%FT%TZ) ====="
    echo "-- load: $(cut -d' ' -f1-3 /proc/loadavg)   mem: $(free -g | awk '/Mem:/{print $3"G used / "$2"G"}')   disk /: $(df -h / | awk 'NR==2{print $3" used / "$2}')"
    kubectl get pods -A -o wide --no-headers 2>/dev/null | awk '{printf "%-28s %-55s %-10s restarts=%s\n",$1,$2,$4,$5}'
    echo "-- events (last 60s, warnings first)"
    kubectl get events -A --sort-by=.lastTimestamp 2>/dev/null | tail -15
  } >> ~/results/logs/cluster-snapshots.log
  sleep 60
done
