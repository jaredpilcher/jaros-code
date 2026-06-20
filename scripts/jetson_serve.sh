#!/usr/bin/env bash
# Ensure the Jetson inference endpoint is up. The device runs llama-server as the
# systemd service `gemma.service` (Gemma 4 E2B, llama.cpp/CUDA), which is ENABLED and
# auto-starts on boot and restarts on crash — so normally nothing is needed after a
# move/reboot. This is a manual nudge in case it's stopped.
#   bash scripts/jetson_serve.sh           # start gemma.service if not active, report status
set -uo pipefail
HOST="${1:-jetson}"   # ssh alias (see ~/.ssh/config) or user@ip

ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" '
  if [ "$(systemctl is-active gemma)" = active ]; then
    echo "ALREADY_RUNNING (gemma.service active on :8000)"
  else
    sudo systemctl start gemma && sleep 5
    echo "start -> is-active=$(systemctl is-active gemma)"
  fi
  systemctl is-enabled gemma | sed "s/^/autostart-on-boot: /"
'
