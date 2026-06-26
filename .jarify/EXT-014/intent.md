# Intent

EXT-014 exists to make the entire repository consistent with the Prime Directive's non-negotiable model
commitment: the single small local model is **Gemma 4 2B (`e2b`), served by llama.cpp** on the Jetson,
and it is the **exclusive** model — the only one the system ever calls. For a time the repo named the
legacy Ollama `gemma2:2b` path as if it were the model; every such stale reference is a Tenet-4 defect,
because specs, docs, and code must trace truthfully to the intent they serve. This spec migrates every
reference — Jarify specs, project docs, agent/tool/harness docstrings, serve scripts, and runtime
defaults — to Gemma 4 2B (`e2b`)/llama.cpp, and demotes the Ollama client to a clearly-labeled,
opt-in-only legacy path that is never the default. Its purpose is purely honesty and consistency: no
behavior change beyond guaranteeing that the system's stated and default model is the exclusive one the
Prime Directive demands. It serves PRIME-001 and never overrides it.
