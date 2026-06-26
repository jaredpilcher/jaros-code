# EXT-006 — Deterministic Local Inference

```text
   stock OllamaAdapter                 DeterministicOllamaClient (harness, legacy back-compat)
   ───────────────────────            ─────────────────────────────────────
   POST /api/generate                 POST /api/generate
     model, prompt, stream=false        model, prompt, stream=false,
                                        options={ temperature:0, seed:S, ... }
   → sampled (temp ~0.8)              → greedy, repeatable
```

Same endpoint, same legacy Ollama `gemma2:2b` model (back-compat path; the INTENDED
model is Gemma 4 2B (`e2b`) served by llama.cpp — see REQ-4), same two-plane discipline — only the
sampling changes. Greedy decoding removes a noise source that was making solvable
tasks fail intermittently, and makes a run's reasoning repeatable, which tightens
the replay guarantee (PRIME-001 Tenet 3) for the model step itself.

`build_llm()` returns this client, so every agent in the loop reasons greedily by
default. Per-request `LlmRequest.params` can still override temperature/seed for the
rare agent that benefits from sampling (e.g. proposing diverse candidates), keeping
the door open for swarm strategies later — but the default is deterministic.
