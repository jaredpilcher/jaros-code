"""EXT-046: custom skills / commands (user drop-ins) -- closes `docs/GAP-MAP.md` Product-surface
parity row #15.

A user drops a plain markdown file at ``.jcode/skills/<name>.md`` (project tier) or
``~/.jcode/skills/<name>.md`` (user tier, mirroring the EXT-042 ``JCODE.md`` two-tier convention)
and it becomes a first-class ``/name`` command -- no code change to jaros-code required. The file
is pure inert DATA (Tenet 1, two-plane discipline): this module only DISCOVERS and PARSES it and
substitutes ``$ARGUMENTS``/``$1``/``$2``... placeholders (Claude-Code-style) into its body; it is
never executed as code, and no model call happens here. The substituted body is handed by
``harness/cli.py`` to the SAME plain-language routing chain ``JcodeCli.handle()`` already runs for
any request -- this module adds no new reasoning mechanism.

Every function here is defensive: a missing/unreadable skills directory, an unresolvable home
directory, or a malformed individual file degrades to "contributes nothing" rather than raising --
observability/extensibility must never crash the CLI it extends (the same discipline
``harness/jcode_md.py`` and ``harness/project_md.py`` already follow).
"""

# #EXT-046-REQ-1 Start
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_PROJECT_SUBDIR = Path(".jcode") / "skills"
_USER_SUBDIR = Path(".jcode") / "skills"


@dataclass(frozen=True)
class SkillDef:
    """One discovered skill: a user-authored ``/name`` command backed by a markdown plan
    template. ``description``/``argument_hint`` come from optional frontmatter and default to
    "" when absent. ``source`` is the path the skill was loaded from (for diagnostics only)."""

    name: str
    description: str
    argument_hint: str
    body: str
    source: str


def _split_frontmatter(text: str) -> "tuple[dict, str]":
    """Split an optional leading ``---``-delimited frontmatter block off `text`.

    Only a tolerant, line-based ``key: value`` parse is performed (no YAML dependency) -- this
    module recognizes exactly ``description`` and ``argument-hint``; any other key is ignored.
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


def _parse_skill_file(path: Path) -> "SkillDef | None":
    """Parse one ``<name>.md`` skill file into a `SkillDef`, or `None` when it should be
    skipped (unreadable, empty body, or a filename that can't cleanly become a `/name`
    command). Never raises."""
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
    return SkillDef(
        name=name,
        description=meta.get("description", ""),
        argument_hint=meta.get("argument-hint", meta.get("argument_hint", "")),
        body=body,
        source=str(path),
    )


def _discover_tier(directory: Path) -> "dict[str, SkillDef]":
    """Discover every valid skill under one `directory` (non-recursive, ``*.md`` only). Never
    raises -- a missing/unreadable directory yields ``{}``."""
    out: "dict[str, SkillDef]" = {}
    try:
        if not directory.is_dir():
            return out
        paths = sorted(directory.glob("*.md"))
    except OSError:
        return out
    for p in paths:
        skill = _parse_skill_file(p)
        if skill is not None:
            out[skill.name] = skill
    return out


def discover_skills(root: "str | Path" = ".") -> "dict[str, SkillDef]":
    """Discover every skill visible to `root`: the PROJECT tier (``<root>/.jcode/skills/*.md``)
    then the USER tier (``~/.jcode/skills/*.md``) -- a project-tier skill wins on a name
    collision. Never raises: any failure on either tier (a missing directory, an unresolvable
    home directory, a permissions error) contributes `{}` from that tier only."""
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
# #EXT-046-REQ-1 End


# #EXT-046-REQ-2 Start
def render_template(body: "str | None", arg_text: "str | None") -> str:
    """Substitute ``$ARGUMENTS`` (the whole argument string) and ``$1``/``$2``/... (individual
    whitespace-split tokens of `arg_text`, 1-indexed) into `body` -- Claude-Code-style plan-
    template substitution. A template with no placeholders passes through unchanged. Never
    raises on `None`/empty input (degrades to the empty string / the template as-is)."""
    if not body:
        return ""
    text = arg_text or ""
    tokens = text.split()
    rendered = body.replace("$ARGUMENTS", text)
    for i, tok in enumerate(tokens, start=1):
        rendered = rendered.replace(f"${i}", tok)
    # Any remaining $N placeholder (position beyond what was supplied) resolves to "".
    import re
    rendered = re.sub(r"\$(\d+)", "", rendered)
    return rendered
# #EXT-046-REQ-2 End
