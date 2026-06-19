# Boot the jaros-code node pinned to the only model the Prime Directive permits:
# local Ollama gemma2:2b (Tenet 2 — small-model-only, zero paid inference).
# The Jaros Ollama adapter selects its model from OLLAMA_MODEL, so we pin it here.
$env:JAROS_LLM_PROVIDER = "ollama"
$env:OLLAMA_MODEL = "gemma2:2b"
$env:OLLAMA_HOST = if ($env:OLLAMA_HOST) { $env:OLLAMA_HOST } else { "http://localhost:11434" }
$env:JAROS_DATA_DIR = Join-Path $PSScriptRoot "..\.jaros-data"
Write-Host "[jaros-code] serving with model=$($env:OLLAMA_MODEL) provider=$($env:JAROS_LLM_PROVIDER)"
jaros serve @args
