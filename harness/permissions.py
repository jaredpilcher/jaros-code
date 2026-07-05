"""EXT-048: user-configurable permission rules + REPL modes -- closes `docs/GAP-MAP.md`
Product-surface parity row #17.

A user drops a plain JSON file at ``.jcode/permissions.json`` (project tier) and/or
``~/.jcode/permissions.json`` (user tier, mirroring the EXT-042 ``JCODE.md`` / EXT-046 ``skills``
/ EXT-047 ``hooks`` two-tier convention) holding a list of rules, each
``{"tool": <glob, optional>, "arg": <glob, optional>, "action": "allow"|"ask"|"deny"}``. The config
file is pure inert DATA (Tenet 1, two-plane discipline): this module only loads/parses it and
resolves WHICH rule (if any) applies to a given tool/arg -- it never decides anything about the
host's actual safety envelope.

**THE SAFETY INVARIANT (the entire point of this spec).** A permission rule is consulted by
``harness.coding_loop.Runtime.apply`` STRICTLY AFTER the existing hard gate
(``jaros.core.decision_gate.validate_decision`` -- egress/destructive-ops denylist, secrets,
path-jail) has already accepted the Decision. A user ``"allow"`` rule can therefore only ever
NARROW what already passed those gates -- it can NEVER widen, weaken, or bypass them. See
``Runtime.apply`` in ``harness/coding_loop.py`` for the enforcement order, and
``tests/test_ext048_permissions.py`` for the explicit proof (an `allow` rule for a denylisted
`shell.exec` command is still refused by the hard gate, with the gate's own rejection reason).

**Modes** (``plan``/``default``/``acceptEdits``) are a SEPARATE, stronger mechanism than a
permission rule: ``plan`` mode withholds every write/shell Decision before the gate or hooks ever
see it (a true "propose only," never even attempted), while ``acceptEdits`` narrowly auto-approves
an ``"ask"``-resolving WRITE Decision (never ``shell.exec``) that has already passed the hard gate.

Every function here is defensive, mirroring ``harness/hooks.py``/``harness/skills.py``: a
missing/unreadable permissions file, an unresolvable home directory, or a malformed config degrades
to "no rules configured" rather than raising -- a permissions feature must never crash the CLI it
extends. No ``.jcode/permissions.json`` anywhere (either tier) is a complete no-op: zero behavior
change (``decide()`` with no rules always resolves ``"allow"``, exactly today's implicit policy).
"""

# #EXT-048-REQ-1 Start
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_PROJECT_PERMISSIONS_SUBPATH = Path(".jcode") / "permissions.json"
_USER_PERMISSIONS_SUBPATH = Path(".jcode") / "permissions.json"

VALID_ACTIONS = ("allow", "ask", "deny")


@dataclass(frozen=True)
class PermissionRule:
    """One configured permission rule: ``tool`` (a glob against the Decision `type`, ``None``/
    absent matches every tool) and ``arg`` (a glob against a resolved string argument -- e.g. a
    path or shell command, ``None``/absent matches every arg) together gate ``action``
    (``"allow"``/``"ask"``/``"deny"``). ``source`` is the config file path, for diagnostics."""

    tool: "str | None"
    arg: "str | None"
    action: str
    source: str = ""


def _parse_rule_item(item, source: str) -> "PermissionRule | None":
    """Parse one rule entry. Returns ``None`` (skip) for anything malformed (not a dict, missing/
    invalid ``action``) -- never raises."""
    if not isinstance(item, dict):
        return None
    action = item.get("action")
    if action not in VALID_ACTIONS:
        return None
    tool = item.get("tool")
    tool = tool.strip() if isinstance(tool, str) and tool.strip() else None
    arg = item.get("arg")
    arg = arg.strip() if isinstance(arg, str) and arg.strip() else None
    return PermissionRule(tool=tool, arg=arg, action=action, source=source)


def _parse_permissions_file(path: Path) -> "list[PermissionRule]":
    """Parse one ``permissions.json`` file into an ordered ``[PermissionRule, ...]``. Never
    raises: a missing file, unreadable/non-UTF-8 file, invalid JSON, an unrecognized top-level
    shape, or any per-item malformation degrades to that piece contributing nothing rather than
    aborting the whole parse (a single bad rule entry never blocks the others). Accepts either a
    bare top-level list of rules or ``{"rules": [...]}`` (both are common settings-file shapes)."""
    try:
        if not path.is_file():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(raw, dict):
        items = raw.get("rules")
    elif isinstance(raw, list):
        items = raw
    else:
        return []
    if not isinstance(items, list):
        return []
    return [r for r in (_parse_rule_item(item, str(path)) for item in items) if r is not None]


def load_project_permissions(root: "str | Path" = ".") -> "list[PermissionRule]":
    """Discover + parse the PROJECT-level ``<root>/.jcode/permissions.json``. Returns ``[]`` when
    absent, unreadable, or malformed -- never raises."""
    try:
        return _parse_permissions_file(Path(root) / _PROJECT_PERMISSIONS_SUBPATH)
    except Exception:
        return []


def load_user_permissions() -> "list[PermissionRule]":
    """Discover + parse the USER-level ``~/.jcode/permissions.json``. Returns ``[]`` when absent,
    unreadable, malformed, or the home directory can't be resolved -- never raises."""
    try:
        home = Path.home()
    except Exception:
        return []
    try:
        return _parse_permissions_file(home / _USER_PERMISSIONS_SUBPATH)
    except Exception:
        return []


def load_permission_rules(root: "str | Path" = ".") -> "list[PermissionRule]":
    """Combine the PROJECT + USER tiers into one ordered rule list: PROJECT rules come FIRST,
    then USER rules -- since `decide()` is first-match-wins, this means a project rule takes
    precedence over a same-shaped user default. Returns ``[]`` (no rules anywhere) when neither
    tier has content -- a graceful no-op that leaves every caller byte-identical to before this
    spec (``decide([], ...)`` always resolves ``"allow"``). Never raises.
    """
    try:
        project = load_project_permissions(root)
    except Exception:
        project = []
    try:
        user = load_user_permissions()
    except Exception:
        user = []
    return list(project) + list(user)
# #EXT-048-REQ-1 End


# #EXT-048-REQ-2 Start
def _globmatch(pattern: "str | None", value: "str | None") -> bool:
    """``None``/absent pattern matches everything. A pattern WITH a value only matches when
    `value` is known and glob-matches it -- never raises."""
    if not pattern or pattern == "*":
        return True
    if value is None:
        return False
    try:
        import fnmatch
        return fnmatch.fnmatch(str(value), pattern)
    except Exception:
        return False


def _rule_matches(rule: PermissionRule, tool_name: "str | None", arg: "str | None") -> bool:
    try:
        return _globmatch(rule.tool, tool_name) and _globmatch(rule.arg, arg)
    except Exception:
        return False


def decide(rules: "list[PermissionRule] | None", tool_name: "str | None",
           arg: "str | None" = None) -> str:
    """Resolve the effective action for `tool_name`/`arg`: the FIRST rule (in list order) whose
    `tool`/`arg` globs both match wins outright -- later rules are never consulted once a match is
    found (first-match-wins; list rules from most- to least-specific). No matching rule (including
    an empty/``None`` `rules`) resolves ``"allow"`` -- today's implicit policy (no EXTRA
    restriction beyond whatever hard gate already governs this Decision), which is exactly what
    makes "no permissions.json anywhere" a complete no-op. Never raises.

    ★ SAFETY INVARIANT (see module docstring): this function is advisory data-lookup ONLY -- it
    has no access to, and no ability to influence, the hard gate. Callers (see
    ``harness.coding_loop.Runtime.apply``) MUST consult this only AFTER the hard gate has already
    accepted the Decision, never before and never as a substitute for it.
    """
    try:
        for rule in rules or []:
            if _rule_matches(rule, tool_name, arg):
                return rule.action
    except Exception:
        pass
    return "allow"


def resolve_decision_arg(decision) -> "str | None":
    """Best-effort extraction of a representative string argument from a Decision's payload, for
    arg-glob matching (e.g. a file `path`, a shell `command`, a rename `target`, a commit
    `message`). Returns ``None`` when the payload has none of these -- never raises."""
    try:
        payload = getattr(decision, "payload", None)
        if not isinstance(payload, dict):
            return None
        for key in ("path", "command", "target", "message"):
            val = payload.get(key)
            if isinstance(val, str) and val:
                return val
            if isinstance(val, list) and val:
                return " ".join(str(v) for v in val)
    except Exception:
        pass
    return None
# #EXT-048-REQ-2 End


# #EXT-048-REQ-4 Start
# REPL modes (Claude-Code-style): `plan` (propose only -- no side effects), `default` (today's
# behavior, unchanged), `acceptEdits` (auto-approve an `"ask"`-resolving WRITE Decision that
# already passed the hard gate -- never `shell.exec`, a narrower auto-approval than "everything").
MODES = ("plan", "default", "acceptEdits")
DEFAULT_MODE = "default"

# Decision types withheld ENTIRELY under `plan` mode -- described, never executed, never even
# reaching the gate or hooks. Read-only types (fs.read/fs.grep/...) are deliberately NOT in this
# set, so information-gathering still works while the user is in propose-only plan mode.
PLAN_MODE_WITHHELD_TYPES = frozenset({
    "code.write_file", "code.apply_patch", "code.search_replace", "shell.exec",
})

# The narrower subset `acceptEdits` auto-approves on an `"ask"` result -- deliberately EXCLUDES
# `shell.exec` (running an arbitrary command is not "an edit"; it still needs an explicit allow
# rule, an interactive approval, or falls back to the safe deny).
ACCEPT_EDITS_AUTO_TYPES = frozenset({
    "code.write_file", "code.apply_patch", "code.search_replace",
})
# #EXT-048-REQ-4 End
