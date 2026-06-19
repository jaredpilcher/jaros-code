#!/usr/bin/env bash
# Boot the jaros-code node pinned to the only model the Prime Directive permits:
# local Ollama gemma2:2b (Tenet 2 — small-model-only, zero paid inference).
# The Jaros Ollama adapter selects its model from OLLAMA_MODEL, so we pin it here.
set -euo pipefail
export JAROS_LLM_PROVIDER="ollama"
export OLLAMA_MODEL="gemma2:2b"
export OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
export JAROS_DATA_DIR="$(cd "$(dirname "$0")/.." && pwd)/.jaros-data"
echo "[jaros-code] serving with model=$OLLAMA_MODEL provider=$JAROS_LLM_PROVIDER"
exec jaros serve "$@"
