#!/usr/bin/env bash
# Launch the jaros-code CLI (Claude-Code-like REPL) on local gemma2:2b. POSIX.
#   bash scripts/jcode.sh                 # interactive REPL
#   bash scripts/jcode.sh /status         # one command and exit
#   bash scripts/jcode.sh "fix foo.py"    # one plain-language request
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Inference on the Jetson (small Gemma 4 via llama.cpp), not Ollama. Override via env.
export JCODE_LLM_BACKEND="${JCODE_LLM_BACKEND:-llamacpp}"
export LLAMACPP_HOST="${LLAMACPP_HOST:-http://192.168.1.183:8000}"
export PYTHONIOENCODING="utf-8"
cd "$ROOT"
exec python -m harness.cli "$@"
