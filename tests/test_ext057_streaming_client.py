"""EXT-057 REQ-1: streaming llama.cpp client — all OFFLINE, no network/server required.

Covers:
  (a) pure-parser: synthetic SSE lines -> reconstructed token stream (malformed/blank
      lines and both OpenAI-delta and llama.cpp-native `content` shapes tolerated).
  (b) byte-stability: build_payload(...) still emits "stream": False (non-streaming
      complete() path unchanged — Tenet 3).
  (c) clean termination: stream_complete() never hangs — it returns promptly both when
      the (stubbed) response ends early with no [DONE], and when the deadline trips
      while the (stubbed) response never produces anything.
"""

from __future__ import annotations

# #EXT-057-REQ-1 Start
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jaros.llm import LlmRequest  # noqa: E402
from harness.llamacpp_client import DeterministicLlamaCppClient  # noqa: E402


# ---------------------------------------------------------------------------
# (a) Pure-parser test — no socket, no thread, just the line -> delta helper.
# ---------------------------------------------------------------------------

def test_parse_sse_line_reconstructs_token_stream_skipping_bad_lines():
    lines = [
        'data: {"choices":[{"delta":{"content":"Hel"}}]}',   # OpenAI-delta shape
        "",                                                   # keep-alive blank -> skip
        "data: {this is not valid json}",                     # malformed -> skip
        'not-a-data-line',                                     # non "data:" line -> skip
        'data: {"choices":[{"delta":{"content":"lo"}}]}',
        'data: {"choices":[{"delta":{}}]}',                    # empty delta -> skip
        'data: {"content":" World"}',                          # llama.cpp native field
        'data: {"choices":[{"text":"!"}]}',                    # choices[0].text fallback
        "data: [DONE]",
        'data: {"choices":[{"delta":{"content":"unreachable"}}]}',  # after DONE -> never read
    ]

    collected = []
    for line in lines:
        token = DeterministicLlamaCppClient._parse_sse_line(line)
        if token is DeterministicLlamaCppClient._SSE_DONE:
            break
        if token:
            collected.append(token)

    assert "".join(collected) == "Hello World!"


def test_parse_sse_line_returns_none_for_blank_and_non_data_lines():
    assert DeterministicLlamaCppClient._parse_sse_line("") is None
    assert DeterministicLlamaCppClient._parse_sse_line("   ") is None
    assert DeterministicLlamaCppClient._parse_sse_line(": keep-alive comment") is None


def test_parse_sse_line_done_sentinel_is_distinct_from_none_and_str():
    done = DeterministicLlamaCppClient._parse_sse_line("data: [DONE]")
    assert done is DeterministicLlamaCppClient._SSE_DONE
    assert done is not None
    assert not isinstance(done, str)


# ---------------------------------------------------------------------------
# (b) Byte-stability — the non-streaming path is unchanged.
# ---------------------------------------------------------------------------

def test_build_payload_still_emits_stream_false():
    c = DeterministicLlamaCppClient(model="gemma4:e2b-it-qat", host="http://jetson:8080", seed=7)
    payload = c.build_payload(LlmRequest(prompt="hello"))
    assert payload["stream"] is False


def test_stream_complete_copies_payload_without_mutating_build_payload():
    c = DeterministicLlamaCppClient(host="http://fake-host:8080")
    req = LlmRequest(prompt="hi")
    before = c.build_payload(req)
    assert before["stream"] is False

    # Drive stream_complete (urlopen stubbed to fail immediately — no real network) and
    # confirm build_payload's own output is untouched afterward: the shared builder was
    # copied, never mutated in place.
    c.timeout = 0.05

    def _boom(req, timeout=None):
        raise OSError("connection refused")

    with patch("urllib.request.urlopen", _boom):
        list(c.stream_complete(req))

    after = c.build_payload(req)
    assert after["stream"] is False
    assert before["stream"] is False  # the original dict object was never mutated


# ---------------------------------------------------------------------------
# (c) Clean termination — never hangs.
# ---------------------------------------------------------------------------

def _fake_cm(iter_values):
    """A MagicMock context manager whose iteration yields `iter_values`."""
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cm)
    cm.__exit__ = MagicMock(return_value=False)
    cm.__iter__ = MagicMock(return_value=iter(iter_values))
    return cm


def test_stream_complete_terminates_on_early_close_without_done_sentinel():
    """Response ends (StopIteration) without ever sending [DONE] -> generator must
    still return promptly with whatever tokens it collected, never hang waiting."""
    lines = [
        b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n',
        b'data: {"choices":[{"delta":{"content":" there"}}]}\n',
    ]
    cm = _fake_cm(lines)
    c = DeterministicLlamaCppClient(host="http://fake-host:8080")
    c.timeout = 5.0  # generous — early close should finish long before this

    t0 = time.time()
    with patch("urllib.request.urlopen", lambda req, timeout=None: cm):
        tokens = list(c.stream_complete(LlmRequest(prompt="hi")))
    elapsed = time.time() - t0

    assert "".join(tokens) == "Hi there"
    assert elapsed < 3.0, f"early-close stream took {elapsed:.2f}s — should return promptly"


def test_stream_complete_terminates_on_hard_deadline_when_response_never_yields():
    """Response never produces a line (simulated hang) -> generator must still return
    once the hard wall-clock deadline passes, never block the caller indefinitely."""

    def _hanging_iter():
        time.sleep(5.0)  # far longer than the client's timeout below
        yield b'data: {"choices":[{"delta":{"content":"late"}}]}\n'

    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cm)
    cm.__exit__ = MagicMock(return_value=False)
    cm.__iter__ = MagicMock(side_effect=lambda: _hanging_iter())

    c = DeterministicLlamaCppClient(host="http://fake-host:8080")
    c.timeout = 0.2  # hard deadline well under the 5s hang

    t0 = time.time()
    with patch("urllib.request.urlopen", lambda req, timeout=None: cm):
        tokens = list(c.stream_complete(LlmRequest(prompt="hi")))
    elapsed = time.time() - t0

    assert tokens == []  # deadline hit before any token arrived
    assert elapsed < 2.0, f"deadline-bound stream took {elapsed:.2f}s — must abandon promptly"


def test_stream_complete_terminates_cleanly_on_connection_error():
    """urlopen raising mid-connect must not raise out of the generator or hang it."""
    c = DeterministicLlamaCppClient(host="http://fake-host:8080")
    c.timeout = 1.0

    def _boom(req, timeout=None):
        raise OSError("connection refused")

    t0 = time.time()
    with patch("urllib.request.urlopen", _boom):
        tokens = list(c.stream_complete(LlmRequest(prompt="hi")))
    elapsed = time.time() - t0

    assert tokens == []
    assert elapsed < 2.0
# #EXT-057-REQ-1 End
