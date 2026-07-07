"""EXT-057 REQ-2 — the stream-bus event vocabulary + `coding_loop.solve_streaming`.

Verifies the event factories match the SHARED CONTRACT and that `solve_streaming` yields the right
ordered event sequence in both modes (real-orchestration via `solve_fn`, and model-direct streaming),
never raising out of the generator. All stubbed — NO network, NO Jetson.
"""
# #EXT-057-REQ-2 Start
from harness import stream_bus
from harness.coding_loop import solve_streaming


def _types(events):
    return [e["type"] for e in events]


# --- stream_bus vocabulary --------------------------------------------------------------------

def test_event_factories_match_contract():
    assert stream_bus.assistant_token("hi") == {"type": "assistant_token", "text": "hi"}
    assert stream_bus.tool_start("read") == {"type": "tool_start", "name": "read"}
    tr = stream_bus.tool_result("tests", ok=False, summary="1 failed")
    assert tr == {"type": "tool_result", "name": "tests", "ok": False, "summary": "1 failed"}
    assert stream_bus.done("final") == {"type": "done", "final": "final"}
    for factory in (stream_bus.thinking, stream_bus.ask, stream_bus.cancel):
        assert stream_bus.is_valid(factory("x"))
    assert not stream_bus.is_valid({"type": "bogus"})
    assert not stream_bus.is_valid("not a dict")


# --- mode A: real orchestration via solve_fn (capability preserved) ---------------------------

def test_solve_streaming_runs_real_orchestration_and_yields_final():
    def fake_route_plain(line):
        return (f"solved: {line}", "agent")   # (text, label) shape, like cli._route_plain

    events = list(solve_streaming("fix foo.py", llm=None, solve_fn=fake_route_plain))
    types = _types(events)
    assert types[0] == "thinking"           # working indicator up front (never a dead cursor)
    assert "assistant_token" in types
    assert types[-1] == "done"
    assert events[-1]["final"] == "solved: fix foo.py"


def test_solve_streaming_solve_fn_plain_string_return():
    events = list(solve_streaming("hi", solve_fn=lambda line: "plain answer"))
    assert events[-1] == {"type": "done", "final": "plain answer"}


def test_solve_streaming_solve_fn_error_never_raises():
    def boom(line):
        raise RuntimeError("orchestration blew up")

    events = list(solve_streaming("x", solve_fn=boom))   # must NOT raise
    assert _types(events)[-1] == "done"
    assert "error:" in events[-1]["final"]


# --- mode B: model-direct token streaming -----------------------------------------------------

class _StreamingLlm:
    def stream_complete(self, req):
        for tok in ("Hello", ", ", "world"):
            yield tok


class _BlockingLlm:
    class _R:
        text = "blocking answer"

    def complete(self, req):
        return self._R()


def test_solve_streaming_streams_model_tokens():
    events = list(solve_streaming("say hi", llm=_StreamingLlm()))
    toks = [e["text"] for e in events if e["type"] == "assistant_token"]
    assert toks == ["Hello", ", ", "world"]        # streamed token-by-token
    assert events[-1] == {"type": "done", "final": "Hello, world"}


def test_solve_streaming_falls_back_to_blocking_complete():
    events = list(solve_streaming("say hi", llm=_BlockingLlm()))
    assert events[-1] == {"type": "done", "final": "blocking answer"}
    assert any(e["type"] == "assistant_token" and e["text"] == "blocking answer" for e in events)


def test_solve_streaming_cancel_stops_early():
    calls = {"n": 0}

    def cancel_after_one():
        calls["n"] += 1
        return calls["n"] >= 1   # cancel immediately after the first token

    events = list(solve_streaming("x", llm=_StreamingLlm(), on_cancel=cancel_after_one))
    assert any(e["type"] == "cancel" for e in events)
    assert _types(events)[-1] == "done"
# #EXT-057-REQ-2 End
