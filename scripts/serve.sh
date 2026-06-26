#!/usr/bin/env bash
# Boot the jaros-code node pinned to the only model the Prime Directive permits:
# Gemma 4 2B (e2b) via llama.cpp on the Jetson Orin Nano (Tenet 2 — small-model-only,
# zero paid inference). PRIME-001: llama.cpp/Jetson is the exclusive model path.
# To verify the Jetson is serving first, run: bash scripts/jetson_serve.sh
set -euo pipefail

# #EXT-014-REQ-1 Start
export JCODE_LLM_BACKEND="${JCODE_LLM_BACKEND:-llamacpp}"
export LLAMACPP_HOST="${LLAMACPP_HOST:-http://192.168.1.183:8000}"
export JAROS_DATA_DIR="$(cd "$(dirname "$0")/.." && pwd)/.jaros-data"

# Legacy Ollama back-compat: ONLY activated when JCODE_LLM_BACKEND=ollama is explicitly set.
# NOT the default. NOT the intended model. Retained for back-compat only.
if [ "${JCODE_LLM_BACKEND}" = "ollama" ]; then
    export JAROS_LLM_PROVIDER="ollama"
    export OLLAMA_MODEL="${OLLAMA_MODEL:-gemma2:2b}"
    export OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
    echo "[jaros-code] [LEGACY] serving with model=$OLLAMA_MODEL provider=ollama (back-compat only; set JCODE_LLM_BACKEND=llamacpp for the intended path)"
else
    echo "[jaros-code] serving with backend=$JCODE_LLM_BACKEND host=$LLAMACPP_HOST (Gemma 4 2B e2b / llama.cpp / Jetson)"
fi
# #EXT-014-REQ-1 End

exec jaros serve "$@"
