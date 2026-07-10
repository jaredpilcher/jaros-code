"""EXT-036 REQ-49: deterministic tool-calling AGENT-LOOP SCAFFOLD repair -- the direct analog of
the ``http.server`` scaffold repair (REQ-48) for the "agent" real-systems class.

MEASURED (``.jaros-data/artifacts/realsys_agent.log``, 2026-07-09, the FIRST on-Jetson agent
build, ``plain-tool-calling-agent`` 0/3): gemma writes an agent that never correctly performs the
mechanical OpenAI tool-call protocol boilerplate `harness.agent_oracle` pins as the injection
contract:

- 2 of 3 builds made ZERO tool calls at all (``tool_call count mismatch: expected 2, got 0``) --
  no request/dispatch loop was ever wired, or it silently swallowed every ``tool_calls`` turn.
- 1 of 3 builds extracted the WRONG field for a tool's arguments (``args mismatch: ... got
  {'tool_call_id': 'call_1...``) -- it read the tool-call's own ``id``/``tool_call_id`` instead of
  ``["function"]["arguments"]``, a classic protocol-shape confusion (several sibling string keys
  on the same JSON object), not a reasoning failure.

This is a TWO-PLANE fix in the same shape as the already-landed ``http.server`` scaffold (REQ-48):
the MODEL's job is the judgement of WHICH tool to call and why (that reasoning happens entirely at
RUNTIME, inside the actual chat-completions turn the agent sends to the real/stub model -- it is
never baked into build-time code); the DETERMINISTIC tool's job is the surrounding MECHANICAL
protocol boilerplate -- the request/response loop, the ``tool_calls[].function.name`` +
``json.loads(...function.arguments...)`` extraction, the POST to ``{JAROS_TOOL_URL}/<name>``, the
observation feed-back into the message list, and the ``__JAROS_AGENT_FINAL__...__END__`` sentinel
on termination.

**Design choice vs. the http.server scaffold (REQ-48):** REQ-48 recognizes and PRESERVES a
distinct judgement fragment gemma already wrote (a request-dispatcher function) and wires it into
a generated skeleton, because that fragment IS the model's judgement (which endpoint does what).
Here there is no equivalent fragment worth preserving: the entire agent LOOP is fixed, standard
OpenAI-tool-calling boilerplate (the same shape for every task in this class -- only the runtime
tool choices differ, and those come from the model's live completions responses, not from
build-time code). So when the built agent's loop is not already correct, this module generates the
COMPLETE, DETERMINISTIC, standard agent-loop skeleton wholesale (mirroring the exact shape proven
correct by ``tests/test_ext060_agent_task.py``'s ``CORRECT_PLAIN_AGENT``/
``_AGENT_UNGUARDED_BASELINE_PY`` fixtures) rather than trying to salvage or wire a broken
extraction fragment -- there is nothing salvageable in "read the wrong JSON key".

Non-degrading: fires ONLY when the spec demands this exact tool-calling agent contract
(``OPENAI_BASE_URL``/``JAROS_TOOL_URL``/``tool_calls`` conventions) AND no module already contains
a loop that correctly performs BOTH the chat-completions round-trip AND the ``function.name`` +
``json.loads(...arguments...)`` extraction -- an already-working agent (including one with EXTRA,
task-specific logic layered on top, e.g. the step-guard MODIFY task) is left completely untouched.
Never raises.
"""
# #EXT-036-REQ-49 Start
from __future__ import annotations

import re

_AGENT_INDICATOR_RE = re.compile(
    r"\bOPENAI_BASE_URL\b|\bJAROS_TOOL_URL\b|\btool[- _]calling\b|\btool_calls\b",
    re.IGNORECASE,
)
_CHAT_ENDPOINT_RE = re.compile(r"chat[/_]completions", re.IGNORECASE)
_TOOL_URL_INDICATOR_RE = re.compile(r"\bJAROS_TOOL_URL\b")
_TOOL_CALLS_FIELD_RE = re.compile(r"tool_calls")
# The correct name-extraction shape: `...["function"]["name"]` (subscript or attribute-ish
# `.get(...)` chaining), never a bare `["name"]` off the tool-call itself (that would silently
# grab nothing, since a raw tool_call dict has no top-level "name" key).
_FUNCTION_NAME_RE = re.compile(
    r"\[\s*[\"']function[\"']\s*\]\s*\[\s*[\"']name[\"']\s*\]"
    r"|\.get\(\s*[\"']function[\"']\s*(?:,\s*(?:\{\}|None))?\s*\)\s*(?:\.get\(|\[)\s*[\"']name[\"']",
)
# The correct args-extraction shape: `json.loads(...)` applied to something whose text mentions
# "arguments" -- NOT `tool_call_id`/`id` (the measured wrong-field bug). A loose but leak-free
# textual co-occurrence check (mirrors `has_real_serve_loop`'s style): never a full expression
# parse, just "does a json.loads(...) call's argument text mention arguments".
_ARGUMENTS_LOADS_RE = re.compile(r"json\.loads\([^)\n]*arguments[^)\n]*\)", re.IGNORECASE)
_FINAL_SENTINEL_RE = re.compile(r"__JAROS_AGENT_FINAL__")


def spec_demands_tool_calling_agent(spec_text: "str | None") -> bool:
    """True when the visible ``spec_text`` demands the pinned OpenAI-protocol tool-calling AGENT
    contract (``harness.agent_oracle``'s injection contract): it mentions
    ``OPENAI_BASE_URL``/``JAROS_TOOL_URL``/"tool calling"/``tool_calls`` AND separately requires a
    chat-completions round-trip (mentions "chat" + "completion", or the literal
    ``chat/completions`` path). Never raises -- any non-string or empty input is simply not a
    demand."""
    if not spec_text:
        return False
    text = str(spec_text)
    if not _AGENT_INDICATOR_RE.search(text):
        return False
    if _CHAT_ENDPOINT_RE.search(text):
        return True
    low = text.lower()
    return "chat" in low and "completion" in low


def has_correct_agent_loop(modules: "dict[str, str] | None") -> bool:
    """True when the built ``modules`` ALREADY correctly perform the full mechanical
    tool-calling protocol: a request loop against the ``JAROS_TOOL_URL``-addressed tool sandbox,
    reading a ``tool_calls`` field, extracting the tool name via ``["function"]["name"]`` (never
    a bare/wrong sibling key), decoding the arguments via ``json.loads(...)`` applied to the
    ``arguments`` field, and printing the ``__JAROS_AGENT_FINAL__`` sentinel on termination.

    The check is deliberately GENEROUS (matches across ALL modules combined, not just one) so
    this repair never touches an already-working build, including one that layers extra
    task-specific logic (e.g. a step-guard) on top of the same correct core loop. Never raises."""
    try:
        items = list((modules or {}).items())
    except (AttributeError, TypeError):
        return False
    combined_parts: "list[str]" = []
    for name, code in items:
        try:
            if not name or not str(name).endswith(".py") or not code:
                continue
            combined_parts.append(str(code))
        except Exception:
            continue
    if not combined_parts:
        return False
    combined = "\n".join(combined_parts)
    return bool(
        _TOOL_URL_INDICATOR_RE.search(combined)
        and _TOOL_CALLS_FIELD_RE.search(combined)
        and _FUNCTION_NAME_RE.search(combined)
        and _ARGUMENTS_LOADS_RE.search(combined)
        and _FINAL_SENTINEL_RE.search(combined)
    )


# The DETERMINISTIC, standard agent-loop skeleton -- the exact mechanical shape proven correct
# against `harness.agent_oracle` by `tests/test_ext060_agent_task.py`'s `CORRECT_PLAIN_AGENT` /
# `harness.real_systems_suite._AGENT_UNGUARDED_BASELINE_PY` fixtures (stdlib-only: json/os/sys/
# urllib.request -- no third-party dependency, never any network call except the two pinned
# endpoints the oracle -- or a real Jetson llama.cpp endpoint at build-run time -- hosts).
AGENT_SKELETON_PY = '''import json
import os
import sys
import urllib.request


def _post(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    goal = sys.argv[1] if len(sys.argv) > 1 else ""
    base_url = os.environ["OPENAI_BASE_URL"]
    tool_url = os.environ["JAROS_TOOL_URL"]
    messages = [{"role": "user", "content": goal}]

    while True:
        resp = _post(base_url + "/chat/completions", {"model": "stub", "messages": messages})
        message = resp["choices"][0]["message"]
        tool_calls = message.get("tool_calls")
        if tool_calls:
            call = tool_calls[0]
            name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"])
            messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
            observed = _post(tool_url + "/" + name, args)
            messages.append({
                "role": "tool", "tool_call_id": call.get("id"),
                "content": json.dumps(observed.get("observation")),
            })
            continue
        content = message.get("content") or ""
        print("__JAROS_AGENT_FINAL__" + content + "__END__", flush=True)
        return


if __name__ == "__main__":
    main()
'''


def generate_agent_skeleton() -> str:
    """Return the DETERMINISTIC, standard tool-calling agent-loop skeleton (:data:`AGENT_SKELETON_PY`).
    Pure string composition -- never executes anything, takes no arguments (the loop is fixed,
    standard boilerplate; the model's judgement is supplied entirely at RUNTIME through the actual
    chat-completions responses it sends, never baked into this generated code)."""
    return AGENT_SKELETON_PY


def _resolve_entry_name(modules: "dict[str, str]", spec_text: "str | None") -> str:
    from harness.filename_contract import demanded_filenames
    demanded = demanded_filenames(spec_text)
    if demanded:
        return demanded[0].split("/")[-1]
    if "main.py" in modules:
        return "main.py"
    py_mods = [k for k in modules if k.endswith(".py")]
    if len(py_mods) == 1:
        return py_mods[0]
    return "main.py"


def apply_agent_scaffold(modules: "dict[str, str]", spec_text: "str | None", *,
                          llm=None) -> "tuple[dict[str, str], list[str]]":
    """The public, never-raising repair: fires ONLY when ``spec_text`` demands the pinned
    tool-calling agent contract (:func:`spec_demands_tool_calling_agent`) AND no module in
    ``modules`` already correctly performs the full mechanical protocol
    (:func:`has_correct_agent_loop`).

    When it fires, REPLACES the spec-demanded entrypoint module (resolved via
    ``harness.filename_contract.demanded_filenames``, falling back to ``main.py``) with the
    DETERMINISTIC standard agent-loop skeleton (:func:`generate_agent_skeleton`) -- the mechanical
    request/parse/dispatch/sentinel boilerplate is fixed and standard for this class, so it is
    always generated wholesale rather than patched; the model's WHICH-tool judgement is supplied
    entirely at runtime by the actual (or, under the oracle, scripted-stub) model responses this
    skeleton faithfully relays, never by build-time code.

    ``llm`` is accepted for call-site/API parity with the sibling ``http.server`` scaffold
    (``harness.http_service_scaffold.apply_http_service_scaffold``) but is intentionally UNUSED:
    unlike that repair's dispatcher-handler recognition, there is no separable build-time
    judgement fragment here worth a clean-prompt retry over -- the fix is a fixed, deterministic
    skeleton every time.

    Returns a NEW dict (never mutates ``modules``) plus a list of explanatory notes. Never raises
    -- any internal failure leaves ``modules`` unchanged."""
    try:
        mods = dict(modules or {})
        notes: "list[str]" = []

        if not spec_demands_tool_calling_agent(spec_text):
            return mods, notes
        if not mods:
            return mods, notes

        if has_correct_agent_loop(mods):
            notes.append("a correct tool-call loop already exists -- no-op")
            return mods, notes

        entry_name = _resolve_entry_name(mods, spec_text)
        mods[entry_name] = generate_agent_skeleton()
        notes.append(
            f"no correct tool_calls[].function.name + json.loads(.arguments) extraction loop "
            f"found -- generated the standard deterministic agent-loop skeleton at {entry_name}"
        )
        return mods, notes
    except Exception as exc:
        try:
            fallback = dict(modules or {})
        except (TypeError, ValueError):
            fallback = {}
        return fallback, [f"apply_agent_scaffold failed -- no-op: {exc}"]
# #EXT-036-REQ-49 End
