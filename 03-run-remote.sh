#!/usr/bin/env bash
# Copies node/ to the server, checks for AMX, then runs install -> deploy+smoke -> bench in a tmux session.
# Usage: ./03-run-remote.sh            start everything (stops early if there is no AMX)
#        ./03-run-remote.sh attach     watch progress (detach with Ctrl-b d)
#        ./03-run-remote.sh collect    copy ~/results back into ./results/<timestamp>/
set -euo pipefail
source "$(dirname "$0")/env.sh"
FIP=$(cat "$STATE_DIR/fip"); K="-i ${SSH_PUBKEY%.pub} -o StrictHostKeyChecking=accept-new"; SSH="ssh $K ubuntu@$FIP"

case "${1:-run}" in
  attach)  exec ssh $K -t ubuntu@"$FIP" tmux attach -t ei ;;
  collect) d="results/$(date +%Y%m%d-%H%M)"; mkdir -p "$d"; scp $K -r ubuntu@"$FIP":results/. "$d/"; echo "Saved to $d"; exit 0 ;;
esac

scp $K -r node ubuntu@"$FIP":~/ >/dev/null
$SSH 'chmod +x ~/node/*.sh && ~/node/hwcheck.sh' || {
  echo "No AMX on this server. Tear it down (CONFIRM=yes ./99-teardown.sh) and pick a gen-3 (x3) profile."; exit 2; }

# Logging: every terminal line (timestamped) -> ~/results/logs/session.log; cluster snapshot every 60 s
$SSH "mkdir -p ~/results/logs; chmod +x ~/node/snapshot-loop.sh; nohup ~/node/snapshot-loop.sh >/dev/null 2>&1 &"
$SSH "sudo apt-get install -y -qq tmux >/dev/null; tmux new -d -s ei \
  'SOLUTIONS_REF=$SOLUTIONS_REF MODEL_NAME=$MODEL_NAME bash -c \"~/node/install.sh && ~/node/experiments.sh; echo ALL-DONE exit=\\\$?; exec bash\"'"
$SSH "tmux pipe-pane -o -t ei '~/node/ts-log.sh ~/results/logs/session.log'"
echo "Started. Install ~25 min, then experiments E2-E4 ~60-75 min."
echo "Watch:   ./03-run-remote.sh attach"
echo "Then:    ./03-run-remote.sh collect   and   CONFIRM=yes ./99-teardown.sh"
