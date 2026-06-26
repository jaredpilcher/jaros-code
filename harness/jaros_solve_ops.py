"""Deterministic solve operations exposed as Runtime-applied Decisions (EXT-013 / REQ-2).

Every host effect used by the behavioral solve is expressed here as a typed
Decision applied via ``Runtime.apply(decision)`` — never a raw Python call — so
the full two-plane discipline (Tenet 1) is enforced by the Runtime gate:
  gate -> executor -> DecisionLog

Three ops:

  write_artifact(rt, path, content, *, source)
      Write spec/tests/code via the ``code.write_file`` tool.

  run_tests(rt, command, *, cwd, timeout_s, source)
      Run a test command via the ``shell.exec`` tool; returns the result dict.

  repair_syntax(rt, content, *, seed, source)
      Parse-gated syntax repair via the ``code.repair`` tool; returns the
      (possibly unchanged) content string.

All three accept the ``Runtime`` instance as their first argument so they share
the same DecisionLog/TransitionLog within a solve run.

Note: importing this module does NOT connect to the Jetson or the LLM; the
repair op only calls the LLM if the content doesn't parse (the parse gate is
deterministic and skips the call when code is valid).
"""

from __future__ import annotations

import uuid

from jaros.core import create_decision

# #EXT-013-REQ-2 Start

_DEFAULT_TIMEOUT_S = 15
_DEFAULT_SOURCE = "jaros-solve"


def write_artifact(rt, path: str, content: str, *, source: str = _DEFAULT_SOURCE) -> dict:
    """Write an artifact (gherkin spec, tests, or code) to *path* via the
    ``code.write_file`` tool through ``Runtime.apply``.

    Returns the tool result dict (keys: tool, path, applied, created, bytesAfter).
    Raises RuntimeError if the gate rejects the Decision (e.g. content exceeds the
    size cap or triggers the code-safety filter).
    """
    decision = create_decision(
        id=f"write-{uuid.uuid4().hex}",
        source=source,
        type="code.write_file",
        payload={"path": path, "content": content},
    )
    return rt.apply(decision)


def run_tests(
    rt,
    command: str,
    *,
    cwd: str | None = None,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
    source: str = _DEFAULT_SOURCE,
) -> dict:
    """Run *command* via the ``shell.exec`` tool through ``Runtime.apply``.

    Returns the tool result dict (keys: tool, command, exitCode, stdout, stderr,
    timedOut).  Raises RuntimeError if the gate rejects the Decision (e.g. the
    command contains a denied pattern such as a network call).
    """
    payload: dict = {"command": command, "timeout_s": timeout_s}
    if cwd is not None:
        payload["cwd"] = cwd
    decision = create_decision(
        id=f"shell-{uuid.uuid4().hex}",
        source=source,
        type="shell.exec",
        payload=payload,
    )
    return rt.apply(decision)


def repair_syntax(
    rt,
    content: str,
    *,
    seed: int = 0,
    source: str = _DEFAULT_SOURCE,
) -> str:
    """Invoke parse-gated ``repair_indentation`` via the ``code.repair`` tool
    through ``Runtime.apply``.

    If *content* already parses cleanly the tool returns it unchanged (fast
    path — no LLM call).  Otherwise the tool calls the LLM to re-indent.

    To inject a stub LLM in tests (avoiding Jetson), call
    ``repair_tool.set_llm_factory(fn)`` before invoking this function, and
    ``repair_tool.set_llm_factory(None)`` after.  The factory is kept at the
    module level in ``repair_tool`` (NOT in the Decision payload) because
    ``create_decision`` enforces JSON-only payloads.

    Returns the (possibly repaired) Python source string.
    Raises RuntimeError if the gate rejects the Decision (e.g. empty content).
    """
    decision = create_decision(
        id=f"repair-{uuid.uuid4().hex}",
        source=source,
        type="code.repair",
        payload={"content": content, "seed": seed},
    )
    result = rt.apply(decision)
    return result.get("content", content)

# #EXT-013-REQ-2 End
