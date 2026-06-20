# Launch the jaros-code CLI (Claude-Code-like REPL) on local gemma2:2b. Windows.
#   pwsh scripts/jcode.ps1                 # interactive REPL
#   pwsh scripts/jcode.ps1 /status         # one command and exit
#   pwsh scripts/jcode.ps1 "fix foo.py"    # one plain-language request
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
# Inference on the Jetson (small Gemma 4 via llama.cpp), not Ollama. Override via env.
if (-not $env:JCODE_LLM_BACKEND) { $env:JCODE_LLM_BACKEND = "llamacpp" }
if (-not $env:LLAMACPP_HOST) { $env:LLAMACPP_HOST = "http://192.168.1.183:8000" }
$env:PYTHONIOENCODING = "utf-8"
Set-Location $root
python -m harness.cli @args
