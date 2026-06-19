"""Bounded edit->test->judge coding loop (EXT-003).

Composes the EXT-002 single-purpose agents and EXT-001 deterministic tools into a
multi-step coding loop, routing every Decision through the real Jaros gate +
executor + decision log so each step is validated, executed, and recorded (replay
faithful). The transcript mirrors Claude Code's look and feel.

Only `editor` and `test-reader` call gemma2:2b (the reasoning steps). Everything
else is deterministic: the model decides *what*, the executor and tools decide *how*.
"""

from __future__ import annotations

import importlib.util
import os
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
MODEL = os.environ.get("OLLAMA_MODEL", "gemma2:2b")


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


def _load_agent(filename: str, llm):
    path = AGENTS_DIR / filename
    spec = importlib.util.spec_from_file_location(f"agent_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build(llm)


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
    """Return the deterministic local Ollama client (EXT-006): greedy + seeded so
    gemma2:2b is repeatable. Falls back to the stock adapter only if unavailable."""
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
    print(f"   model    : {MODEL}  (ollama, zero paid inference)")
    print(f"   target   : {target}")
    print(f"   test     : {test_cmd}")
    print(f"   max tries: {max_iters}")
    print("   " + "-" * 56)


def _round_header(r: int, total: int) -> None:
    print(f"\n  \033[36m[*] round {r}/{total}\033[0m")


def _step(label: str, detail: str) -> None:
    print(f"    \033[2m{label:<14}\033[0m {detail}")


# #EXT-003-REQ-2 Start
def fix_loop(target: str, instruction: str, test_cmd: str, *,
             max_iters: int = 4, cwd: str | None = None,
             editor_agent: str = "rewriter_agent.py", verbose: bool = True) -> LoopResult:
    """Run the bounded edit->test->judge loop until tests pass or attempts run out.

    ``editor_agent`` selects the editing agent: ``rewriter_agent.py`` (whole-file,
    2B-reliable; default) or ``editor_agent.py`` (surgical OLD/NEW edit).
    ``verbose`` prints the Claude-Code-like transcript (off for batch evals).
    """
    rt = Runtime()
    llm = build_llm()
    editor = _load_agent(editor_agent, llm)
    test_reader = _load_agent("test_reader_agent.py", llm)
    target_path = Path(target)

    def _v(fn, *a):
        if verbose:
            fn(*a)

    _v(_banner, target, test_cmd, max_iters)
    last_output = ""

    for r in range(1, max_iters + 1):
        _v(_round_header, r, max_iters)

        # 1) reasoning: editor proposes one exact edit (gemma2:2b). On retries it
        # gets the previous failure output as feedback, so it can correct itself
        # (greedy decoding alone would just repeat the same mistake).
        content = target_path.read_text(encoding="utf-8") if target_path.is_file() else ""
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
        # Attempt 1 is greedy (temp 0, repeatable). Retries escalate temperature and
        # vary the seed so a deterministically-wrong answer can be escaped.
        temperature = 0.0 if r == 1 else min(0.8, 0.3 * (r - 1))
        [edit] = editor.decide({"path": str(target), "content": content,
                                "instruction": instruction, "symbols": symbols,
                                "feedback": last_output if r > 1 else "",
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

        # 1b) deterministic syntax guard: a broken .py can never import, so catch it
        # now and feed the exact SyntaxError back next round (don't waste a test run).
        if str(target).endswith(".py") and target_path.is_file():
            serr = python_syntax_error(target_path.read_text(encoding="utf-8"))
            if serr:
                last_output = f"SyntaxError: {serr}"
                _v(_step, "py.check", f"\033[31msyntax error\033[0m {serr}")
                continue

        # 2) operator: run the test command via shell.exec (deterministic tool)
        test_dec = create_decision(
            id=f"test-{uuid.uuid4().hex}", source="orchestrator",
            type="shell.exec", payload={"command": test_cmd, **({"cwd": cwd} if cwd else {})})
        result = rt.apply(test_dec)
        last_output = (result.get("stdout", "") + result.get("stderr", "")) if isinstance(result, dict) else str(result)
        exit_code = result.get("exitCode") if isinstance(result, dict) else None
        _v(_step, "shell.exec", f"exit={exit_code}  {last_output.strip().splitlines()[-1] if last_output.strip() else ''}")

        # 3) reasoning: test-reader judges PASS/FAIL (gemma2:2b) — recorded as the
        # advance verdict. Ground-truth success, however, is the deterministic exit
        # code (Tenet 3): a hallucinated PASS must never count as solved.
        [verdict] = test_reader.decide({"output": last_output})
        rt.apply(verdict)
        passed = verdict.payload.get("verdict") == "pass"
        _v(_step, "test-reader", ("\033[32mPASS\033[0m" if passed else "\033[31mFAIL\033[0m") + f"  ({verdict.payload.get('note','')})")

        if exit_code == 0:
            _v(print, f"\n  \033[32m[OK] solved in {r} attempt(s)\033[0m\n")
            return LoopResult(success=True, attempts=r, final_output=last_output)

    _v(print, f"\n  \033[31m[X] not solved in {max_iters} attempts\033[0m\n")
    return LoopResult(success=False, attempts=max_iters, final_output=last_output)
# #EXT-003-REQ-2 End
# #EXT-003-REQ-3 End
