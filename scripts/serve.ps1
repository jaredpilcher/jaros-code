# Boot the jaros-code node pinned to the only model the Prime Directive permits:
# Gemma 4 2B (e2b) via llama.cpp on the Jetson Orin Nano (Tenet 2 — small-model-only,
# zero paid inference). PRIME-001: llama.cpp/Jetson is the exclusive model path.
# To verify the Jetson is serving first, run: bash scripts/jetson_serve.sh

# #EXT-014-REQ-1 Start
$env:JCODE_LLM_BACKEND = if ($env:JCODE_LLM_BACKEND) { $env:JCODE_LLM_BACKEND } else { "llamacpp" }
$env:LLAMACPP_HOST = if ($env:LLAMACPP_HOST) { $env:LLAMACPP_HOST } else { "http://192.168.1.183:8000" }
$env:JAROS_DATA_DIR = Join-Path $PSScriptRoot "..\.jaros-data"

# Legacy Ollama back-compat: ONLY activated when JCODE_LLM_BACKEND=ollama is explicitly set.
# NOT the default. NOT the intended model. Retained for back-compat only.
if ($env:JCODE_LLM_BACKEND -eq "ollama") {
    $env:JAROS_LLM_PROVIDER = "ollama"
    $env:OLLAMA_MODEL = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { "gemma2:2b" }
    $env:OLLAMA_HOST = if ($env:OLLAMA_HOST) { $env:OLLAMA_HOST } else { "http://localhost:11434" }
    Write-Host "[jaros-code] [LEGACY] serving with model=$($env:OLLAMA_MODEL) provider=ollama (back-compat only; set JCODE_LLM_BACKEND=llamacpp for the intended path)"
} else {
    Write-Host "[jaros-code] serving with backend=$($env:JCODE_LLM_BACKEND) host=$($env:LLAMACPP_HOST) (Gemma 4 2B e2b / llama.cpp / Jetson)"
}
# #EXT-014-REQ-1 End

jaros serve @args
