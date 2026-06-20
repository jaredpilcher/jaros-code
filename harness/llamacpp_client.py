"""Deterministic llama.cpp server client (EXT-006 / REQ-2).

Mirrors DeterministicOllamaClient but targets a llama.cpp `llama-server` (e.g. on a
Jetson Orin Nano reached over the LAN), which speaks a different API than Ollama. Uses
the OpenAI-compatible `/v1/chat/completions` endpoint so the model's own chat template is
applied (important for instruction-tuned Gemma), with greedy + seeded decoding for
repeatability. Still a LOCAL model only — no paid/cloud inference (PRIME-001 Tenet 2);
pointing at the Jetson on the LAN is the intended local-inference path, not internet egress.

Config via env (so the only switch needed is setting these):
  JCODE_LLM_BACKEND=llamacpp      # select this client (see coding_loop.build_llm)
  LLAMACPP_HOST=http://HOST:8080  # llama-server base URL (default port 8080)
  LLAMACPP_MODEL=<label>          # optional label for telemetry (server serves one gguf)
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request

from jaros.llm import LlmRequest, LlmResponse

from harness.ollama_client import _DEFAULT_SEED, _record_call


class DeterministicLlamaCppClient:
    """Greedy, seeded llama.cpp adapter satisfying the `LlmClient` contract."""

    def __init__(self, model: str | None = None, host: str | None = None,
                 seed: int = _DEFAULT_SEED) -> None:
        self.model = model or os.environ.get(
            "LLAMACPP_MODEL", os.environ.get("OLLAMA_MODEL", "gemma-4-e2b"))
        # Default to the Jetson llama-server on the LAN (override via LLAMACPP_HOST).
        self.host = (host or os.environ.get("LLAMACPP_HOST", "http://192.168.1.183:8000")).rstrip("/")
        self.seed = seed
        # A generation is ~2s on the Jetson; cap the call so a stalled/half-open socket
        # (e.g. the device gets moved mid-request) fails in ~60s instead of hanging the
        # whole eval. The hung HumanEval run was each cascade attempt burning the old 180s.
        self.timeout = float(os.environ.get("LLAMACPP_TIMEOUT_S", "90"))

    def build_payload(self, req: LlmRequest) -> dict:
        """Construct the /v1/chat/completions body (pure — unit-testable without a server)."""
        params = {"temperature": 0, "seed": self.seed}
        if isinstance(getattr(req, "params", None), dict):
            params.update(req.params)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": req.prompt}],
            "temperature": params.get("temperature", 0),
            "seed": params.get("seed", self.seed),
            "stream": False,
        }
        # ALWAYS bound the output. Without this the model can run away to the context
        # limit on certain prompts (it never emits a clean stop) — that, not the device,
        # is what made HumanEval_39/_63 "hang". A code file fits comfortably in the default.
        n = params.get("num_predict", params.get("max_tokens",
                       int(os.environ.get("LLAMACPP_MAX_TOKENS", "1024"))))
        payload["max_tokens"] = n
        return payload

    @staticmethod
    def parse_response(resp: dict) -> str:
        """Pull the assistant text out of an OpenAI-style chat completion response."""
        return (resp["choices"][0]["message"]["content"] or "").strip()

    def complete(self, req: LlmRequest) -> LlmResponse:
        data = json.dumps(self.build_payload(req)).encode("utf-8")
        t0 = time.time()
        last_exc = None
        # Retry transient connection drops (the device gets moved/rebooted); a few short
        # backoffs ride out a blip without failing the whole cycle. Long outages are
        # handled upstream by the runner's endpoint health-gate.
        for attempt in range(3):
            request = urllib.request.Request(
                f"{self.host}/v1/chat/completions",
                data=data, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    resp = json.loads(response.read().decode("utf-8"))
                    text = self.parse_response(resp)
                    _record_call(self.model, time.time() - t0, len(req.prompt), len(text))
                    return LlmResponse(text=text, model=self.model)
            except urllib.error.URLError as exc:
                # A read timeout (server too slow on THIS prompt) won't get better by
                # retrying — fail fast. Only retry genuine connection drops (refused/reset).
                if isinstance(getattr(exc, "reason", None), (TimeoutError, socket.timeout)):
                    raise RuntimeError(f"llama.cpp timed out >{self.timeout}s ({self.model} @ {self.host})")
                last_exc = exc
                time.sleep(2 * (attempt + 1))
            except (TimeoutError, socket.timeout):
                raise RuntimeError(f"llama.cpp timed out >{self.timeout}s ({self.model} @ {self.host})")
            except Exception as exc:  # response/parse error — fail fast, surfaced (Tenet 3)
                raise RuntimeError(f"llama.cpp complete failed ({self.model} @ {self.host}): {exc}")
        raise RuntimeError(f"llama.cpp unreachable after retries ({self.model} @ {self.host}): {last_exc}")


def health(host: str | None = None, timeout: float = 8.0) -> dict:
    """Probe a llama-server: returns {ok, status, models?} — used to verify the endpoint
    before we switch the harness onto it. /v1/models is the OpenAI-style discovery route."""
    base = (host or os.environ.get("LLAMACPP_HOST", "http://192.168.1.183:8000")).rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/v1/models", timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8"))
            return {"ok": True, "host": base,
                    "models": [m.get("id") for m in body.get("data", [])]}
    except Exception as exc:
        return {"ok": False, "host": base, "error": str(exc)}
