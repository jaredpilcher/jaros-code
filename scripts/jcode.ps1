# Launch the jaros-code CLI (Claude-Code-like REPL) on local gemma2:2b. Windows.
#   pwsh scripts/jcode.ps1                 # interactive REPL
#   pwsh scripts/jcode.ps1 /status         # one command and exit
#   pwsh scripts/jcode.ps1 "fix foo.py"    # one plain-language request
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$env:JAROS_LLM_PROVIDER = "ollama"
if (-not $env:OLLAMA_MODEL) { $env:OLLAMA_MODEL = "gemma2:2b" }
$env:PYTHONIOENCODING = "utf-8"
Set-Location $root
python -m harness.cli @args
