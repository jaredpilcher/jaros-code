"""Bounded edit->test->judge coding loop (EXT-003).

Composes the EXT-002 single-purpose agents and EXT-001 deterministic tools into a
multi-step coding loop, routing every Decision through the real Jaros gate +
executor + decision log so each step is validated, executed, and recorded (replay
faithful). The transcript mirrors Claude Code's look and feel.

Only `editor` and `test-reader` call Gemma 4 2B (`e2b`) (the reasoning steps). Everything
else is deterministic: the model decides *what*, the executor and tools decide *how*.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# Windows consoles default to cp1252; force UTF-8 so the transcript never crashes.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from jaros.core import create_decision
from jaros.core.decision_gate import validate_decision
from jaros.execution import executor
from jaros.execution.handlers import make_advance_handler
from jaros.execution.tools import load_custom_tools
from jaros.llm import LlmConfig, create_llm_client
from jaros.state import DecisionLog, TransitionLog, record_decision

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / ".jaros-data"
AGENTS_DIR = DATA_DIR / "agents"
TOOLS_DIR = DATA_DIR / "tools"
# #EXT-014-REQ-1 Start
def _active_model_label() -> str:
    """The model actually serving inference, for honest banners/reports (Tenet 3).

    Default backend is llamacpp (Gemma 4 2B e2b on Jetson).
    Legacy Ollama path (gemma2:2b) only reached when JCODE_LLM_BACKEND=ollama explicitly set.
    """
    if os.environ.get("JCODE_LLM_BACKEND", "llamacpp").strip().lower().startswith("llama"):
        return os.environ.get("LLAMACPP_MODEL", "gemma-4-e2b")
    # Legacy back-compat: Ollama + gemma2:2b, only when JCODE_LLM_BACKEND=ollama
    return os.environ.get("OLLAMA_MODEL", "gemma2:2b")
# #EXT-014-REQ-1 End


MODEL = _active_model_label()
# Unit tests finish in well under a second; a generated infinite loop must NOT burn the
# shell.exec 120s default (12 attempts x 120s = ~24 min wasted on one bad problem). Cap
# test runs short so the eval/repair loops stay fast and never hang on a bad generation.
TEST_TIMEOUT_S = int(os.environ.get("JCODE_TEST_TIMEOUT_S", "15"))

# Strategy-diverse CASCADE for the implement regime (EXT-003/REQ-5). Proven out-of-sample
# on HumanEval[40:60]: baseline 13/20 -> cascade 17/20 (+4, ZERO regressions). Each attempt
# is a DIFFERENT strategy generated from the CLEAN stub; the deterministic test selects the
# first that passes -> the UNION of what the strategies solve, strictly non-regressing.
_FEWSHOT = (
    "Study these two examples of implementing a Python function from its spec, then do "
    "the same for the real task.\n\n"
    "EXAMPLE 1\nSPEC: Return the number of vowels in string s (case-insensitive).\n"
    "CODE:\ndef count_vowels(s):\n    return sum(1 for c in s.lower() if c in \"aeiou\")\n\n"
    "EXAMPLE 2\nSPEC: Return the running maximum of a list nums; empty list returns [].\n"
    "CODE:\ndef running_max(nums):\n    out, m = [], None\n    for n in nums:\n"
    "        m = n if m is None else max(m, n)\n        out.append(m)\n    return out\n\n"
    "Work carefully and handle edge cases. Now the REAL task:\n"
)
# (mode, instruction_prefix, temperature) per attempt — ALL body-only. The whole-file
# rewriter wastes its token budget re-copying the docstring and TRUNCATES before the closing
# sentinel on long problems, so its attempts contributed nothing to the union AND ran ~2x
# slower. Confirmed apples-to-apples on HumanEval[::4]: all-body == mixed (31/41 = 76%, same
# problems) at ~39s vs ~78s per problem. So every attempt uses the fast, complete body mode,
# diversified by temperature + few-shot. (EXT-003/REQ-5.)
_CASCADE_STRATEGIES = [
    ("body", "", 0.0), ("body", "", 0.4), ("body", _FEWSHOT, 0.2),
    ("body", _FEWSHOT, 0.6), ("body", "", 0.9), ("body", "", 1.1),
]


# Tool-usage telemetry (EXT-007 / REQ-4): count how often each tool/decision type
# fires, so we can SEE which agent<->tool wirings are actually used and prune dead
# ones. Module-level so it aggregates across the many fix_loops in one eval run.
_TOOL_USAGE: Counter = Counter()
# Wiring EDGES that actually fired: "<source-agent> -> <tool/decision-type>". This is
# how we prove wirings are USED by agents and detect orphans (EXT-007 / REQ-4).
_WIRING_USAGE: Counter = Counter()


def tool_usage() -> dict:
    """Snapshot of decision-type -> invocation count since the last reset."""
    return dict(_TOOL_USAGE)


def wiring_usage() -> dict:
    """Snapshot of '<agent> -> <tool>' edge -> count: the wirings actually used."""
    return dict(_WIRING_USAGE)


def reset_tool_usage() -> None:
    _TOOL_USAGE.clear()
    _WIRING_USAGE.clear()


# #EXT-003-REQ-1 Start
class Runtime:
    """Faithful Jaros execution path: gate -> executor -> decision log."""

    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        state_dir = data_dir / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        executor.register_handler("advance", make_advance_handler())
        load_custom_tools(TOOLS_DIR)  # registers fs.*, code.apply_patch, shell.exec
        self._log = TransitionLog(state_dir)
        self._log.ensure()
        self._dlog = DecisionLog(state_dir)
        self._dlog.ensure()

    def apply(self, decision):
        """Validate at the gate, then execute, recording the accepted Decision."""
        gated = validate_decision(decision)
        if not gated.ok:
            raise RuntimeError(f"gate rejected {decision.type}: {gated.reason}")
        outcome = executor.apply(
            decision,
            on_accept=lambda d: record_decision(self._dlog, d),
            log=self._log,
        )
        if not outcome.applied:
            raise RuntimeError(f"executor refused {decision.type}: {outcome.reason}")
        _TOOL_USAGE[decision.type] += 1  # telemetry: this tool fired
        _WIRING_USAGE[f"{decision.source} -> {decision.type}"] += 1  # which agent used it
        return outcome.output
# #EXT-003-REQ-1 End


# Specialist dispatch by target type (EXT-007 / REQ-6): config files go to the
# config-editor specialist; code/other go to the default rewriter. An explicit
# editor_agent override is always respected.
_CONFIG_EXTS = {".json", ".yaml", ".yml", ".ini", ".toml", ".cfg"}


def select_editor_agent(target: str, editor_agent: str = "rewriter_agent.py") -> str:
    if editor_agent != "rewriter_agent.py":
        return editor_agent  # explicit override always respected
    p = Path(target)
    name, ext = p.name.lower(), p.suffix.lower()
    if name.startswith("dockerfile") or ext == ".dockerfile":
        return "dockerfile_editor_agent.py"
    if ext in {".md", ".markdown"}:
        return "markdown_editor_agent.py"
    if ext in _CONFIG_EXTS:
        return "config_editor_agent.py"
    return editor_agent


def _load_agent(filename: str, llm):
    path = AGENTS_DIR / filename
    spec = importlib.util.spec_from_file_location(f"agent_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build(llm)


def distill_failure(output: str) -> str:
    """Pull the salient failure lines (assertion/error/traceback) out of noisy test
    output, so the agent gets a SHARP signal on retry instead of the whole dump."""
    if not output:
        return ""
    keep = [ln for ln in output.splitlines()
            if any(k in ln for k in ("Error", "assert", "FAILED", "Traceback", "E   ", "line "))]
    distilled = "\n".join(keep[-12:]) if keep else ""
    return distilled or output[-600:]


def _count_test_failures(output: str) -> int:
    """How many tests pytest reported failed/errored — the progress signal for keep_partial
    multi-file fixing. A syntax/uncountable failure ranks worst (999) so a real partial wins."""
    nums = [int(m) for m in re.findall(r"(\d+)\s+(?:failed|error)", output or "")]
    return sum(nums) if nums else 999


def python_syntax_error(src: str) -> str | None:
    """Return a short description if ``src`` is not valid Python, else None.

    Deterministic (no model): the loop uses this to catch a broken edit immediately
    and feed the precise error back, instead of wasting a test run on code that can
    never import."""
    try:
        compile(src, "<edited>", "exec")
        return None
    except SyntaxError as exc:
        return f"line {exc.lineno}: {exc.msg}"


def build_llm():
    """Return the deterministic local reasoning client (EXT-006): greedy + seeded so the
    model is repeatable. Backend selected by JCODE_LLM_BACKEND:
      'llamacpp' (default) -> DeterministicLlamaCppClient (Gemma 4 2B (`e2b`) on Jetson, /v1/chat)
      'ollama'   (legacy)  -> DeterministicOllamaClient   (local Ollama, /api/generate, back-compat)
    Either way it is a LOCAL model only (Tenet 2)."""
    backend = os.environ.get("JCODE_LLM_BACKEND", "llamacpp").strip().lower()
    if backend in ("llamacpp", "llama.cpp", "llama_cpp", "llama-cpp"):
        from harness.llamacpp_client import DeterministicLlamaCppClient
        return DeterministicLlamaCppClient()
    os.environ.setdefault("JAROS_LLM_PROVIDER", "ollama")
    os.environ.setdefault("OLLAMA_MODEL", MODEL)
    try:
        from harness.ollama_client import DeterministicOllamaClient
        return DeterministicOllamaClient(model=MODEL)
    except Exception:
        return create_llm_client(LlmConfig(provider="ollama"))


@dataclass
class LoopResult:
    success: bool
    attempts: int
    final_output: str


# --- Claude-Code-like transcript ------------------------------------------

def _banner(target: str, test_cmd: str, max_iters: int) -> None:
    print("\n\033[1m jaros-code \033[0m  software-dev harness on Jaros")
    # #EXT-014-REQ-1 Start
    # Backend label is dynamic: llamacpp (default, Gemma 4 2B e2b) or ollama (legacy, explicit only).
    _be = os.environ.get("JCODE_LLM_BACKEND", "llamacpp").strip().lower()
    _be_label = "llamacpp, zero paid inference" if _be.startswith("llama") else "ollama, zero paid inference (legacy)"
    print(f"   model    : {MODEL}  ({_be_label})")
    # #EXT-014-REQ-1 End
    print(f"   target   : {target}")
    print(f"   test     : {test_cmd}")
    print(f"   max tries: {max_iters}")
    print("   " + "-" * 56)


def _round_header(r: int, total: int) -> None:
    print(f"\n  \033[36m[*] round {r}/{total}\033[0m")


def _step(label: str, detail: str) -> None:
    print(f"    \033[2m{label:<14}\033[0m {detail}")


# #EXT-003-REQ-4 Start
# Off-by-one / boundary operator mutations. The hardest bug class for a 2B model is
# the one that turns on a single operator it cannot reason about (`<` vs `<=`). We
# learned the honest lesson empirically: every *model-side* decomposition (locate the
# line, fix the line, quote the snippet) bottoms out on that same judgement Gemma 4 2B (e2b)
# cannot make. So we move the fix into the DETERMINISTIC plane — try each candidate
# single-operator edit, keep the first that turns the test suite green. No model call,
# so it is 100% reproducible (Tenet 3). This is classic automated program repair,
# scoped to the boundary-bug class the rewriter reliably misses.
_BOUNDARY_MUTATIONS = [
    (re.compile(r"(?<![<>=!])<(?![=])"), "<="),   # <  -> <=
    (re.compile(r"(?<![<>=!])>(?![=])"), ">="),   # >  -> >=
    (re.compile(r"<="), "<"),                       # <= -> <
    (re.compile(r">="), ">"),                       # >= -> >
    (re.compile(r"(?<![<>=!])<(?![=])"), ">"),    # <  -> >
    (re.compile(r"(?<![<>=!])>(?![=])"), "<"),    # >  -> <
    (re.compile(r"\+\s*1\b"), "- 1"),              # + 1 -> - 1
    (re.compile(r"-\s*1\b"), "+ 1"),               # - 1 -> + 1
]


def boundary_repair_candidates(source: str) -> list[str]:
    """Pure, deterministic: every single-operator boundary mutation of ``source``,
    one occurrence changed per candidate (so a multi-occurrence operator yields one
    variant per site). Ordered and de-duplicated for reproducibility."""
    seen: set[str] = set()
    out: list[str] = []
    for pat, repl in _BOUNDARY_MUTATIONS:
        for m in pat.finditer(source):
            cand = source[:m.start()] + repl + source[m.end():]
            if cand != source and cand not in seen:
                seen.add(cand)
                out.append(cand)
    return out


def mutation_repair_loop(target: str, test_cmd: str, *, cwd: str | None = None,
                         verbose: bool = False) -> LoopResult:
    """Deterministic boundary-bug repair (the ant, not the boulder): mechanically try
    each single-operator mutation via the write_file TOOL, run the suite via the
    shell.exec TOOL, and keep the first candidate that passes. No reasoning call — the
    judgement the 2B can't make is replaced by exhaustive deterministic search over a
    tiny, safe edit space."""
    rt = Runtime()
    target_path = Path(target)
    original = target_path.read_text(encoding="utf-8")
    candidates = boundary_repair_candidates(original)

    def _run_tests() -> int | None:
        res = rt.apply(create_decision(id=f"t-{uuid.uuid4().hex}", source="orchestrator",
                       type="shell.exec", payload={"command": test_cmd, "timeout_s": TEST_TIMEOUT_S, **({"cwd": cwd} if cwd else {})}))
        return res.get("exitCode") if isinstance(res, dict) else None

    for i, cand in enumerate(candidates, 1):
        rt.apply(create_decision(id=f"mut-{uuid.uuid4().hex}", source="mutation-repair",
                 type="code.write_file", payload={"path": str(target), "content": cand}))
        code = _run_tests()
        if verbose:
            _step("mutate", f"candidate {i}/{len(candidates)} -> exit {code}")
        if code == 0:
            return LoopResult(success=True, attempts=i, final_output="boundary mutation passed")
    # No candidate worked: restore the original bug so we never leave a worse file.
    target_path.write_text(original, encoding="utf-8", newline="\n")
    return LoopResult(success=False, attempts=len(candidates), final_output="no boundary mutation passed")
# #EXT-003-REQ-4 End


# #EXT-003-REQ-2 Start
def fix_loop(target: str, instruction: str, test_cmd: str, *,
             max_iters: int = 4, cwd: str | None = None,
             editor_agent: str = "rewriter_agent.py", verbose: bool = True,
             keep_partial: bool = False) -> LoopResult:
    """Run the bounded edit->test->judge loop until tests pass or attempts run out.

    ``editor_agent`` selects the editing agent: ``rewriter_agent.py`` (whole-file,
    2B-reliable; default) or ``editor_agent.py`` (surgical OLD/NEW edit).
    ``verbose`` prints the Claude-Code-like transcript (off for batch evals).
    """
    rt = Runtime()
    llm = build_llm()
    target_path = Path(target)
    # Dispatcher (EXT-007/REQ-6): route to the specialist agent by target type.
    editor = _load_agent(select_editor_agent(target, editor_agent), llm)
    # Pick the deterministic syntax checker for this file type (py.check / json.check).
    check_type = {".py": "py.check", ".json": "json.check"}.get(target_path.suffix.lower())
    test_reader = _load_agent("test_reader_agent.py", llm)
    # Capture the ORIGINAL content so the decomposed bug-fix fallback can run on the
    # real bug (not the rewriter's mangled attempt) if the whole-file approach fails.
    original_content = target_path.read_text(encoding="utf-8") if target_path.is_file() else ""

    # Implement regime = a stub to fill in (HumanEval/MBPP/from-intent), as opposed to
    # repairing existing code. Implement uses the proven strategy-cascade; repair keeps
    # feedback-iteration. The cascade needs its full strategy set, so widen the budget.
    implement = ("NotImplementedError" in original_content
                 or bool(re.search(r"^\s*pass\s*$", original_content, re.M)))
    # GENERIC stub (e.g. MBPP's `def f(*args, **kwargs)`) carries NO real parameter names, so
    # body-only splices a body onto the wrong signature and fails — the whole-file rewriter must
    # regenerate the correct signature from the spec. Body-only's win is specific to RICH-signature
    # stubs (HumanEval). So route generic stubs to "whole". (Fixes the MBPP regression from the
    # all-body cascade: MBPP 73%->43% restored without losing the HumanEval speed win.)
    generic_stub = bool(re.search(r"def\s+\w+\s*\([^)]*\*args", original_content))
    body_completer = None
    if implement:
        max_iters = max(max_iters, len(_CASCADE_STRATEGIES))
        body_completer = _load_agent("body_completer_agent.py", llm)  # fast body-only cascade mode

    def _v(fn, *a):
        if verbose:
            fn(*a)

    _v(_banner, target, test_cmd, max_iters)
    last_output = ""
    # keep_partial (opt-in, used by the multi-file fixer): remember the attempt with the FEWEST
    # test failures so that on overall failure we leave it in place (a partial cross-file fix to
    # build on) instead of restoring the original. Off by default -> single-file behavior is
    # byte-identical (this stays None and the block below is skipped).
    best_partial: tuple[int, str] | None = None

    for r in range(1, max_iters + 1):
        _v(_round_header, r, max_iters)

        # 1) reasoning: editor proposes one exact edit (Gemma 4 2B (e2b)). On retries it
        # gets the previous failure output as feedback, so it can correct itself
        # (greedy decoding alone would just repeat the same mistake).
        # Wire the fs.read TOOL: the agent's content comes through a recorded tool
        # decision (decision log stays complete; fs.read is a used wiring, not orphan).
        content = ""
        if target_path.is_file():
            try:
                rres = rt.apply(create_decision(
                    id=f"read-{uuid.uuid4().hex}", source="orchestrator",
                    type="fs.read", payload={"path": str(target)}))
                if isinstance(rres, dict):
                    content = rres.get("content", "") or ""
            except RuntimeError:
                content = target_path.read_text(encoding="utf-8")
        # Wire the py.symbols TOOL into the agent's context: run the deterministic
        # tool through the runtime and feed its structure summary to the rewriter.
        symbols = ""
        if str(target).endswith(".py") and target_path.is_file():
            try:
                sres = rt.apply(create_decision(
                    id=f"sym-{uuid.uuid4().hex}", source="orchestrator",
                    type="py.symbols", payload={"path": str(target)}))
                if isinstance(sres, dict) and sres.get("symbols"):
                    symbols = ", ".join(f"{s['name']}({s['kind']})" for s in sres["symbols"])
            except RuntimeError:
                pass
        # Implement: each attempt is a DIFFERENT strategy from the CLEAN stub (the proven
        # cascade); the test selects the first pass. Repair: greedy attempt 1, then escalate
        # temperature and feed the failure back so a wrong answer can be corrected.
        if implement:
            mode, prefix, temperature = _CASCADE_STRATEGIES[(r - 1) % len(_CASCADE_STRATEGIES)]
            # All-body for rich-signature stubs; generic (*args) stubs need the whole-file
            # rewriter to produce the correct signature (see generic_stub above).
            if generic_stub:
                mode = "whole"
            agent = body_completer if mode == "body" else editor
            # Experiment toggle: feed the previous attempt's failure into later attempts so the
            # cascade can CORRECT (not just re-roll). Off by default (independent attempts proven).
            fb = (distill_failure(last_output)
                  if (r > 1 and os.environ.get("JCODE_IMPLEMENT_FEEDBACK")) else "")
            [edit] = agent.decide({"path": str(target), "content": original_content,
                                   "instruction": prefix + instruction, "symbols": symbols,
                                   "feedback": fb, "temperature": temperature, "seed": r})
        else:
            temperature = 0.0 if r == 1 else min(0.8, 0.3 * (r - 1))
            gen_feedback = distill_failure(last_output) if r > 1 else ""
            [edit] = editor.decide({"path": str(target), "content": content,
                                    "instruction": instruction, "symbols": symbols,
                                    "feedback": gen_feedback,
                                    "temperature": temperature, "seed": r})
        if edit.type == "code.apply_patch":
            _v(_step, "editor", f"edit {edit.payload['old']!r} -> {edit.payload['new']!r}")
        elif edit.type == "code.write_file":
            _v(_step, "rewriter", f"rewrite {edit.payload['path']} ({len(edit.payload['content'])} chars)")
        else:
            _v(_step, "editor", f"no edit ({edit.payload.get('note','')})")
        try:
            out = rt.apply(edit)
            if isinstance(out, dict) and out.get("applied"):
                _v(_step, out.get("tool", "tool"), f"applied to {out['path']} ({out['bytesAfter']} bytes)")
        except RuntimeError as exc:
            # A gate/safety rejection (e.g. unsafe generated code) is fed back so the
            # agent can correct, rather than silently retried.
            last_output = f"Your edit was rejected by the validation/safety gate: {exc}"
            _v(_step, "apply", f"\033[31mrejected\033[0m: {exc}")
            continue

        # 1b) deterministic syntax guard via the dispatched checker (py.check for .py,
        # json.check for .json): broken syntax can never pass, so catch it now and feed
        # the exact error back next round. Keeps those tools used, non-orphan verbs.
        if check_type and target_path.is_file():
            try:
                cres = rt.apply(create_decision(
                    id=f"chk-{uuid.uuid4().hex}", source="orchestrator",
                    type=check_type, payload={"path": str(target)}))
            except RuntimeError:
                cres = None
            if isinstance(cres, dict) and cres.get("valid") is False:
                serr = cres.get("error") if check_type == "json.check" else f"line {cres.get('line')}: {cres.get('error')}"
                last_output = f"{'JSON error' if check_type=='json.check' else 'SyntaxError'}: {serr}"
                _v(_step, check_type, f"\033[31msyntax error\033[0m {serr}")
                continue

        # 2) operator: run the test command via shell.exec (deterministic tool)
        test_dec = create_decision(
            id=f"test-{uuid.uuid4().hex}", source="orchestrator",
            type="shell.exec", payload={"command": test_cmd, "timeout_s": TEST_TIMEOUT_S, **({"cwd": cwd} if cwd else {})})
        result = rt.apply(test_dec)
        last_output = (result.get("stdout", "") + result.get("stderr", "")) if isinstance(result, dict) else str(result)
        exit_code = result.get("exitCode") if isinstance(result, dict) else None
        _v(_step, "shell.exec", f"exit={exit_code}  {last_output.strip().splitlines()[-1] if last_output.strip() else ''}")

        # 3) reasoning: test-reader judges PASS/FAIL (Gemma 4 2B (e2b)) — recorded as the
        # advance verdict. Ground-truth success, however, is the deterministic exit
        # code (Tenet 3): a hallucinated PASS must never count as solved.
        [verdict] = test_reader.decide({"output": last_output})
        rt.apply(verdict)
        passed = verdict.payload.get("verdict") == "pass"
        _v(_step, "test-reader", ("\033[32mPASS\033[0m" if passed else "\033[31mFAIL\033[0m") + f"  ({verdict.payload.get('note','')})")

        if exit_code == 0:
            _v(print, f"\n  \033[32m[OK] solved in {r} attempt(s)\033[0m\n")
            return LoopResult(success=True, attempts=r, final_output=last_output)

        if keep_partial and target_path.is_file():   # remember the least-failing attempt
            fails = _count_test_failures(last_output)
            if best_partial is None or fails < best_partial[0]:
                best_partial = (fails, target_path.read_text(encoding="utf-8"))

    # Fallback (ant, not boulder): if the whole-file rewrite couldn't crack a .py BUG FIX
    # (existing buggy code, not a from-scratch stub), hand the real bug to the
    # DETERMINISTIC boundary-mutation repair — it tries each single-operator edit and
    # keeps the first that turns the suite green. Runs on a FRESH copy of the original
    # bug, so it never regresses what the rewriter already solves (only runs on failure).
    # Single-file fallback only. Skipped when keep_partial is set: a multi-file fixer wants the
    # partial edit kept, and single-operator mutations can't fix a fault that spans files.
    if (not keep_partial and str(target).endswith(".py") and original_content
            and "NotImplementedError" not in original_content):
        _v(print, "\n  whole-file rewrite failed — trying deterministic boundary-mutation repair...")
        target_path.write_text(original_content, encoding="utf-8", newline="\n")  # restore the real bug
        lr = mutation_repair_loop(target, test_cmd, cwd=cwd, verbose=verbose)
        if lr.success:
            _v(print, f"\n  \033[32m[OK] boundary-mutation repair solved it\033[0m\n")
            return lr

    if keep_partial and best_partial is not None:   # leave the least-failing attempt to build on
        target_path.write_text(best_partial[1], encoding="utf-8", newline="\n")

    _v(print, f"\n  \033[31m[X] not solved in {max_iters} attempts\033[0m\n")
    return LoopResult(success=False, attempts=max_iters, final_output=last_output)
# #EXT-003-REQ-2 End
# #EXT-003-REQ-3 End
