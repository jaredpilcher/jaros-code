#!/usr/bin/env bash
# Reconnect the Jetson inference endpoint: (re)start llama-server if it isn't running.
# Idempotent — safe to call any time the endpoint is down (e.g. after the device is
# moved/rebooted; llama-server is NOT a systemd service so it does not auto-start).
#   bash scripts/jetson_serve.sh            # start if down, report status
set -uo pipefail
HOST="${1:-jetson}"   # ssh alias (see ~/.ssh/config) or user@ip
LAUNCH='/home/jared/llama.cpp/build/bin/llama-server -m /home/jared/models/gemma-4-e2b-Q4_K_M.gguf --alias gemma-4-e2b --host 0.0.0.0 --port 8000 --n-gpu-layers 99 --ctx-size 4096 --flash-attn on --jinja --reasoning off --threads 4'

ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" "
  if pgrep -f llama-server >/dev/null; then echo 'ALREADY_RUNNING'; else
    nohup $LAUNCH > /home/jared/llama-server.log 2>&1 &
    sleep 3
    pgrep -f llama-server >/dev/null && echo 'STARTED' || { echo 'FAILED_TO_START'; tail -5 /home/jared/llama-server.log; }
  fi
"
