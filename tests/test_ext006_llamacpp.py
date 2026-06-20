"""EXT-006 REQ-2 llama.cpp backend: payload/parse + backend selection, all without a
running server (deterministic). Confirms the harness is ready to point at a llama-server
(e.g. on the Jetson) by flipping JCODE_LLM_BACKEND, before the endpoint exists.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jaros.llm import LlmRequest  # noqa: E402
from harness.llamacpp_client import DeterministicLlamaCppClient  # noqa: E402


def test_payload_is_chat_completions_greedy_seeded():
    c = DeterministicLlamaCppClient(model="gemma4:e2b-it-qat", host="http://jetson:8080", seed=7)
    p = c.build_payload(LlmRequest(prompt="hello"))
    assert p["messages"] == [{"role": "user", "content": "hello"}]
    assert p["temperature"] == 0 and p["seed"] == 7 and p["stream"] is False
    assert c.host == "http://jetson:8080"  # trailing slash stripping etc.


def test_per_request_params_override_and_num_predict_maps():
    c = DeterministicLlamaCppClient()
    p = c.build_payload(LlmRequest(prompt="x", params={"temperature": 0.6, "seed": 3, "num_predict": 128}))
    assert p["temperature"] == 0.6 and p["seed"] == 3
    assert p["max_tokens"] == 128  # ollama-style num_predict -> openai max_tokens


def test_parse_response_extracts_assistant_text():
    resp = {"choices": [{"message": {"role": "assistant", "content": "  def f(): pass  "}}]}
    assert DeterministicLlamaCppClient.parse_response(resp) == "def f(): pass"


def test_build_llm_selects_llamacpp_backend(monkeypatch):
    from harness import coding_loop
    monkeypatch.setenv("JCODE_LLM_BACKEND", "llamacpp")
    llm = coding_loop.build_llm()
    assert isinstance(llm, DeterministicLlamaCppClient)


def test_build_llm_defaults_to_llamacpp(monkeypatch):
    # Inference now runs on the Jetson (llama.cpp) by default, not Ollama.
    from harness import coding_loop
    monkeypatch.delenv("JCODE_LLM_BACKEND", raising=False)
    llm = coding_loop.build_llm()
    assert isinstance(llm, DeterministicLlamaCppClient)


def test_build_llm_ollama_still_selectable(monkeypatch):
    from harness import coding_loop
    monkeypatch.setenv("JCODE_LLM_BACKEND", "ollama")
    llm = coding_loop.build_llm()
    assert type(llm).__name__ == "DeterministicOllamaClient"
