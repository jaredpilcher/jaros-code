#!/usr/bin/env bash
# Launch the jaros-code CLI (Claude-Code-like REPL) on local gemma2:2b. POSIX.
#   bash scripts/jcode.sh                 # interactive REPL
#   bash scripts/jcode.sh /status         # one command and exit
#   bash scripts/jcode.sh "fix foo.py"    # one plain-language request
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export JAROS_LLM_PROVIDER="ollama"
export OLLAMA_MODEL="${OLLAMA_MODEL:-gemma2:2b}"
export PYTHONIOENCODING="utf-8"
cd "$ROOT"
exec python -m harness.cli "$@"
