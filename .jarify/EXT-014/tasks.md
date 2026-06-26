# Implementation Tasks — EXT-014 Gemma 4 2B (e2b) exclusive model migration

### [TASK-1] Default + exclusive runtime model

Make Gemma 4 2B (`e2b`)/llama.cpp the default + exclusive runtime selection.

#### Steps
1. Set `.jaros-data/config/llm.json` to the llama.cpp backend + Gemma 4 2B (`e2b`); update serve scripts.
2. Default the LLM backend selection to llama.cpp in code (Ollama only if explicitly requested).

#### Implements
- [REQ-1] Gemma 4 2B (e2b)/llama.cpp is the default and exclusive runtime model

### [TASK-2] Migrate Jarify spec docs to Gemma 4 2B (e2b)

#### Steps
1. In `.jarify/EXT-00*/` and `EXT-01*/` intent/requirements/design, replace `gemma2:2b`-as-the-model with Gemma 4 2B (`e2b`); serving via llama.cpp; legacy Ollama mentions explicitly labeled.
2. Keep meaning intact; do not alter requirement IDs or structure.

#### Implements
- [REQ-2] All Jarify spec docs reference Gemma 4 2B (e2b)

### [TASK-3] Migrate project docs

#### Steps
1. Update README.md, CLAUDE.md, docs/ARCHITECTURE.md, docs/CATALOG.md, docs/HANDOFF.md, SAFETY.md to name Gemma 4 2B (`e2b`)/llama.cpp.
2. CLAUDE.md governance/design sections: replace "all reasoning is local gemma2:2b via Ollama".

#### Implements
- [REQ-3] All project docs reference Gemma 4 2B (e2b)/llama.cpp

### [TASK-4] Migrate agent/tool/harness docstrings + comments

#### Steps
1. Update model-naming docstrings/comments in `.jaros-data/agents/*` and `.jaros-data/tools/*`.
2. Update harness module docstrings/comments (humaneval/mbpp/report/eval_runner/honesty/coding_loop/cli/agentic_eval). DOCSTRING-ONLY — no behavior change.

#### Implements
- [REQ-4] Agent/tool/harness docstrings + comments updated

### [TASK-5] Mark the legacy Ollama path

#### Steps
1. Add a clear legacy/back-compat header to `harness/ollama_client.py`; ensure no default/serve script makes it the default.
2. Run the test suite to confirm no functional regression.

#### Implements
- [REQ-5] Legacy Ollama path clearly marked, never default

### [TASK-6] Restore traceability (index.json) for 5 specs

#### Steps
1. Use `jarify-manage-links` to generate `index.json` for EXT-002, EXT-004, EXT-007, EXT-011, EXT-012 from code anchors.
2. Note any REQ with no clear code anchor.

#### Implements
- [REQ-6] Traceability restored for specs missing index.json
