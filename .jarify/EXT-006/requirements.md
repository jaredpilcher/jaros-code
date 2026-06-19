---
id: EXT-006
title: Deterministic Local Inference
status: partial
priority: high
implementation:
  - file: harness/ollama_client.py
    ranges:
      - - 1
        - 120
---

This spec serves **Tenets 2 & 3** of PRIME-001. The stock adapter calls Ollama with
default sampling (temperature ~0.8), so gemma2:2b answers the *same* prompt
differently across runs — observed directly: a task the harness can solve fails
intermittently purely from sampling variance. Greedy, seeded decoding makes a small
model both more reliable and more reproducible, without changing the model. The
intelligence still comes from the harness; we simply stop adding avoidable noise.

### [REQ-1] Greedy, seeded Ollama client

A `LlmClient` implementation calls local Ollama with temperature 0 and a fixed seed
so a given prompt yields a stable, repeatable completion. It uses only the local
gemma2:2b endpoint (no paid/cloud inference, Tenet 2).

#### Acceptance Criteria
- [ ] Implement the `LlmClient` contract: `complete(LlmRequest) -> LlmResponse`
- [ ] Send Ollama options `temperature: 0` and a fixed `seed` by default
- [ ] Select the model from `OLLAMA_MODEL` (default `gemma2:2b`); standard library only
- [ ] Allow per-request overrides via `LlmRequest.params` (e.g. temperature, seed, num_predict)

### [REQ-2] Harness uses deterministic inference by default

The coding loop builds its LLM through this client so every reasoning step is greedy
and repeatable by default.

#### Acceptance Criteria
- [ ] `harness.coding_loop.build_llm` returns the deterministic client
- [ ] The same prompt returns identical text across repeated calls (greedy)
- [ ] A failed Ollama call raises a clear, surfaced error (never silent)
