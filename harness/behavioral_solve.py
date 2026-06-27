"""harness/behavioral_solve.py — THE canonical behavioral solve (EXT-012 system).

The local 2B authors a Gherkin behavior spec (with a COMPREHENSION step that pins the exact case the
intent names, read literally), derives its OWN tests from that spec, implements the function, and fixes
the code against those tests. This is jaros-code's DEFAULT solve path — the integrated stack of the
mechanisms proven on held-out real commits:

  multi-function localize (caller's job) -> Gherkin + comprehension -> self-tests -> code -> fix.

Proven (intent-only, hidden-oracle, no leakage): more-itertools held-out 6/37 = 16.2% vs the
multi-function baseline 4/37 = 10.8%; cross-repo combined 7/48 vs 5/48 (see .jarify/EXT-012).

It is ENVIRONMENT-AGNOSTIC: `run_tests(code, test_code) -> (passed, feedback)` adapts it to the eval
(Docker on a repo checkout) or the product (`jcode` -> local pytest), so the evaluation harness and the
real product share exactly ONE solve. New mechanisms (retrieval, etc.) enter here as layers, measured
then kept or pruned — the system only moves forward.

EXT-013 / REQ-4 adds `behavioral_solve_jaros`: the same deterministic fix-loop, but every host effect
is performed via Runtime.apply(Decision) — gate -> executor -> DecisionLog — so each solve is
hash-chain logged and byte-identically replayable (Tenet 3), and the two-plane discipline (Tenet 1)
is enforced by the runtime rather than by convention.
"""
from __future__ import annotations

from typing import Callable

# The proven Gherkin grains currently live in commit_replay (the eval's first home); the eval will be
# refactored to import them from here. Reusing them keeps ONE implementation feeding both clients.
from harness.commit_replay import g_gherkin, g_selftests, g_code   # noqa: E402


def behavioral_solve(intent: str, name: str, current_src: str | None, context: str, pkg: str,
                     run_tests: Callable[[str, str], tuple[bool, str]],
                     max_fix: int = 2) -> dict:
    """Canonical behavioral solve. Returns {code, gherkin, tests, self_pass}.

    intent       : the change to make (commit message / user request).
    name         : the function to write/repair.
    current_src  : its current source, or None if new.
    context      : module preamble (imports/sentinels) the model can use.
    pkg          : import package for the self-tests (`from <pkg> import <name>`).
    run_tests    : env adapter: (candidate_code, test_code) -> (passed, short_feedback).
    """
    gherkin = g_gherkin(intent, name, current_src, context)          # behavior spec (+comprehension)
    tests = g_selftests(name, gherkin, pkg)                          # the model's OWN tests, from spec
    code = g_code(intent, name, current_src, context, gherkin)       # first implementation
    self_pass = False
    for _ in range(max_fix + 1):                                     # fix against its own tests
        if not code:
            break
        self_pass, feedback = run_tests(code, tests)
        if self_pass:
            break
        code = g_code(intent, name, current_src, context, gherkin, feedback)
    return {"code": code, "gherkin": gherkin, "tests": tests, "self_pass": self_pass}


# --- Agentic variant: bootstrap, then the 2B JUDGES the revision layer at each failure -------------
# Smoke finding: a free 2B-judge collapses to "code" — it won't even pick "run" among 2 options. So a
# small model can't run the mechanical control flow. Ground it: bootstrap (spec->tests->code) and the
# RUN are deterministic; the 2B's judgement goes where it adds value — when the self-tests FAIL,
# diagnose WHICH layer is wrong and revise it (emergent revision path, any layer revisited).
_REV = {"code": "the implementation has a LOGIC bug -> rewrite the code",
        "gherkin": "the behavior spec MISUNDERSTOOD the intent -> rewrite the spec (and its tests)",
        "repair": "the logic is right but the code has broken indentation/syntax",
        "done": "stop — it cannot be fixed"}


def _judge_revision(intent: str, name: str, fb: str, temp: float) -> str:
    """The 2B as a judge AT THE FAILURE: diagnose which layer to revise. One short call."""
    from harness.pass1_eval import _llm
    from jaros.llm import LlmRequest
    menu = "\n".join(f"  {a} = {d}" for a, d in _REV.items())
    prompt = (f"You are building the Python function `{name}`.\nGOAL: {intent}\n"
              f"Its self-tests FAILED with:\n{str(fb)[:400]}\n\n"
              f"Diagnose the cause and pick the SINGLE next action:\n{menu}\nAnswer with ONLY one word.")
    out = _llm().complete(LlmRequest(prompt=prompt,
                                     params={"temperature": temp, "max_tokens": 8})).text.strip().lower()
    return next((a for a in _REV if a in out), "code")


def behavioral_solve_agentic(intent: str, name: str, current_src: str | None, context: str, pkg: str,
                             run_tests: Callable[[str, str], tuple[bool, str]],
                             max_rounds: int = 4, temp: float = 0.0) -> dict:
    """Agentic behavioral solve: bootstrap (spec->tests->code), then auto-run + the 2B judges the
    REVISION layer at each failure (code / gherkin / repair / done) — emergent, layers revisited.
    temp>0 -> non-deterministic. Honest: self-tests scaffold; the hidden oracle scores (caller).
    Returns {code, gherkin, tests, self_pass, trace}."""
    from harness.commit_replay import g_gherkin as _gk, g_selftests as _gt, g_code as _gc
    gherkin = _gk(intent, name, current_src, context)
    tests = _gt(name, gherkin, pkg)
    code = _gc(intent, name, current_src, context, gherkin)
    trace = ["spec", "tests", "code"]
    passed = False
    for _ in range(max_rounds):
        passed, fb = run_tests(code, tests)
        trace.append("run")
        if passed:
            break
        a = _judge_revision(intent, name, str(fb), temp)
        trace.append(a)
        if a == "done":
            break
        if a == "gherkin":                                   # spec was wrong -> re-spec, re-test, re-code
            gherkin = _gk(intent, name, current_src, context)
            tests = _gt(name, gherkin, pkg)
            code = _gc(intent, name, current_src, context, gherkin, str(fb)[:400])
        elif a == "repair":
            from harness.pass1_eval import _bc, _llm
            code = _bc.repair_indentation(_llm(), code)
        else:                                                # "code": logic bug -> revise the code
            code = _gc(intent, name, current_src, context, gherkin, str(fb)[:400])
    return {"code": code, "gherkin": gherkin, "tests": tests, "self_pass": passed, "trace": trace}


# #EXT-013-REQ-4 Start
# ---- Jaros-native behavioral solve (EXT-013 / REQ-4) --------------------------------
#
# Attribution (EXT-012/design.md): deterministic fix-loop 7/37 >= agentic 2B-judge 6/37.
# The judge-agent is available (EXT-013/TASK-4) but NOT the driver here.  Every host
# effect is performed via Runtime.apply(Decision) so the full gate->executor->DecisionLog
# chain is enforced by the runtime — two-plane discipline by construction (Tenet 1) and
# hash-chain logged for byte-identical replay (Tenet 3).
#
# Flow: gherkin-agent -> test-writer-agent -> [augment] -> code-writer-agent -> run_tests
#       -> on fail: code-writer-agent (feedback) -> run_tests ... (bounded by max_fix)
# All decisions are applied through Runtime.apply; the solver is the DETERMINISTIC
# fix-loop (not the orchestrator judge-agent).
#
# EXT-012 REQ-13 (2026-06-27): docstring-derived self-test augmentation is now the
# DEFAULT in the Jaros-native path.  When ``augment_source`` is supplied (the visible
# parent-repo source text), self-tests are augmented after Grain 2 via the deterministic
# ``code.augment_selftests`` tool before the fix-loop starts.  This is the confirmed
# honest lift (2-run mean 8.5/37 vs 6.0/37 baseline).  Honesty: augmentation reads
# ONLY the visible docstring; the hidden oracle is never touched here.


def _load_agent_from_file(filepath: str, llm):
    """Load a Jaros agent from an absolute file path and call build(llm)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_agent_mod", filepath)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.build(llm)


def behavioral_solve_jaros(
    intent: str,
    name: str,
    current_src: str | None,
    context: str,
    pkg: str,
    runtime,
    *,
    llm=None,
    spec_path: str | None = None,
    test_path: str | None = None,
    code_path: str | None = None,
    test_command: str | None = None,
    test_cwd: str | None = None,
    max_fix: int = 2,
    pre_test_hook: "Callable[[str, str], None] | None" = None,
    augment_source: str | None = None,
) -> dict:
    """Jaros-native behavioral solve: same deterministic fix-loop as ``behavioral_solve``
    but every host effect routes through ``Runtime.apply(Decision)`` — gate -> executor ->
    DecisionLog — so the solve is hash-chain logged and byte-identically replayable.

    The driver is the **deterministic fix-loop** (NOT the orchestrator judge-agent), per
    the EXT-012/design.md attribution: deterministic 7/37 >= agentic 6/37.

    Parameters
    ----------
    intent        : commit message / user request describing the change.
    name          : Python function name to write/repair.
    current_src   : existing function source, or None if new.
    context       : module preamble (imports/sentinels) visible to the model.
    pkg           : import package for self-tests (``from <pkg> import <name>``).
    runtime       : a ``harness.coding_loop.Runtime`` instance (or compatible stub).
                    ALL host effects go through ``runtime.apply(Decision)``.
    llm           : LLM client; if None, ``harness.coding_loop.build_llm()`` is called.
    spec_path     : where to write the Gherkin spec (default ``.jcode/<name>.gherkin``).
    test_path     : where to write self-tests (default ``test_<name>.py``).
    code_path     : where to write the implementation (default ``.jcode/<name>.py``).
    test_command  : shell command to run self-tests (default ``python -m pytest <test_path>``).
    test_cwd      : working dir for the test command (default: None -> current dir).
    max_fix       : max repair iterations after the first attempt (default 2).
    pre_test_hook : optional ``(code: str, tests: str) -> None`` called (via the Runtime or
                    directly) BEFORE each test run to prepare the environment — e.g. apply
                    the generated code to the repo file before running Docker.  When provided,
                    the hook is called with the current candidate ``code`` and ``tests``
                    strings; any side effects (writing the file, staging test artefacts) are
                    the hook's responsibility.  The Runtime still issues the ``shell.exec``
                    Decision for the actual test run.
    augment_source : visible parent-repo source text for the target function (default None).
                    When provided, the model's self-tests are augmented with doctest-derived
                    assertions AFTER Grain 2 and BEFORE the fix-loop, via the deterministic
                    ``code.augment_selftests`` tool.  This is the EXT-012 REQ-13 confirmed
                    honest lift; it reads ONLY the visible docstring — never the hidden oracle.
                    If None, no augmentation is applied (graceful no-op).

    Returns
    -------
    dict with keys: code, gherkin, tests, self_pass, applied_decisions
        ``applied_decisions`` is the list of Decision types applied via Runtime.apply
        in order (useful for test assertions on the wiring sequence).
    """
    import os
    from pathlib import Path
    from harness import jaros_solve_ops as _ops

    # Resolve default artifact paths
    _sp = spec_path or f".jcode/{name}.gherkin"
    _tp = test_path or f"test_{name}.py"
    _cp = code_path or f".jcode/{name}.py"
    _tc = test_command or f"python -m pytest {_tp} -x -q"

    # Resolve LLM (lazy — avoid Jetson connection in tests that inject llm=stub)
    if llm is None:
        from harness.coding_loop import build_llm
        llm = build_llm()

    # Locate agents dir relative to this file (harness/../.jaros-data/agents/)
    _agents_dir = Path(__file__).resolve().parents[1] / ".jaros-data" / "agents"

    applied_decisions: list[str] = []          # ordered record of decision types applied

    def _apply(decision) -> dict:
        """Apply a Decision through the Runtime and record its type."""
        result = runtime.apply(decision)
        applied_decisions.append(decision.type)
        return result

    # --- Grain 1: Gherkin spec via GherkinWriterBoundary ---------------------------
    gherkin_agent = _load_agent_from_file(str(_agents_dir / "gherkin_agent.py"), llm)
    [gk_decision] = gherkin_agent.decide({
        "intent": intent, "name": name, "func": name,
        "current_src": current_src, "context": context,
        "spec_path": _sp,
    })
    _apply(gk_decision)
    # Extract the spec text from the decision payload (the agent embeds it there)
    gherkin: str = gk_decision.payload.get("content", "")

    # --- Grain 2: Self-tests via TestWriterBoundary --------------------------------
    test_agent = _load_agent_from_file(str(_agents_dir / "test_writer_agent.py"), llm)
    [tw_decision] = test_agent.decide({
        "intent": f"{intent}\n\nBehavior scenarios:\n{gherkin}",
        "module": pkg, "func": name,
        "signature": f"def {name}(...)",
        "test_path": _tp,
    })
    _apply(tw_decision)
    tests: str = tw_decision.payload.get("content", "")

    # #EXT-012-REQ-13 Start
    # --- Augment self-tests with doctest-derived assertions (EXT-012 REQ-13 default) ---
    # HONESTY: augment_source is the VISIBLE parent-repo source; never the hidden oracle.
    # Graceful no-op if augment_source is None or the target has no docstring examples.
    if augment_source is not None:
        try:
            import importlib.util as _ilu
            from pathlib import Path as _Path
            from types import SimpleNamespace as _SN
            _tools_dir = _Path(__file__).resolve().parents[1] / ".jaros-data" / "tools"
            _spec = _ilu.spec_from_file_location("_sat_tool", str(_tools_dir / "selftest_augmenter_tool.py"))
            _mod = _ilu.module_from_spec(_spec)    # type: ignore[arg-type]
            _spec.loader.exec_module(_mod)         # type: ignore[union-attr]
            _tool = _mod.SelftestAugmenterTool()
            _dec = _SN(payload={"name": name, "source": augment_source, "self_tests": tests},
                       type="code.augment_selftests")
            _v = _tool.validate(_dec)
            if _v.ok:
                tests = _tool.execute(_dec).get("self_tests", tests)
        except Exception:  # noqa: BLE001 — augmentation is best-effort; never block the solve
            pass
    # #EXT-012-REQ-13 End

    # --- Grain 3: First code implementation via CodeWriterBoundary -----------------
    code_agent = _load_agent_from_file(str(_agents_dir / "code_agent.py"), llm)
    [cw_decision] = code_agent.decide({
        "intent": intent, "name": name, "func": name,
        "current_src": current_src, "context": context,
        "gherkin": gherkin, "feedback": "",
        "code_path": _cp,
    })
    _apply(cw_decision)
    code: str = cw_decision.payload.get("content", "")

    # --- Deterministic fix-loop: run self-tests, repair/regen on failure -----------
    # Default driver: deterministic fix-loop (NOT the judge-agent).
    # EXT-012/design.md: deterministic 7/37 >= agentic 6/37; judge is available but
    # not the driver here — the bottleneck is generation, not orchestration.
    self_pass = False
    for _attempt in range(max_fix + 1):
        if not code:
            break
        # #EXT-013-REQ-5 Start
        # Prepare environment before each test run (e.g. apply code to repo file for Docker).
        if pre_test_hook is not None:
            pre_test_hook(code, tests)
        # #EXT-013-REQ-5 End
        # Run self-tests via shell.exec Decision (through Runtime, logged)
        run_result = _ops.run_tests(runtime, _tc, cwd=test_cwd, source="behavioral-solve-jaros")
        applied_decisions.append("shell.exec")
        exit_code = run_result.get("exitCode") if isinstance(run_result, dict) else None
        self_pass = exit_code == 0
        if self_pass:
            break
        if _attempt >= max_fix:
            break
        # Build feedback from the test output for the next code attempt
        stdout = run_result.get("stdout", "") if isinstance(run_result, dict) else ""
        stderr = run_result.get("stderr", "") if isinstance(run_result, dict) else ""
        feedback = (stdout + stderr)[:600]

        # Revise code via CodeWriterBoundary with feedback
        [cw_dec2] = code_agent.decide({
            "intent": intent, "name": name, "func": name,
            "current_src": current_src, "context": context,
            "gherkin": gherkin, "feedback": feedback,
            "code_path": _cp,
        })
        _apply(cw_dec2)
        code = cw_dec2.payload.get("content", "")

    return {
        "code": code,
        "gherkin": gherkin,
        "tests": tests,
        "self_pass": self_pass,
        "applied_decisions": applied_decisions,
    }
# #EXT-013-REQ-4 End
