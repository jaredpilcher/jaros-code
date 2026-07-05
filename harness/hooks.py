"""EXT-047: user-configurable lifecycle hooks -- closes `docs/GAP-MAP.md` Product-surface parity
row #16.

A user drops a plain JSON file at ``.jcode/hooks.json`` (project tier) and/or
``~/.jcode/hooks.json`` (user tier, mirroring the EXT-042 ``JCODE.md`` / EXT-046 ``skills``
two-tier convention) mapping a lifecycle EVENT (``PreToolUse``, ``PostToolUse``,
``SessionStart``, ``Stop``) to a list of shell commands to run, optionally scoped to a tool-name
``matcher`` glob (PreToolUse/PostToolUse only -- mirrors Claude Code's own hooks config shape).
The config file is pure inert DATA (Tenet 1, two-plane discipline): this module only loads/parses
it and decides WHICH configured hook(s) apply to a given event/tool -- it never runs a hook
directly with a raw ``subprocess`` call. Every hook command is executed through the SAME gated
``shell.exec`` Decision path (``harness.coding_loop.Runtime`` -> the Jaros gate's ``validate()`` /
``execute()``, denylist + timeout + process-tree-kill) every other tool call already goes through
-- hooks are user-authorized, but never bypass the security gates.

**Anti-recursion, by construction.** The default hook runner builds a FRESH, hooks-DISABLED
``Runtime`` purely to execute the hook's own shell command -- so firing a hook can never
re-trigger hook firing (a ``PreToolUse`` hook matching ``shell.exec`` would otherwise recurse
forever the moment ANY hook -- including itself -- ran a shell command). The Runtime a caller
uses for its own tool calls (e.g. ``harness.cli.JcodeCli.rt``) is a SEPARATE instance that carries
the real ``hooks_config`` and fires PreToolUse/PostToolUse hooks around each Decision it applies
(see ``harness.coding_loop.Runtime.apply``).

**Block-on-nonzero (Claude-Code-style).** A ``PreToolUse`` hook that exits non-zero BLOCKS the
tool call it was about to gate -- the clerk refuses it, deterministically and honestly (no tool
call, no partial effect). ``PostToolUse``/``SessionStart``/``Stop`` hooks are observational only
(their exit code is recorded but never blocks anything -- the tool/session event they attach to
has already happened, or is a lifecycle boundary with nothing left to refuse).

Every function here is defensive, mirroring ``harness/skills.py`` and ``harness/jcode_md.py``: a
missing/unreadable hooks file, an unresolvable home directory, or a malformed config degrades to
"no hooks configured" rather than raising -- a hooks feature must never crash the CLI it extends.
No ``.jcode/hooks.json`` anywhere (either tier) is a complete no-op: zero behavior change.
"""

# #EXT-047-REQ-1 Start
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_PROJECT_HOOKS_SUBPATH = Path(".jcode") / "hooks.json"
_USER_HOOKS_SUBPATH = Path(".jcode") / "hooks.json"

# The four lifecycle events this spec supports (mirrors Claude Code's hook surface).
VALID_EVENTS = ("PreToolUse", "PostToolUse", "SessionStart", "Stop")
_TOOL_SCOPED_EVENTS = frozenset({"PreToolUse", "PostToolUse"})


@dataclass(frozen=True)
class HookDef:
    """One configured hook: a shell ``command`` to run on `event`, optionally scoped to tool
    names matching `matcher` (a glob pattern; ``None``/absent matches every tool -- only
    meaningful for PreToolUse/PostToolUse). ``source`` is the config file path, for diagnostics."""

    command: str
    matcher: "str | None" = None
    source: str = ""


@dataclass(frozen=True)
class HookOutcome:
    """The observed result of firing one configured hook."""

    event: str
    command: str
    matcher: "str | None"
    exit_code: "int | None"
    stdout: str
    stderr: str
    blocked: bool  # True only for a PreToolUse hook that exited non-zero


def _parse_hook_item(item, source: str) -> "HookDef | None":
    """Parse one entry of an event's hook list. Returns ``None`` (skip) for anything malformed
    (not a dict, missing/blank ``command``) -- never raises."""
    if not isinstance(item, dict):
        return None
    command = item.get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    matcher = item.get("matcher")
    matcher = matcher.strip() if isinstance(matcher, str) and matcher.strip() else None
    return HookDef(command=command, matcher=matcher, source=source)


def _parse_hooks_file(path: Path) -> "dict[str, list[HookDef]]":
    """Parse one ``hooks.json`` file into ``{event: [HookDef, ...]}``. Never raises: a missing
    file, unreadable/non-UTF-8 file, invalid JSON, a non-dict top level, or any per-event/per-item
    malformation degrades to that piece contributing nothing rather than aborting the whole
    parse (a single bad hook entry never blocks the others)."""
    out: "dict[str, list[HookDef]]" = {}
    try:
        if not path.is_file():
            return out
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    if not isinstance(raw, dict):
        return out
    for event in VALID_EVENTS:
        items = raw.get(event)
        if not isinstance(items, list):
            continue
        defs = [hd for hd in (_parse_hook_item(item, str(path)) for item in items) if hd is not None]
        if defs:
            out[event] = defs
    return out


def load_project_hooks(root: "str | Path" = ".") -> "dict[str, list[HookDef]]":
    """Discover + parse the PROJECT-level ``<root>/.jcode/hooks.json``. Returns ``{}`` when
    absent, unreadable, or malformed -- never raises."""
    try:
        return _parse_hooks_file(Path(root) / _PROJECT_HOOKS_SUBPATH)
    except Exception:
        return {}


def load_user_hooks() -> "dict[str, list[HookDef]]":
    """Discover + parse the USER-level ``~/.jcode/hooks.json``. Returns ``{}`` when absent,
    unreadable, malformed, or the home directory can't be resolved -- never raises."""
    try:
        home = Path.home()
    except Exception:
        return {}
    try:
        return _parse_hooks_file(home / _USER_HOOKS_SUBPATH)
    except Exception:
        return {}


def load_hooks(root: "str | Path" = ".") -> "dict[str, list[HookDef]]":
    """Combine the PROJECT + USER tiers into one ``{event: [HookDef, ...]}`` mapping: BOTH tiers'
    hooks fire for a given event (project-tier hooks run first, then user-tier), unlike the
    EXT-046 skills registry's project-wins-on-collision rule -- there is no name collision here,
    every configured hook for an event is additive. Returns ``{}`` (no hooks anywhere) when
    neither tier has content -- a graceful no-op that leaves every caller byte-identical to
    before this spec. Never raises.
    """
    project = load_project_hooks(root)
    user = load_user_hooks()
    merged: "dict[str, list[HookDef]]" = {}
    for event in VALID_EVENTS:
        combined = list(project.get(event, [])) + list(user.get(event, []))
        if combined:
            merged[event] = combined
    return merged
# #EXT-047-REQ-1 End


# #EXT-047-REQ-2 Start
def _matches(matcher: "str | None", tool_name: "str | None") -> bool:
    """A hook with no matcher (or ``matcher="*"``) applies to every tool. A hook WITH a matcher
    only applies when `tool_name` is known and glob-matches it -- never raises."""
    if not matcher or matcher == "*":
        return True
    if not tool_name:
        return False
    try:
        import fnmatch
        return fnmatch.fnmatch(tool_name, matcher)
    except Exception:
        return False


def _default_run_command(command: str, cwd: "str | None") -> dict:
    """Run one hook's shell command through the SAME gated ``shell.exec`` Decision path every
    other tool call uses (the Jaros gate's ``validate()``/``execute()``, denylist + timeout +
    process-tree-kill -- see ``.jaros-data/tools/shell_exec_tool.py``) via a FRESH,
    hooks-disabled ``harness.coding_loop.Runtime`` -- so firing this hook can never recursively
    re-trigger hook firing (see module docstring). Never raises: a gate rejection or executor
    refusal (``RuntimeError`` from ``Runtime.apply``) is reported as an honest non-zero exit,
    exactly like a real failing shell command would be.
    """
    try:
        import uuid
        from jaros.core import create_decision
        from harness.coding_loop import Runtime

        rt = Runtime(root=cwd)  # no hooks_config -> cannot recurse into hook-firing itself
        decision = create_decision(
            id=f"hook-{uuid.uuid4().hex}", source="hooks", type="shell.exec",
            payload={"command": command, "cwd": cwd, "timeout_s": 30},
        )
        result = rt.apply(decision)
        return result if isinstance(result, dict) else {"exitCode": None, "stdout": "", "stderr": ""}
    except RuntimeError as exc:
        # The gate refused the command (e.g. the shell.exec denylist) or the executor refused
        # it -- an honest non-zero exit, never bypassed and never silently swallowed.
        return {"exitCode": 1, "stdout": "", "stderr": str(exc)}
    except Exception as exc:  # never raise -- a hook failure must never crash its caller
        return {"exitCode": 1, "stdout": "", "stderr": f"hook failed to run: {exc}"}


def fire_event(event: str, hooks_config: "dict | None", *, tool_name: "str | None" = None,
               cwd: "str | None" = None, run_command=None) -> "list[HookOutcome]":
    """Fire every hook configured for `event` in `hooks_config`, skipping any whose `matcher`
    doesn't match `tool_name` (only checked for PreToolUse/PostToolUse -- SessionStart/Stop have
    no tool to scope against and always fire). Each hook runs via `run_command` (a
    ``(command, cwd) -> {"exitCode", "stdout", "stderr"}`` callable; defaults to
    :func:`_default_run_command`, the real gated path -- tests may inject a fake/echo runner).

    Never raises: an unknown `event`, a ``None``/malformed `hooks_config`, or any single hook's
    own failure degrades to "contributes nothing" (that hook, or the whole call) rather than
    raising -- hook firing must never crash the tool call or session lifecycle it observes.
    """
    if event not in VALID_EVENTS:
        return []
    try:
        defs = (hooks_config or {}).get(event) or []
    except Exception:
        return []
    if not defs:
        return []

    runner = run_command or _default_run_command
    outcomes: "list[HookOutcome]" = []
    for hd in defs:
        try:
            if event in _TOOL_SCOPED_EVENTS and not _matches(hd.matcher, tool_name):
                continue
            result = runner(hd.command, cwd)
            result = result if isinstance(result, dict) else {}
            exit_code = result.get("exitCode")
            blocked = event == "PreToolUse" and exit_code is not None and exit_code != 0
            outcomes.append(HookOutcome(
                event=event, command=hd.command, matcher=hd.matcher, exit_code=exit_code,
                stdout=result.get("stdout") or "", stderr=result.get("stderr") or "",
                blocked=blocked,
            ))
        except Exception:
            continue
    return outcomes


def blocked(outcomes: "list[HookOutcome] | None") -> bool:
    """True iff any outcome in `outcomes` was a blocking PreToolUse hook. Never raises."""
    try:
        return any(getattr(o, "blocked", False) for o in (outcomes or []))
    except Exception:
        return False


def blocking_reason(outcomes: "list[HookOutcome] | None") -> "str | None":
    """The first blocking hook's honest reason string, or ``None`` if nothing blocked. Never
    raises."""
    try:
        for o in outcomes or []:
            if getattr(o, "blocked", False):
                return (f"PreToolUse hook {o.command!r} exited {o.exit_code} -- tool call refused"
                        + (f" (matcher={o.matcher!r})" if o.matcher else ""))
    except Exception:
        pass
    return None
# #EXT-047-REQ-2 End
