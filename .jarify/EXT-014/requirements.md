---
id: EXT-014
title: Gemma 4 2B (e2b) exclusive model — migrate all references
status: partial
priority: high
implementation:
  - file: .jaros-data/config/llm.json
    ranges:
      - - 1
        - 40
---

# EXT-014 — Gemma 4 2B (e2b) is the exclusive model; migrate all references

PRIME-001 now states the exclusive model is **Gemma 4 2B (`e2b`) served by llama.cpp** on the Jetson;
the legacy Ollama `gemma2:2b` path is not the intended model. But ~55 files (specs, agents, tools, docs,
harness, scripts) still name `gemma2:2b`/Ollama as THE model — a Tenet-4 stale-spec defect surfaced by
the governance compliance loop. This spec migrates every reference so the whole repo is consistent with
the Prime Directive, and makes Gemma 4 2B (`e2b`)/llama.cpp the default + exclusive runtime model.
Functional backend code may retain a legacy Ollama client, but it must be clearly marked legacy and
never the default.

### [REQ-1] Gemma 4 2B (e2b)/llama.cpp is the default and exclusive runtime model

The runtime selects Gemma 4 2B (`e2b`) via llama.cpp by default; no path silently uses another model.

#### Acceptance Criteria
- [ ] `.jaros-data/config/llm.json` (and the serve scripts) default to the llama.cpp backend + Gemma 4 2B (`e2b`)
- [ ] Code default for the LLM backend is llama.cpp (Ollama only if explicitly selected, marked legacy)
- [ ] A single source of truth names the model; no hard-coded `gemma2:2b` as "the model" in active paths

### [REQ-2] All Jarify spec docs reference Gemma 4 2B (e2b)

Every `.jarify/*` intent/requirements/design references Gemma 4 2B (`e2b`), not `gemma2:2b` as the model.

#### Acceptance Criteria
- [ ] EXT-001..013 spec docs updated (model name = Gemma 4 2B (`e2b`); serving = llama.cpp)
- [ ] No spec presents `gemma2:2b` as the current/intended model (legacy mentions explicitly labeled)
- [ ] Consistent with PRIME-001/intent.md

### [REQ-3] All project docs reference Gemma 4 2B (e2b)/llama.cpp

README, CLAUDE.md, docs/ARCHITECTURE.md, docs/CATALOG.md, docs/HANDOFF.md, SAFETY.md updated.

#### Acceptance Criteria
- [ ] Each doc names Gemma 4 2B (`e2b`)/llama.cpp as the model/backend
- [ ] CLAUDE.md governance/design sections no longer say "all reasoning is local gemma2:2b via Ollama"
- [ ] Legacy Ollama mentions are explicitly labeled legacy

### [REQ-4] Agent/tool/harness docstrings + comments updated

Source-level references in agents, tools, and harness modules name Gemma 4 2B (`e2b`).

#### Acceptance Criteria
- [ ] Agent docstrings (editor/rewriter/test_writer/orchestrator/...) updated where they name the model
- [ ] Harness module docstrings/comments updated (humaneval/mbpp/report/eval_runner/honesty/coding_loop/...)
- [ ] No active comment claims `gemma2:2b` is the model; behavior unchanged (docstring-only edits)

### [REQ-5] Legacy Ollama path clearly marked, never default

The Ollama `gemma2:2b` client may remain for back-compat but is unambiguously legacy.

#### Acceptance Criteria
- [ ] `ollama_client.py` header marks it legacy/back-compat, not the intended model
- [ ] No serve script or config makes Ollama the default
- [ ] Tests still pass (no functional regression)

### [REQ-6] Traceability restored for specs missing index.json

Compliance: EXT-002, EXT-004, EXT-007, EXT-011, EXT-012 lack `index.json`.

#### Acceptance Criteria
- [ ] `index.json` generated (via jarify-manage-links) for EXT-002/004/007/011/012 from code anchors
- [ ] Each maps its REQs to the implementing files/ranges; missing-anchor cases noted
