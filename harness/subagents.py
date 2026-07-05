"""EXT-050: user-authorable subagents -- closes `docs/GAP-MAP.md` Product-surface parity row #19.

A user drops a plain markdown file at ``.jcode/agents/<name>.md`` (project tier) or
``~/.jcode/agents/<name>.md`` (user tier, mirroring the EXT-042 ``JCODE.md`` / EXT-046 ``skills`` /
EXT-047 ``hooks`` / EXT-048 ``permissions`` two-tier convention) and it becomes a delegatable,
scoped subagent -- no code change to jaros-code required. The file is pure inert DATA (Tenet 1,
two-plane discipline): this module only DISCOVERS and PARSES it and composes its body (a
system-prompt prefix) with a delegated task; it is never executed as code, and no model call
happens here. The composed prompt is handed by ``harness/cli.py`` to the SAME plain-language
routing chain ``JcodeCli._route_plain`` already runs for any request -- this module adds no new
reasoning mechanism.

A subagent's optional ``tools:`` frontmatter (a CSV allowlist of tool/Decision type names) is
enforced NOT here, but at ``harness.coding_loop.Runtime.apply`` -- the SAME gate -> executor ->
decision-log seam EXT-047's hooks and EXT-048's permission rules already use -- via a new
``tool_allowlist`` constructor parameter, consulted STRICTLY AFTER the hard gate has already
accepted the Decision. This is the safety invariant the whole spec exists to prove: a subagent's
allowlist can only NARROW what the hard gates already permit, never widen past them.

Every function here is defensive: a missing/unreadable agents directory, an unresolvable home
directory, or a malformed individual file degrades to "contributes nothing" rather than raising --
observability/extensibility must never crash the CLI it extends (the same discipline
``harness/skills.py`` and ``harness/jcode_md.py`` already follow).
"""

# #EXT-050-REQ-1 Start
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_SUBDIR = Path(".jcode") / "agents"
_USER_SUBDIR = Path(".jcode") / "agents"


@dataclass(frozen=True)
class SubagentDef:
    """One discovered subagent: a user-authored, delegatable scoped agent backed by a markdown
    system-prompt body. ``description``/``model`` come from optional frontmatter and default to
    ""/``None`` when absent. ``tools`` is a tuple of tool/Decision type names parsed from the CSV
    `tools:` frontmatter value (empty tuple when absent -- "no extra narrowing beyond the hard
    gates"). ``source`` is the path the subagent was loaded from (for diagnostics only)."""

    name: str
    description: str
    tools: "tuple[str, ...]" = field(default_factory=tuple)
    model: "str | None" = None
    body: str = ""
    source: str = ""


def _split_frontmatter(text: str) -> "tuple[dict, str]":
    """Split an optional leading ``---``-delimited frontmatter block off `text`.

    Only a tolerant, line-based ``key: value`` parse is performed (no YAML dependency) -- this
    module recognizes exactly ``description``, ``tools``, and ``model``; any other key is ignored.
    Returns ``({}, text)`` unchanged when `text` doesn't open with a frontmatter delimiter."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta: dict = {}
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        line = lines[i]
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip().lower()] = val.strip()
        i += 1
    if i >= len(lines):   # no closing '---' found -- treat the whole thing as body, no frontmatter
        return {}, text
    body = "\n".join(lines[i + 1:]).lstrip("\n")
    return meta, body


def _parse_tools_field(raw: "str | None") -> "tuple[str, ...]":
    """Parse a CSV `tools:` frontmatter value into an order-preserving tuple of tool/Decision
    type names, dropping empty entries. Never raises on `None`/malformed input."""
    if not raw or not isinstance(raw, str):
        return ()
    out = []
    for part in raw.split(","):
        part = part.strip()
        if part and part not in out:
            out.append(part)
    return tuple(out)


def _parse_subagent_file(path: Path) -> "SubagentDef | None":
    """Parse one ``<name>.md`` subagent file into a `SubagentDef`, or `None` when it should be
    skipped (unreadable, empty body, or a filename that can't cleanly become a subagent name).
    Never raises."""
    name = path.stem
    if not name.isidentifier():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    meta, body = _split_frontmatter(text)
    body = body.strip()
    if not body:
        return None
    model = meta.get("model") or None
    return SubagentDef(
        name=name,
        description=meta.get("description", ""),
        tools=_parse_tools_field(meta.get("tools")),
        model=model,
        body=body,
        source=str(path),
    )


def _discover_tier(directory: Path) -> "dict[str, SubagentDef]":
    """Discover every valid subagent under one `directory` (non-recursive, ``*.md`` only). Never
    raises -- a missing/unreadable directory yields ``{}``."""
    out: "dict[str, SubagentDef]" = {}
    try:
        if not directory.is_dir():
            return out
        paths = sorted(directory.glob("*.md"))
    except OSError:
        return out
    for p in paths:
        subagent = _parse_subagent_file(p)
        if subagent is not None:
            out[subagent.name] = subagent
    return out


def discover_subagents(root: "str | Path" = ".") -> "dict[str, SubagentDef]":
    """Discover every subagent visible to `root`: the PROJECT tier
    (``<root>/.jcode/agents/*.md``) then the USER tier (``~/.jcode/agents/*.md``) -- a
    project-tier subagent wins on a name collision. Never raises: any failure on either tier (a
    missing directory, an unresolvable home directory, a permissions error) contributes `{}`
    from that tier only."""
    try:
        project = _discover_tier(Path(root) / _PROJECT_SUBDIR)
    except Exception:
        project = {}
    try:
        home = Path.home()
        user = _discover_tier(home / _USER_SUBDIR)
    except Exception:
        user = {}
    merged = dict(user)
    merged.update(project)   # project tier wins on a name collision
    return merged
# #EXT-050-REQ-1 End


# #EXT-050-REQ-2 Start
def render_subagent_prompt(subagent: "SubagentDef | None", task: "str | None") -> str:
    """Compose a subagent's system-prompt `body` with a delegated `task` into ONE plain-language
    request -- pure string composition, no model call, no placeholder-substitution mechanism
    (unlike EXT-046 skill templates: a subagent's body is a persona/scope prefix, not a
    $ARGUMENTS plan template). Degrades gracefully when either half is empty/`None`; never
    raises."""
    body = (getattr(subagent, "body", "") or "").strip()
    task_text = (task or "").strip()
    if body and task_text:
        return f"{body}\n\nTASK: {task_text}"
    return body or task_text
# #EXT-050-REQ-2 End
