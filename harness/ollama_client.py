# #EXT-014-REQ-5 Start
# LEGACY / BACK-COMPAT ONLY — NOT THE INTENDED MODEL PATH
#
# This module implements the legacy Ollama `gemma2:2b` backend, retained solely for
# back-compatibility with environments that still run a local Ollama server.
#
# The EXCLUSIVE intended model is Gemma 4 2B (`e2b`) served by llama.cpp on the
# Jetson Orin Nano (PRIME-001, EXT-014). Select it via:
#   JCODE_LLM_BACKEND=llamacpp  (or leave unset — llama.cpp is the default)
#   LLAMACPP_HOST=http://192.168.1.183:8000
#
# The Ollama path is selected ONLY when JCODE_LLM_BACKEND=ollama is set explicitly.
# No serve script, config file, or code path may make Ollama the default (EXT-014 REQ-1).
# #EXT-014-REQ-5 End
"""Deterministic local Ollama client (EXT-006).

LEGACY back-compat module — see module header above. The active model is Gemma 4 2B
(`e2b`) via llama.cpp (PRIME-001 / EXT-014); this client is retained only for
environments that explicitly select `JCODE_LLM_BACKEND=ollama`.

A standard-library `LlmClient` that calls local Ollama with greedy, seeded decoding
(temperature 0, fixed seed) so gemma2:2b returns a stable, repeatable completion for
a given prompt. Local model only — no paid/cloud inference (PRIME-001 Tenet 2) — and
repeatable, which tightens the replay guarantee for the reasoning step (Tenet 3).
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from jaros.llm import LlmRequest, LlmResponse

# #EXT-006-REQ-1 Start
_DEFAULT_SEED = 7

# Model-call telemetry (EXT-006 / REQ-3): undeniable, ongoing proof that the LOCAL
# gemma2:2b is actually being invoked. Every real call increments a counter and
# appends to an audit log the owner can tail in real time.
_CALL_LOG = Path(__file__).resolve().parents[1] / ".jaros-data" / "artifacts" / "eval" / "model_calls.log"
_STATS = {"count": 0, "model": None, "totalLatencySec": 0.0, "lastCall": None}


def model_call_stats() -> dict:
    return dict(_STATS)


def reset_model_calls() -> None:
    _STATS.update(count=0, model=None, totalLatencySec=0.0, lastCall=None)


def _record_call(model: str, latency: float, prompt_len: int, resp_len: int) -> None:
    _STATS["count"] += 1
    _STATS["model"] = model
    _STATS["totalLatencySec"] = round(_STATS["totalLatencySec"] + latency, 3)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _STATS["lastCall"] = ts
    try:
        _CALL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_CALL_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{ts}  model={model}  latency={latency:.2f}s  prompt={prompt_len}c  resp={resp_len}c\n")
    except OSError:
        pass


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
        t0 = time.time()
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                resp = json.loads(response.read().decode("utf-8"))
                text = (resp.get("response", "") or "").strip()
                _record_call(self.model, time.time() - t0, len(req.prompt), len(text))
                return LlmResponse(text=text, model=self.model)
        except Exception as exc:  # surfaced, never silent (Tenet 3)
            raise RuntimeError(f"Ollama complete failed ({self.model}): {exc}")
# #EXT-006-REQ-1 End
