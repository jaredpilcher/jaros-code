# Design — EXT-014: Gemma 4 2B (e2b) exclusive-model migration

## Overview

PRIME-001 declares the exclusive runtime model to be **Gemma 4 2B (`e2b`) served by llama.cpp**
on the Jetson, while the legacy Ollama `gemma2:2b` path is retained only for back-compat and must
never be the default. This spec is a **consistency migration**: it makes the runtime default the
llama.cpp backend from a single source of truth, and sweeps every stale `gemma2:2b`/Ollama
reference across the four documentation/reference layers so the whole repo agrees with the Prime
Directive. Almost all changes are docstring/comment/spec-text edits (no behavior change); the one
functional invariant is that no active code path silently selects a non-default model, and the
legacy Ollama client is explicitly labeled legacy. REQ-6 additionally restores `index.json`
traceability for specs that lacked it.

## The single source of truth and the reference layers

```text
                    .jaros-data/config/llm.json          scripts/serve.ps1 / serve.sh
                    (backend=llamacpp, model=            (mirror the same default when
                     Gemma 4 2B e2b)  ── SOURCE OF ──►    booting the Jetson node)
                              │           TRUTH
                              ▼
                    harness LLM backend selection
                    (llama.cpp default; Ollama only if
                     JCODE_LLM_BACKEND=ollama, marked legacy)
                              │
        ┌─────────────────────┼──────────────────────┬───────────────────────┐
        ▼                     ▼                      ▼                       ▼
  LAYER 1: config       LAYER 2: .jarify        LAYER 3: project        LAYER 4: source
  + serve scripts       spec docs (EXT-001..)   docs (README, CLAUDE.md, docstrings/comments
  [REQ-1]               [REQ-2]                 ARCHITECTURE, ...)      in agents/tools/harness
                                                [REQ-3]                 [REQ-4]

  LEGACY path (REQ-5): ollama_client.py header marks it legacy/back-compat, never default.
  TRACEABILITY (REQ-6): regenerate index.json for EXT-002/004/007/011/012 from code anchors.
```

## Migration invariants

- **One name, one place.** The model identity lives in `llm.json` (mirrored by the serve
  scripts); no active path hard-codes `gemma2:2b` as "the model."
- **Default is llama.cpp + Gemma 4 2B (`e2b`).** Ollama is reachable only by explicit
  `JCODE_LLM_BACKEND=ollama` selection and is unambiguously labeled legacy everywhere it appears.
- **Docs-only where possible.** Layers 2–4 are text edits that must not change behavior; the
  suite stays green as proof of no functional regression.
- **Consistency with PRIME-001 is the acceptance bar** — a stale spec is a Tenet-4 defect, which
  is exactly what this migration retires.
