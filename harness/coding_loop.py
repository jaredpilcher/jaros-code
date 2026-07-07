"""Bounded edit->test->judge coding loop (EXT-003).

Composes the EXT-002 single-purpose agents and EXT-001 deterministic tools into a
multi-step coding loop, routing every Decision through the real Jaros gate +
executor + decision log so each step is validated, executed, and recorded (replay
faithful). The transcript mirrors Claude Code's look and feel.

Only `editor` and `test-reader` call Gemma 4 2B (`e2b`) (the reasoning steps). Everything
else is deterministic: the model decides *what*, the executor and tools decide *how*.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, replace as _dataclass_replace
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
# #EXT-037-REQ-1 Start
# TASK-2: the writer tools' `validate()` gates a `root`-jail on an OPTIONAL `root` key in
# the Decision payload (EXT-037), but no caller supplied one -- the jail was dormant in
# production. `Runtime` is the ONE real Jaros-native choke point every write Decision
# passes through (gate -> executor -> log), so an opt-in `root` here is the single place
# that can stamp it onto every write Decision universally, with zero change to callers
# that don't pass `root` (default `None`, fully backward compatible).
_ROOT_JAILED_DECISION_TYPES = frozenset(
    {"code.write_file", "code.apply_patch", "code.search_replace"})
# #EXT-037-REQ-1 End
class Runtime:
    """Faithful Jaros execution path: gate -> executor -> decision log."""

    # #EXT-045-REQ-1 Start
    def __init__(self, data_dir: Path = DATA_DIR, root: "str | None" = None,
                 on_event: "callable | None" = None,
                 # #EXT-047-REQ-2 Start
                 hooks_config: "dict | None" = None,
                 # #EXT-047-REQ-2 End
                 # #EXT-048-REQ-4 Start
                 mode: str = "default",
                 permission_rules: "list | None" = None,
                 ask_callback: "callable | None" = None,
                 # #EXT-048-REQ-4 End
                 # #EXT-049-REQ-2 Start
                 checkpoint_ring: "object | None" = None,
                 # #EXT-049-REQ-2 End
                 # #EXT-050-REQ-3 Start
                 tool_allowlist: "list[str] | None" = None) -> None:
                 # #EXT-050-REQ-3 End
        # #EXT-045-REQ-1 End
        state_dir = data_dir / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        executor.register_handler("advance", make_advance_handler())
        load_custom_tools(TOOLS_DIR)  # registers fs.*, code.apply_patch, shell.exec
        self._log = TransitionLog(state_dir)
        self._log.ensure()
        self._dlog = DecisionLog(state_dir)
        self._dlog.ensure()
        # #EXT-037-REQ-1 Start
        self._root = root  # project root to stamp onto write Decisions (opt-in; see above)
        # #EXT-037-REQ-1 End
        # #EXT-045-REQ-1 Start
        # Optional streaming hook (EXT-045): called with a small event dict at the SAME seam
        # that already records each accepted Decision to the hash-chain (`record_decision`
        # below) -- pure presentation, no new decision-making path. `None` (the default) is a
        # complete no-op: every pre-EXT-045 caller of `Runtime(...)` behaves byte-identically.
        self._on_event = on_event
        # #EXT-045-REQ-1 End
        # #EXT-047-REQ-2 Start
        # User-configurable lifecycle hooks (EXT-047): `None`/`{}` (the default) is a complete
        # no-op -- every pre-EXT-047 caller of `Runtime(...)` behaves byte-identically. When
        # non-empty, PreToolUse/PostToolUse hooks fire around each Decision this Runtime applies
        # (see `apply` below) -- see `harness.hooks` for the gated firing mechanism.
        self._hooks_config = hooks_config
        # #EXT-047-REQ-2 End
        # #EXT-048-REQ-4 Start
        # REPL mode + permission rules (EXT-048): `mode="default"` and `permission_rules=None`
        # (both defaults) are a complete no-op -- every pre-EXT-048 caller of `Runtime(...)`
        # behaves byte-identically. `ask_callback` is only ever consulted when a permission rule
        # resolves `"ask"`; `None` (the default, and every headless/non-interactive caller) means
        # an `"ask"` degrades to a safe-default deny rather than blocking on input (see `apply`).
        self._mode = mode if mode in ("plan", "default", "acceptEdits") else "default"
        self._permission_rules = permission_rules
        self._ask_callback = ask_callback
        # #EXT-048-REQ-4 End
        # #EXT-049-REQ-2 Start
        # Fine-grained checkpoint ring (EXT-049): `None` (the default) is a complete no-op --
        # every pre-EXT-049 caller of `Runtime(...)` behaves byte-identically. When supplied (a
        # `harness.checkpoint_ring.CheckpointRing`), `apply()` below captures the pre-edit content
        # of the file a write/edit Decision is about to change, at the SAME seam that already logs
        # every accepted Decision to the hash-chain -- no parallel history store.
        self._checkpoint_ring = checkpoint_ring
        # #EXT-049-REQ-2 End
        # #EXT-050-REQ-3 Start
        # Subagent tool-allowlist (EXT-050): `None` (the default) is a complete no-op -- every
        # pre-EXT-050 caller of `Runtime(...)` behaves byte-identically. When supplied (a
        # subagent's `tools:` frontmatter, via `harness.cli.JcodeCli._subagent_runtime`), `apply()`
        # below refuses any Decision whose `type` is NOT in this list -- consulted STRICTLY AFTER
        # the hard gate has already accepted the Decision, so this can only NARROW what the hard
        # gate already permits, never widen past it (the safety invariant this spec proves).
        try:
            self._tool_allowlist = list(tool_allowlist) if tool_allowlist else None
        except TypeError:
            self._tool_allowlist = None
        # #EXT-050-REQ-3 End

    # #EXT-048-REQ-4 Start
    def set_mode(self, mode: str) -> None:
        """Update this Runtime's live mode (EXT-048) -- called by `harness.cli.JcodeCli.cmd_mode`
        so a `/mode` change takes effect immediately without reconstructing the CLI. An unknown
        `mode` value degrades to `"default"` rather than raising."""
        self._mode = mode if mode in ("plan", "default", "acceptEdits") else "default"
    # #EXT-048-REQ-4 End

    # #EXT-045-REQ-1 Start
    def _emit(self, event: dict) -> None:
        """Best-effort event notification -- NEVER raises and NEVER affects `apply()`'s own
        control flow, even if `on_event` itself is broken."""
        if self._on_event is None:
            return
        try:
            self._on_event(event)
        except Exception:
            pass
    # #EXT-045-REQ-1 End

    def apply(self, decision):
        """Validate at the gate, then execute, recording the accepted Decision."""
        # #EXT-037-REQ-1 Start
        if (self._root and decision.type in _ROOT_JAILED_DECISION_TYPES
                and isinstance(decision.payload, dict) and "root" not in decision.payload):
            decision = _dataclass_replace(decision, payload={**decision.payload, "root": self._root})
        # #EXT-037-REQ-1 End
        # #EXT-048-REQ-4 Start
        # `plan` mode (EXT-048): a user-toggled REPL mode (`/mode plan`) makes every write/shell
        # Decision propose-only -- described and returned WITHOUT any side effect: no PreToolUse
        # hook fires, the hard gate never runs, the executor never runs. This is STRONGER than a
        # permission rule (a true "propose only," not merely "ask and default to no"). Read-only
        # types (fs.read/fs.grep/...) are unaffected, so information-gathering still works.
        # `self._mode` defaults to "default" -- byte-identical to before this spec unless a caller
        # explicitly opts into plan mode.
        if self._mode == "plan":
            from harness.permissions import PLAN_MODE_WITHHELD_TYPES
            if decision.type in PLAN_MODE_WITHHELD_TYPES:
                self._emit({"phase": "planned", "type": decision.type,
                            "payload": decision.payload})
                return {"planned": True, "type": decision.type, "payload": decision.payload,
                        "note": "plan mode: no side effect performed -- description only"}
        # #EXT-048-REQ-4 End
        # #EXT-047-REQ-2 Start
        # PreToolUse hooks (EXT-047): fire BEFORE the gate even sees this Decision. A hook that
        # exits non-zero BLOCKS the tool call -- the clerk refuses it, exactly like a gate
        # rejection, deterministically and honestly (no partial effect ever happens). A no-op
        # when `self._hooks_config` is empty/None (the default) -- byte-identical to before.
        if self._hooks_config:
            from harness import hooks as _hooks
            try:
                pre_outcomes = _hooks.fire_event(
                    "PreToolUse", self._hooks_config, tool_name=decision.type, cwd=self._root)
            except Exception:
                pre_outcomes = []
            _block_reason = _hooks.blocking_reason(pre_outcomes) if pre_outcomes else None
            if _block_reason:
                self._emit({"phase": "error", "type": decision.type, "reason": _block_reason})
                raise RuntimeError(f"PreToolUse hook blocked {decision.type}: {_block_reason}")
        # #EXT-047-REQ-2 End
        # #EXT-045-REQ-1 Start
        self._emit({"phase": "call", "type": decision.type, "payload": decision.payload,
                    "source": decision.source})
        # #EXT-045-REQ-1 End
        gated = validate_decision(decision)
        if not gated.ok:
            # #EXT-045-REQ-1 Start
            self._emit({"phase": "error", "type": decision.type, "reason": gated.reason})
            # #EXT-045-REQ-1 End
            raise RuntimeError(f"gate rejected {decision.type}: {gated.reason}")
        # #EXT-050-REQ-3 Start
        # Subagent tool-allowlist (EXT-050): consulted ONLY here, AFTER the hard gate above has
        # already accepted the Decision -- THE SAFETY INVARIANT (see harness/subagents.py module
        # docstring): this check is unreachable when `gated.ok` is False (the `raise` above already
        # returned control to the caller), so a subagent's `tools:` allowlist can NEVER un-block
        # something the hard gate just refused -- it can only additionally NARROW what the hard
        # gate already permits. `self._tool_allowlist` defaults to `None` -- byte-identical to
        # before this spec for every caller that doesn't pass it.
        if self._tool_allowlist is not None and decision.type not in self._tool_allowlist:
            _reason = (f"subagent tool-allowlist denied {decision.type} "
                       "(not in this subagent's allowed tool set)")
            self._emit({"phase": "error", "type": decision.type, "reason": _reason})
            raise RuntimeError(_reason)
        # #EXT-050-REQ-3 End
        # #EXT-048-REQ-2 Start
        # User permission rules (EXT-048): consulted ONLY here, AFTER the hard gate above has
        # already accepted the Decision -- THE SAFETY INVARIANT (see harness/permissions.py
        # module docstring): a user `allow` rule can never un-block something the hard gate just
        # refused, because this code is unreachable when `gated.ok` is False (the `raise` above
        # already returned control to the caller). `self._permission_rules` defaults to `None` --
        # byte-identical to before this spec for every caller that doesn't pass it.
        if self._permission_rules:
            from harness.permissions import ACCEPT_EDITS_AUTO_TYPES, decide, resolve_decision_arg
            _arg = resolve_decision_arg(decision)
            _action = decide(self._permission_rules, decision.type, _arg)
            if _action == "deny":
                _reason = (f"permission rule denied {decision.type}"
                           + (f" ({_arg})" if _arg else ""))
                self._emit({"phase": "error", "type": decision.type, "reason": _reason})
                raise RuntimeError(_reason)
            if _action == "ask":
                if self._mode == "acceptEdits" and decision.type in ACCEPT_EDITS_AUTO_TYPES:
                    pass  # acceptEdits auto-approves a write Decision that already passed the gate
                elif self._ask_callback is not None:
                    try:
                        _approved = bool(self._ask_callback(decision.type, _arg))
                    except Exception:
                        _approved = False
                    if not _approved:
                        _reason = (f"permission ask declined for {decision.type}"
                                   + (f" ({_arg})" if _arg else ""))
                        self._emit({"phase": "error", "type": decision.type, "reason": _reason})
                        raise RuntimeError(_reason)
                else:
                    # Headless/no interactive prompt wired -- never hang: safe-default deny.
                    _reason = (f"permission ask for {decision.type} has no interactive prompt "
                               "available -- denying by safe default")
                    self._emit({"phase": "error", "type": decision.type, "reason": _reason})
                    raise RuntimeError(_reason)
            # _action == "allow" (or any unrecognized value) falls through to execute normally.
        # #EXT-048-REQ-2 End
        # #EXT-049-REQ-2 Start
        # Fine-grained checkpoint ring (EXT-049): capture the PRE-EDIT content of the file this
        # write/edit Decision is about to change, at this seam -- a plain READ (not a gated side
        # effect; Tenet 1's Decision-routing rule is about host WRITES, and the restore write is
        # routed through a real `code.write_file` Decision elsewhere -- see `harness.cli`). A
        # complete no-op when `self._checkpoint_ring` is `None` (the default).
        _ckpt_path = None
        _ckpt_existed = False
        _ckpt_before = None
        if (self._checkpoint_ring is not None and decision.type in _ROOT_JAILED_DECISION_TYPES
                and isinstance(decision.payload, dict)):
            _p = decision.payload.get("path")
            if isinstance(_p, str) and _p:
                _ckpt_path = _p
                try:
                    _ckpt_existed = os.path.isfile(_p)
                    _ckpt_before = Path(_p).read_text(encoding="utf-8") if _ckpt_existed else None
                except Exception:
                    _ckpt_existed, _ckpt_before = False, None
        # #EXT-049-REQ-2 End
        outcome = executor.apply(
            decision,
            on_accept=lambda d: record_decision(self._dlog, d),
            log=self._log,
        )
        if not outcome.applied:
            # #EXT-045-REQ-1 Start
            self._emit({"phase": "error", "type": decision.type, "reason": outcome.reason})
            # #EXT-045-REQ-1 End
            raise RuntimeError(f"executor refused {decision.type}: {outcome.reason}")
        _TOOL_USAGE[decision.type] += 1  # telemetry: this tool fired
        _WIRING_USAGE[f"{decision.source} -> {decision.type}"] += 1  # which agent used it
        # #EXT-049-REQ-2 Start
        # Only an ACCEPTED Decision (we're past the `outcome.applied` check above) is checkpointed
        # -- a gate/executor rejection never produces a checkpoint entry.
        if _ckpt_path is not None:
            self._checkpoint_ring.record(
                decision_type=decision.type, path=_ckpt_path, existed=_ckpt_existed,
                before_content=_ckpt_before, source=decision.source)
        # #EXT-049-REQ-2 End
        # #EXT-045-REQ-1 Start
        self._emit({"phase": "result", "type": decision.type, "output": outcome.output})
        # #EXT-045-REQ-1 End
        # #EXT-047-REQ-2 Start
        # PostToolUse hooks (EXT-047): fire AFTER a successful execute() -- observational only
        # (the tool call already happened; nothing left to refuse), so a failing PostToolUse
        # hook is recorded but never raised. No-op when `self._hooks_config` is empty/None.
        if self._hooks_config:
            from harness import hooks as _hooks
            try:
                _hooks.fire_event(
                    "PostToolUse", self._hooks_config, tool_name=decision.type, cwd=self._root)
            except Exception:
                pass
        # #EXT-047-REQ-2 End
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


def build_llm(model: "str | None" = None):
    """Return the deterministic local reasoning client (EXT-006): greedy + seeded so the
    model is repeatable. Backend selected by JCODE_LLM_BACKEND:
      'llamacpp' (default) -> DeterministicLlamaCppClient (Gemma 4 2B (`e2b`) on Jetson, /v1/chat)
      'ollama'   (legacy)  -> DeterministicOllamaClient   (local Ollama, /api/generate, back-compat)
    Either way it is a LOCAL model only (Tenet 2).

    # #EXT-050-REQ-3 Start
    ``model`` (EXT-050): an optional override of the model LABEL sent in the request payload --
    defaults to `None` (every pre-EXT-050 caller keeps today's exact selection). This is a
    RELABEL of the request to the SAME local endpoint, never a different backend/provider (Tenet
    2 preserved) -- used by a user-authored subagent's optional `model:` frontmatter
    (`harness.cli.JcodeCli._run_subagent`); genuinely rewiring to a different SERVED Jetson-fitting
    model is EXT-021's multi-model-registry job, out of scope here.
    # #EXT-050-REQ-3 End
    """
    backend = os.environ.get("JCODE_LLM_BACKEND", "llamacpp").strip().lower()
    if backend in ("llamacpp", "llama.cpp", "llama_cpp", "llama-cpp"):
        from harness.llamacpp_client import DeterministicLlamaCppClient
        return DeterministicLlamaCppClient(model=model)
    os.environ.setdefault("JAROS_LLM_PROVIDER", "ollama")
    os.environ.setdefault("OLLAMA_MODEL", MODEL)
    try:
        from harness.ollama_client import DeterministicOllamaClient
        return DeterministicOllamaClient(model=model or MODEL)
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


# #EXT-003-REQ-7 Start
# Deterministic double-application repair fallback. DIAGNOSED (EXT-005 fix_hard_invoice_
# double_tax, 2026-07-06, gemma-4-e2b): the whole-file rewriter (REQ-2) already correctly
# LOCATES this multi-function call-chain bug (a value is passed back through the SAME
# function a second time -- e.g. tax/discount/fee applied twice) -- it is NOT a single-
# function-regen limitation. But the model's "fix" often over-rewrites the untouched
# function's own arithmetic into an ALGEBRAICALLY EQUIVALENT form (`subtotal + subtotal *
# tax_rate` -> `subtotal * (1 + tax_rate)`) that differs by float rounding, so it fails an
# exact-equality oracle even though the double-application bug is gone (confirmed: raw-
# probed the model with the exact pytest failure fed back across 4 rounds -- it never
# reaches back for the byte-identical original arithmetic, it keeps regenerating the same
# rounding-unstable form). The minimal, ALWAYS-safe fix never touches the inner function's
# body at all: unwrap the redundant outer application. That is a mechanical, deterministic
# repair -- the ant, not the boulder -- so it moves into the execution plane exactly like
# REQ-4's boundary-mutation repair, for a DIFFERENT generic bug class (self-composition
# call chains), never touching the (already-correct) function body that introduces the
# instability.
def double_application_repair_candidates(source: str) -> list[str]:
    """Pure, deterministic (no model): every "unwrap one redundant self-application" rewrite
    of ``source``, one occurrence changed per candidate.

    Detects, per function, two shapes of "a function's result is immediately re-passed as
    the first argument to the SAME function again":
      (a) via an intermediate variable -- ``v = fn(...)`` followed later by a call
          ``fn(v, ...)`` -- candidate replaces that outer call with just ``v``
      (b) fully nested -- ``fn(fn(...), ...)`` -- candidate replaces the outer call with
          the exact source text of the inner call (dropping the outer wrapper)

    Never touches ``fn``'s own definition/body. Ordered and de-duplicated for
    reproducibility; returns ``[]`` (never raises) if ``source`` doesn't parse.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines(keepends=True)
    seen: set[str] = set()
    out: list[str] = []

    for func in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        # var name -> fn name it was directly assigned from (simple `v = fn(...)` only).
        var_fn: dict[str, str] = {}
        for node in ast.walk(func):
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)):
                var_fn[node.targets[0].id] = node.value.func.id

        for node in ast.walk(func):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.args):
                continue
            fn = node.func.id
            first = node.args[0]
            replacement = None
            if isinstance(first, ast.Name) and var_fn.get(first.id) == fn:
                replacement = first.id  # v = fn(...); ...; fn(v, ...) -> v
            elif (isinstance(first, ast.Call) and isinstance(first.func, ast.Name)
                    and first.func.id == fn):
                replacement = _span_text(lines, first)  # fn(fn(x, ...), ...) -> fn(x, ...)
            if replacement is None:
                continue
            candidate = _splice_span(lines, node, replacement)
            if candidate != source and candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
    return out


def _span_text(lines: list[str], node: ast.AST) -> str:
    """The exact source text of ``node`` (1-indexed lineno/col_offset, matching the `ast`
    module), pulled from ``lines`` (``source.splitlines(keepends=True)``)."""
    if node.lineno == node.end_lineno:
        return lines[node.lineno - 1][node.col_offset:node.end_col_offset]
    parts = [lines[node.lineno - 1][node.col_offset:]]
    parts.extend(lines[node.lineno:node.end_lineno - 1])
    parts.append(lines[node.end_lineno - 1][:node.end_col_offset])
    return "".join(parts)


def _splice_span(lines: list[str], node: ast.AST, replacement: str) -> str:
    """The full source with ``node``'s exact span replaced by ``replacement``."""
    before = "".join(lines[:node.lineno - 1]) + lines[node.lineno - 1][:node.col_offset]
    after = lines[node.end_lineno - 1][node.end_col_offset:] + "".join(lines[node.end_lineno:])
    return before + replacement + after


def double_application_repair_loop(target: str, test_cmd: str, *, cwd: str | None = None,
                                   verbose: bool = False) -> LoopResult:
    """Deterministic self-composition-call-chain repair (mirrors ``mutation_repair_loop``,
    REQ-4, for a different bug class): mechanically try each
    ``double_application_repair_candidates`` rewrite via the write_file TOOL, run the suite
    via the shell.exec TOOL, and keep the first candidate that passes. No reasoning call —
    fully reproducible (Tenet 3)."""
    rt = Runtime()
    target_path = Path(target)
    original = target_path.read_text(encoding="utf-8")
    candidates = double_application_repair_candidates(original)

    def _run_tests() -> int | None:
        res = rt.apply(create_decision(id=f"t-{uuid.uuid4().hex}", source="orchestrator",
                       type="shell.exec", payload={"command": test_cmd, "timeout_s": TEST_TIMEOUT_S, **({"cwd": cwd} if cwd else {})}))
        return res.get("exitCode") if isinstance(res, dict) else None

    for i, cand in enumerate(candidates, 1):
        rt.apply(create_decision(id=f"dbl-{uuid.uuid4().hex}", source="double-application-repair",
                 type="code.write_file", payload={"path": str(target), "content": cand}))
        code = _run_tests()
        if verbose:
            _step("double-apply", f"candidate {i}/{len(candidates)} -> exit {code}")
        if code == 0:
            return LoopResult(success=True, attempts=i, final_output="double-application repair passed")
    # No candidate worked: restore the original bug so we never leave a worse file.
    target_path.write_text(original, encoding="utf-8", newline="\n")
    return LoopResult(success=False, attempts=len(candidates),
                      final_output="no double-application repair passed")
# #EXT-003-REQ-7 End


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
        # #EXT-003-REQ-7 Start
        # Tried FIRST (cheap, structural): a self-composition call-chain bug (REQ-7) — a
        # value re-applied to the SAME function down the chain (e.g. tax/discount applied
        # twice) — never touches the function's own body, so it can't introduce the
        # rounding instability the model's own equivalent-rewrite sometimes does. Runs on a
        # FRESH copy of the original bug; falls through to boundary-mutation unaffected if
        # it finds no candidate or none passes.
        target_path.write_text(original_content, encoding="utf-8", newline="\n")  # restore the real bug
        lr = double_application_repair_loop(target, test_cmd, cwd=cwd, verbose=verbose)
        if lr.success:
            _v(print, f"\n  \033[32m[OK] double-application repair solved it\033[0m\n")
            return lr
        # #EXT-003-REQ-7 End
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


# #EXT-057-REQ-2 Start
def solve_streaming(request, *, llm=None, solve_fn=None, on_cancel=None, max_tokens=1024):
    """The interactive solve path as a GENERATOR of stream-bus events (EXT-057 REQ-2) -- the seam
    the rebuilt REPL (`harness/repl_render.render_stream`) consumes to feel like Claude Code instead
    of running silently and dumping one block.

    Two modes, chosen by whether the caller passes the real orchestration as ``solve_fn``:

    * ``solve_fn`` given (the REPL passes ``cli._route_plain``): run the FULL orchestration so tool
      routing/capability is UNCHANGED (its tool/Decision activity already streams live through the
      EXT-045 ``Runtime.on_event`` printer -- no new side-effect path, Tenet 1). We yield a
      ``thinking`` indicator so the cursor is never dead during the model's work, then the final
      response text + ``done``. ``solve_fn`` returns either ``(text, label)`` or a plain string.
    * no ``solve_fn`` (a pure conversational turn): stream the model's answer token-by-token via
      TASK-1's ``llm.stream_complete`` -- each delta is an ``assistant_token`` event -- falling back
      to blocking ``llm.complete`` if streaming is unavailable.

    Honors a cooperative ``on_cancel()`` (EXT-055) between chunks -> a ``cancel`` event. NEVER raises
    out of the generator: any internal error becomes a final ``assistant_token`` + ``done`` so the
    REPL always terminates a turn cleanly. Model streaming of the ORCHESTRATOR's own reasoning (vs a
    conversational turn) is a follow-up (threads ``stream_complete`` into the agent calls)."""
    import queue as _queue
    import threading
    from harness import stream_bus

    def _cancelled():
        try:
            return bool(on_cancel and on_cancel())
        except Exception:
            return False

    # --- mode A: real orchestration (capability preserved; tool events print via on_event) -------
    if solve_fn is not None:
        result = {"text": ""}
        doneq: "_queue.Queue" = _queue.Queue()

        def _run():
            try:
                out = solve_fn(request)
                result["text"] = out[0] if isinstance(out, tuple) and out else (
                    "" if out is None else str(out))
            except Exception as exc:  # noqa: BLE001
                result["text"] = f"error: {exc}"
            finally:
                doneq.put(True)

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        yield stream_bus.thinking("working")
        while True:
            try:
                doneq.get(timeout=0.2)
                break
            except _queue.Empty:
                if _cancelled():
                    yield stream_bus.cancel()
                    return
        text = result.get("text", "")
        yield stream_bus.assistant_token(text)
        yield stream_bus.done(text)
        return

    # --- mode B: conversational -> stream the model's answer token-by-token ----------------------
    parts: "list[str]" = []
    try:
        from jaros.llm import LlmRequest
        req = LlmRequest(prompt=str(request), params={"max_tokens": max_tokens})
        streamer = getattr(llm, "stream_complete", None)
        if streamer is not None:
            for delta in streamer(req):
                if not delta:
                    continue
                parts.append(delta)
                yield stream_bus.assistant_token(delta)
                if _cancelled():
                    yield stream_bus.cancel()
                    yield stream_bus.done("".join(parts))
                    return
        if not parts:  # streaming unavailable or empty -> blocking fallback
            text = llm.complete(req).text if llm is not None else ""
            parts.append(text)
            yield stream_bus.assistant_token(text)
    except Exception as exc:  # noqa: BLE001 -- never raise out of the generator
        parts.append(f"error: {exc}")
        yield stream_bus.assistant_token(parts[-1])
    yield stream_bus.done("".join(parts))
# #EXT-057-REQ-2 End
