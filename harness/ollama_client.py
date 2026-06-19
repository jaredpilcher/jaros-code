"""Deterministic local Ollama client (EXT-006).

A standard-library `LlmClient` that calls local Ollama with greedy, seeded decoding
(temperature 0, fixed seed) so gemma2:2b returns a stable, repeatable completion for
a given prompt. Local model only — no paid/cloud inference (PRIME-001 Tenet 2) — and
repeatable, which tightens the replay guarantee for the reasoning step (Tenet 3).
"""

from __future__ import annotations

import json
import os
import urllib.request

from jaros.llm import LlmRequest, LlmResponse

# #EXT-006-REQ-1 Start
_DEFAULT_SEED = 7


class DeterministicOllamaClient:
    """Greedy, seeded Ollama adapter satisfying the `LlmClient` contract."""

    def __init__(self, model: str | None = None, host: str | None = None,
                 seed: int = _DEFAULT_SEED) -> None:
        self.model = model or os.environ.get("OLLAMA_MODEL", "gemma2:2b")
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.seed = seed

    def complete(self, req: LlmRequest) -> LlmResponse:
        options = {"temperature": 0, "seed": self.seed}
        # Per-request overrides (e.g. temperature/seed/num_predict) win.
        if isinstance(getattr(req, "params", None), dict):
            options.update(req.params)
        payload = {
            "model": self.model,
            "prompt": req.prompt,
            "stream": False,
            "options": options,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.host.rstrip('/')}/api/generate",
            data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                resp = json.loads(response.read().decode("utf-8"))
                return LlmResponse(text=(resp.get("response", "") or "").strip(), model=self.model)
        except Exception as exc:  # surfaced, never silent (Tenet 3)
            raise RuntimeError(f"Ollama complete failed ({self.model}): {exc}")
# #EXT-006-REQ-1 End
