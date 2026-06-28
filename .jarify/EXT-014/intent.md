# Intent

EXT-014 exists to make the entire repository consistent with the Prime Directive's model commitment:
every reasoning call goes to a single **local, on-device, zero-cost** open-weight model served by
**llama.cpp** on the Jetson Orin Nano — the binding rule is local + fits-the-device + free, never a
cloud or paid model. The system **began** on **Gemma 4 2B (`e2b`)**, and as of the 2026-06-27 owner
directive the specific model is a permitted lever: it may move to a stronger open-weight model that
still fits the Jetson (Gemma 4 2B remains the baseline + honest comparison anchor). For a time the repo
named the legacy Ollama `gemma2:2b` path as if it were the model; every such stale reference is a
Tenet-4 defect, because specs, docs, and code must trace truthfully to the intent they serve. This spec
keeps every reference — Jarify specs, project docs, agent/tool/harness docstrings, serve scripts, and
runtime defaults — consistent with the **local-on-device/llama.cpp** rule and the *currently selected*
model, and keeps the Ollama client a clearly-labeled, opt-in-only legacy path that is never the default.
Its purpose is honesty and consistency: the system's stated and default model is always the actual
on-device model the Prime Directive demands. It serves PRIME-001 and never overrides it.
