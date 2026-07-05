"""Product-Parity Checklist (EXT-041) -- the scoreboard for jaros-code's product-surface parity axis.

PRIME-001 (owner/supervisor directive 2026-07-04) sharpened the parity bar to the WHOLE Claude
Code CLI PRODUCT, not just how well the model solves tasks. `docs/GAP-MAP.md`'s
"## Product-surface parity" section (rows #12-27) records, feature-by-feature, whether jcode has
each piece of the Claude Code CLI surface (sessions, headless/piping, an instruction-memory
hierarchy, custom commands/skills, hooks, permissions, an MCP client, subagents,
checkpoint/rewind, interrupt-and-steer, long-session context management, background runs,
terminal UX, install/health, multimodal input, and deliberately-deferred surfaces). This module
turns that table into a small, queryable, deterministic instrument: ``PARITY_ROWS`` (the
transcribed rows), ``score()`` (an aggregate percentage + a ranked attack list), and ``render()``
(a readable table for the ``/parity`` CLI command).

Two-plane discipline (Tenet 1): this is pure execution-plane bookkeeping -- no model calls. No
row state is a model judgement; every value here is a transcribed fact, sourced from GAP-MAP as
of ``LAST_SYNCED``. Per Tenet 3, states are NEVER inflated: a row is ``"works"`` only when the
matching CC feature is built AND wired end-to-end with a passing test suite -- not merely a
lever named. As of ``LAST_SYNCED``, nine rows (#12 EXT-044 sessions continue/resume/fork/name,
#13 EXT-043 headless/piping, #14 EXT-042's JCODE.md instruction hierarchy, #15 EXT-046's custom
skills/commands, #16 EXT-047's user-configurable lifecycle hooks, #17 EXT-048's permission rules
+ modes UX, #19 EXT-050's user-authorable subagents, #20 EXT-049's fine-grained checkpoint/
rewind, #24 EXT-045's streaming tool events + statusline) are genuinely ``"works"``; most
others remain ``"missing"``
(GAP-MAP state ``unmeasured``) or ``"partial"`` (GAP-MAP state ``probed`` / ``lever-named``, i.e.
something exists but the CC-parity feature is not yet delivered). That honest baseline, not a
flattering one, is the entire point of the instrument.

MONTHLY RE-SYNC (owner directive): Claude Code is a moving target. Re-audit the official docs
(code.claude.com/docs: overview, cli-reference, commands/skills, hooks, memory, MCP, sub-agents,
checkpointing, settings) at least monthly, update `docs/GAP-MAP.md`'s Product-surface parity
section first, then mirror any row additions/state changes here and bump LAST_SYNCED.
"""

# #EXT-041-REQ-1 Start
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

# The date this module's PARITY_ROWS were last checked against docs/GAP-MAP.md's
# "## Product-surface parity" section (itself sourced from the official Claude Code docs). Bump
# this whenever the rows below are re-synced (target cadence: monthly).
LAST_SYNCED = "2026-07-04"

# Source of truth for these rows.
GAP_MAP_SOURCE = "docs/GAP-MAP.md#product-surface-parity"

VALID_STATES = ("works", "partial", "missing")

_STATE_WEIGHT = {"works": 1.0, "partial": 0.5, "missing": 0.0}


@dataclass(frozen=True)
class ProductParityRow:
    """One row of the Product-Parity Checklist -- mirrors one row of GAP-MAP's
    "## Product-surface parity" table."""

    id: int
    feature: str
    state: str          # one of VALID_STATES
    current_state: str  # one-line honest description of jcode's current state
    next_lever: str      # the next concrete step toward this feature


# Transcribed HONESTLY from docs/GAP-MAP.md, "## Product-surface parity" section, rows #12-27
# (added 2026-07-04). GAP-MAP's own row `State` column (unmeasured / probed / lever-named /
# closed(spec)) maps here as: unmeasured -> missing (nothing built yet), probed / lever-named ->
# partial (something exists but the CC-parity feature is not yet delivered end-to-end),
# closed(spec) -> works (delivered AND test-covered). Rows #12 (EXT-044), #13 (EXT-043), and #14
# (EXT-042) are recorded `closed` in GAP-MAP as of this sync -- every other row stays honestly
# `missing`/`partial`, do not inflate.
PARITY_ROWS: "list[ProductParityRow]" = [
    # #EXT-044-REQ-5 Start
    ProductParityRow(
        id=12, feature="Sessions: continue / resume / fork / name",
        state="works",
        current_state="EXT-044: the EXT-036 REQ-12 session store now carries an optional "
                       "`name` + `created`/`last_active` timestamps and a `.jaros-data/"
                       "sessions/index.json` (name lookup + most-recent, never raises on a "
                       "missing/corrupt index). `jcode -c`/`--continue` resumes the "
                       "most-recently-active session; `-r <id|name>` resumes a specific one by "
                       "id OR its assigned name (honest non-zero-exit error, `JcodeCli` never "
                       "constructed, on an unknown reference); `--fork [<id|name>]` copies a "
                       "session's transcript into a brand-new id, leaving the source file "
                       "byte-unchanged; `/name` and `/fork` mirror both in the REPL. The "
                       "resumed session's prior turns reach the orchestrator/planner context "
                       "via the existing EXT-036 REQ-12/15 `condense()`/`recent()` path (no "
                       "second context mechanism) -- proven end-to-end, not just asserted. A "
                       "fresh invocation with none of these flags is byte-identical to before "
                       "this spec, and the legacy `--resume <id>` flag keeps its exact prior "
                       "(no-error-on-miss) semantics.",
        next_lever="A `--fork-session` alias spelled 1:1 like Claude Code's flag name (cosmetic "
                    "-- `--fork` already delivers the behavior); enforce globally-unique "
                    "session names (today a name collision resolves to the most-recently-"
                    "active match, recorded honestly rather than silently assumed).",
    ),
    # #EXT-044-REQ-5 End
    # #EXT-043-REQ-2 Start
    ProductParityRow(
        id=13, feature="Headless + piping + structured output",
        state="works",
        current_state="EXT-043: stdin piping (`echo req | jcode`, and `jcode -` reads stdin "
                       "unconditionally), `--output-format text|json` (JSON emits a single "
                       "parseable `{request,response,ok,model}` object), a `--max-turns` cap "
                       "(N<1 genuinely refuses to run -- JcodeCli is never constructed; N>=1 is "
                       "a documented no-op above the one-shot path's existing single-turn "
                       "ceiling), and deterministic exit codes (0 success / 1 on any "
                       "construction/handle() failure) are all wired + test-covered, additive "
                       "over the unchanged one-shot/REPL paths. `stream-json` (line-delimited "
                       "event streaming) is honestly deferred -- no per-tool event stream exists "
                       "at the `handle()` seam yet.",
        next_lever="`stream-json` line-delimited output (needs a per-tool/heartbeat event "
                    "stream threaded through `handle()`); `--json-schema`; an explicit `-p` "
                    "alias flag mirroring `claude -p` 1:1.",
    ),
    # #EXT-043-REQ-2 End
    ProductParityRow(
        id=14, feature="Project-instruction memory hierarchy",
        state="works",
        current_state="EXT-042: `JCODE.md` auto-loaded at project root (`<repo>/JCODE.md`) AND "
                       "user level (`~/.jcode/JCODE.md`), injected as a labeled "
                       "`PROJECT INSTRUCTIONS (JCODE.md)` preamble into the orchestrator/planner "
                       "context every plain-language turn; `/init` writes a starter JCODE.md from "
                       "repo comprehension (harness/repo_map.py), root-jailed, never clobbering an "
                       "existing file. Coexists with `.jcode/memory.md` + `/remember` + episodic "
                       "store (unchanged). `@path` imports not yet implemented (deferred, minor).",
        next_lever="`@path` import expansion inside JCODE.md; optional gemma-assisted `/init` "
                    "overview section (deterministic repo-map scaffold ships today).",
    ),
    # #EXT-046-REQ-4 Start
    ProductParityRow(
        id=15, feature="Custom commands / skills",
        state="works",
        current_state="EXT-046: `.jcode/skills/<name>.md` (project) and `~/.jcode/skills/"
                       "<name>.md` (user, project wins on a name collision) register a real "
                       "`/name` command -- `harness/skills.py` discovers + parses optional "
                       "frontmatter (`description`/`argument-hint`) + the markdown body (the "
                       "plan template), never raising on a missing dir or a malformed file. "
                       "`JcodeCli.dispatch` only falls to a matching skill AFTER the existing "
                       "built-in `cmd_*` lookup misses, so a skill can never shadow a built-in; "
                       "the typed args are substituted into the template (`$ARGUMENTS`/`$1`/"
                       "`$2`...) and the rendered text is routed through the SAME plain-language "
                       "chain (`_route_plain`, extracted from `handle()`) a typed non-slash "
                       "request already uses -- no second reasoning mechanism. `/skills` lists "
                       "discovered skills (name + description); `/help` documents the "
                       "convention. A repo with no `.jcode/skills/` anywhere behaves byte-"
                       "identically to before this spec.",
        next_lever="Argument-hint validation/tab-completion; a \"model-invocable when "
                    "relevant\" auto-suggestion mode where the orchestrator itself reaches for "
                    "a skill without the user typing `/name`; skill-authoring/scaffolding "
                    "tooling.",
    ),
    # #EXT-046-REQ-4 End
    # #EXT-047-REQ-5 Start
    ProductParityRow(
        id=16, feature="User-configurable hooks",
        state="works",
        current_state="EXT-047: `.jcode/hooks.json` (project) and `~/.jcode/hooks.json` (user, "
                       "both tiers additive -- no name collision, every configured hook for an "
                       "event fires) map PreToolUse/PostToolUse/SessionStart/Stop to shell "
                       "commands, optionally `matcher`-scoped (a glob against the tool/Decision "
                       "type) for Pre/PostToolUse. `harness.coding_loop.Runtime.apply` -- the "
                       "ONE real gate -> executor -> decision-log choke point every tool call "
                       "already passes through -- fires PreToolUse hooks BEFORE `validate()` and "
                       "PostToolUse hooks AFTER a successful `execute()`; a PreToolUse hook that "
                       "exits non-zero BLOCKS the call (the clerk refuses it, exactly like a "
                       "gate rejection). SessionStart fires once at `JcodeCli` construction, Stop "
                       "fires once at session end (`/quit`/EOF/interrupt in the REPL, or after "
                       "the one-shot headless turn) -- idempotent, guarded against double-firing. "
                       "Every hook's shell command runs through the SAME gated `shell.exec` "
                       "Decision path (denylist + timeout + process-tree-kill) via a FRESH, "
                       "hooks-disabled `Runtime` -- so firing a hook can never recursively "
                       "re-trigger hook firing, and hooks never bypass the security gates. No "
                       "`.jcode/hooks.json` anywhere is a complete no-op (zero behavior change); "
                       "a malformed config degrades to `{}` rather than crashing. `/hooks` lists "
                       "what's configured.",
        next_lever="Surface fired-hook activity in the EXT-045 stream (today only PreToolUse "
                    "blocks emit a stream `error` event; a successful hook's own output isn't "
                    "narrated); a permission-rules-style ask/allow/deny UX around hooks "
                    "(overlaps row #17).",
    ),
    # #EXT-047-REQ-5 End
    # #EXT-048-REQ-5 Start
    ProductParityRow(
        id=17, feature="Permission rules + modes UX",
        state="works",
        current_state="EXT-048: `.jcode/permissions.json` (project) and `~/.jcode/permissions.json` "
                       "(user, project rules consulted first) hold `{tool, arg, action}` rules "
                       "(`action` one of `allow`/`ask`/`deny`, first-match-wins glob on tool/arg); "
                       "`harness.coding_loop.Runtime.apply` -- the same gate -> executor -> "
                       "decision-log choke point EXT-047's hooks use -- consults a matching rule "
                       "ONLY AFTER the hard gate (egress/destructive-ops denylist, secrets, "
                       "path-jail) has already accepted the Decision, so a user `allow` rule can "
                       "NEVER un-block something the hard gate refuses (proven by an explicit "
                       "test: an `allow` rule for a denylisted `shell.exec` command is still "
                       "refused, with the gate's own rejection reason). An `ask` result prompts "
                       "interactively ONLY in the REPL (`interactive=True`, an `input()`-based "
                       "y/n); a headless/one-shot run has no prompt wired and safely DENIES by "
                       "default rather than hanging. A `plan`/`default`/`acceptEdits` mode cycle "
                       "(`/mode`) is wired at the same seam: `plan` withholds every write/shell "
                       "Decision before the gate or hooks ever see it (description only, no side "
                       "effect, proven via the filesystem); `acceptEdits` narrowly auto-approves "
                       "an `ask`-resolving WRITE Decision (never `shell.exec`) that already passed "
                       "the gate. `/permissions` lists configured rules; no config anywhere and "
                       "`mode=\"default\"` are byte-identical no-ops.",
        next_lever="A `bypassPermissions`/\"YOLO\" mode (Claude Code has one; deliberately NOT "
                    "built here -- it would let a rule/mode skip the hard gate, contradicting "
                    "this spec's safety invariant); a richer settings-hierarchy precedence UI "
                    "beyond `/permissions`'s flat listing.",
    ),
    # #EXT-048-REQ-5 End
    ProductParityRow(
        id=18, feature="External-tool extensibility protocol (MCP client)",
        state="missing",
        current_state="None -- no MCP client exists.",
        next_lever="Implement an MCP client as execution-plane adapters: each server tool "
                    "wrapped as a gated Jaros tool (two-plane preserved).",
    ),
    # #EXT-050-REQ-5 Start
    ProductParityRow(
        id=19, feature="Subagent authoring surface",
        state="works",
        current_state="EXT-050: `.jcode/agents/<name>.md` (project) and `~/.jcode/agents/"
                       "<name>.md` (user, project wins on a name collision) register a "
                       "delegatable subagent -- `harness/subagents.py` discovers + parses "
                       "optional frontmatter (`description`/`tools`/`model`) + a system-prompt "
                       "body, never raising on a missing dir or a malformed file. "
                       "`JcodeCli._run_subagent` composes the body with a delegated task and "
                       "routes it through the SAME plain-language chain (`_route_plain`) a typed "
                       "non-slash request already uses -- no second reasoning mechanism -- "
                       "reachable via `/subagent <name> :: <task>` or a deterministic "
                       "\"delegate to <name> subagent: <task>\" phrasing (only fires when <name> "
                       "is actually registered). A subagent's `tools:` allowlist is enforced as a "
                       "new `tool_allowlist` at `harness.coding_loop.Runtime.apply` -- the same "
                       "gate seam EXT-047/EXT-048 use -- consulted ONLY AFTER the hard gate has "
                       "already accepted the Decision, so it can only NARROW what the hard gates "
                       "permit, never widen past them (proven by an explicit test: an "
                       "allowlisted-but-denylisted `shell.exec` command is still refused by the "
                       "hard gate). `/agents` additively lists discovered subagents alongside the "
                       "existing built-in Python fleet; no `.jcode/agents/` anywhere is a "
                       "byte-identical no-op.",
        next_lever="Narrow the tool allowlist into `/agent`'s/`/fix`'s own internally-constructed "
                    "Runtimes (mirrors EXT-049 row #20's identical residual for its checkpoint "
                    "ring); a \"model-invocable when relevant\" auto-suggestion mode beyond an "
                    "explicit `/subagent`/\"delegate to X\" phrasing; genuinely rewiring to a "
                    "different SERVED Jetson-fitting model per subagent (EXT-021's job -- "
                    "`model:` here only relabels the request to the same local endpoint).",
    ),
    # #EXT-050-REQ-5 End
    # #EXT-049-REQ-4 Start
    ProductParityRow(
        id=20, feature="Fine-grained checkpoint / rewind",
        state="works",
        current_state="A bounded per-edit checkpoint ring (`harness/checkpoint_ring.py`) is "
                       "captured at the existing `Runtime.apply` hash-chain seam (EXT-047/EXT-048's "
                       "seam) for every accepted write/edit Decision; `/checkpoints` lists it and "
                       "`/rewind <n|id>` restores prior content THROUGH a real `code.write_file` "
                       "Decision (gated, root-jailed, hash-chain-logged) -- never a raw file write. "
                       "`/undo` (EXT-009) is unchanged. Deferred: the ring is wired only into the "
                       "CLI's primary Runtime, not every internal `Runtime()` construction site, so "
                       "/agent's own edits aren't yet ring-tracked; no delete-file Decision type, so "
                       "a file's CREATION can't be fully undone; conversation-level rewind is out "
                       "of scope (code checkpoints only, matching /undo).",
        next_lever="Wire the ring into /agent's internal Runtime construction sites for full-run "
                    "per-edit granularity; a delete-file Decision type for true un-create.",
    ),
    # #EXT-049-REQ-4 End
    ProductParityRow(
        id=21, feature="Interrupt + steer mid-run",
        state="missing",
        current_state="Ctrl-C crash-safety guards exist; no graceful interrupt-and-steer loop.",
        next_lever="Cooperative cancel points between plan steps (clerk checks an interrupt "
                    "flag; partial state preserved via checkpoints).",
    ),
    ProductParityRow(
        id=22, feature="Context management for long sessions",
        state="partial",
        current_state="Compaction was deferred earlier (bounded flows didn't need it); "
                       "long-horizon runs now do; no `@file` references or `/compact`.",
        next_lever="Deterministic compactor (summarize decided/verified state into the spec -- "
                    "jarify IS the compaction target); `@path` expansion in the REPL.",
    ),
    ProductParityRow(
        id=23, feature="Background runs surface",
        state="partial",
        current_state="Runner/daemon infra exists internally (run_forever, experiment chain); "
                       "not exposed as a product surface (`--bg`/attach/logs/stop).",
        next_lever="`jcode --bg` submits through the existing inbox; `jcode logs/attach/stop "
                    "<id>` read the Jaros log.",
    ),
    # #EXT-045-REQ-3 Start
    ProductParityRow(
        id=24, feature="Terminal UX polish",
        state="works",
        current_state="EXT-045: tool calls now STREAM a concise `-> call` / `OK result` line to "
                       "stdout as they happen, from the same seam that already logs each accepted "
                       "Decision to the hash-chain (`harness.coding_loop.Runtime`'s new `on_event` "
                       "hook) -- on by default on a live terminal, always suppressed under "
                       "`--output-format json` (EXT-043) or a non-TTY stdout unless "
                       "`JCODE_STREAM_EVENTS=1` forces it, and a plain run with none of that stays "
                       "byte-identical. A `statusline()` function renders `model · class · $0 · "
                       "latency` from CURRENT state (active model, last routed action, last "
                       "handle() turn's measured latency); `/statusline [on|off]` toggles a "
                       "persistent line the REPL prints above every prompt. `/help` now documents "
                       "both. Progress display beyond the per-tool line (a live spinner/elapsed "
                       "counter during a single long tool call), `/export`, tab-completion, and "
                       "themes remain undelivered -- kept honestly `partial`, not inflated to "
                       "`works`.",
        next_lever="A live in-flight spinner/elapsed counter for a single long-running tool call "
                    "(today's line only appears at call-start and at completion); `/export` "
                    "(dump the session transcript to a file); tab-completion for slash commands; "
                    "theme/color configuration.",
    ),
    # #EXT-045-REQ-3 End
    ProductParityRow(
        id=25, feature="Install + health story",
        state="partial",
        current_state="`serve.sh`/`.ps1` + `jcode.sh`/`.ps1` exist (repo-local); no packaging, "
                       "no `/doctor`.",
        next_lever="`pipx install jaros-code` packaging; `/doctor` = deterministic checks "
                    "(Jetson reachable, model served, Docker, git).",
    ),
    ProductParityRow(
        id=26, feature="Multimodal input (images)",
        state="missing",
        current_state="None; Gemma e2b/e4b are vision-capable on the Jetson (VLA demos) -- "
                       "genuinely reachable.",
        next_lever="Probe: image -> e4b vision -> structured UI description -> existing build "
                    "pipeline.",
    ),
    ProductParityRow(
        id=27, feature="Deliberately deferred surfaces (honest scope)",
        state="missing",
        current_state="IDE extensions, desktop app, web/cloud sessions, Slack/GitHub-Actions "
                       "integrations, remote control -- out of scope for the CLI-parity pursuit "
                       "FOR NOW; recorded so the scope is stated, not silent.",
        next_lever="Revisit after CLI-product parity; none block the terminal product.",
    ),
]


def score(rows: "Iterable[ProductParityRow] | None" = None) -> dict:
    """Aggregate the checklist into an honest parity percentage + a ranked attack list.

    Never raises: a missing/empty/malformed `rows` degrades to a zero-row, 0% result rather than
    an exception (observability must never break the thing it observes -- EXT-040 precedent).
    """
    try:
        rows = list(rows) if rows is not None else list(PARITY_ROWS)
    except Exception:
        rows = []

    n_works = n_partial = n_missing = 0
    weighted_total = 0.0
    attack_list = []
    for row in rows:
        try:
            state = getattr(row, "state", "missing")
            weight = _STATE_WEIGHT.get(state, 0.0)
            weighted_total += weight
            if state == "works":
                n_works += 1
            elif state == "partial":
                n_partial += 1
                attack_list.append(row)
            else:
                n_missing += 1
                attack_list.append(row)
        except Exception:
            continue

    n_total = len(rows)
    pct = round((weighted_total / n_total) * 100, 1) if n_total else 0.0

    return {
        "pct": pct,
        "n_total": n_total,
        "n_works": n_works,
        "n_partial": n_partial,
        "n_missing": n_missing,
        # Ranked attack list: missing rows before partial rows (zero-coverage gaps are the
        # highest-leverage target), and within each bucket GAP-MAP's own stated row order (the
        # table is already roughly impact-ordered -- sessions/headless/memory first).
        "attack_list": sorted(
            attack_list,
            key=lambda r: (0 if getattr(r, "state", "missing") == "missing" else 1,
                           getattr(r, "id", 0)),
        ),
    }


def render(rows: "Iterable[ProductParityRow] | None" = None) -> str:
    """Render a readable table + summary for the `/parity` CLI command. Never raises."""
    try:
        rows = list(rows) if rows is not None else list(PARITY_ROWS)
    except Exception:
        rows = []

    try:
        lines = [
            f"Product-Parity Checklist (last synced {LAST_SYNCED}, source: {GAP_MAP_SOURCE})",
            f"{'#':>3}  {'state':<8} feature",
            "-" * 60,
        ]
        for row in sorted(rows, key=lambda r: getattr(r, "id", 0)):
            rid = getattr(row, "id", "?")
            state = getattr(row, "state", "missing")
            feature = getattr(row, "feature", "(unknown)")
            current = getattr(row, "current_state", "")
            lines.append(f"{rid:>3}  {state:<8} {feature}")
            if current:
                lines.append(f"       -> {current}")

        result = score(rows)
        lines.append("-" * 60)
        lines.append(
            f"aggregate parity: {result['pct']}%  "
            f"(works={result['n_works']} partial={result['n_partial']} "
            f"missing={result['n_missing']} / {result['n_total']} rows)"
        )
        if result["attack_list"]:
            lines.append("next attack (ranked, missing-first):")
            for row in result["attack_list"][:5]:
                lines.append(
                    f"  #{getattr(row, 'id', '?')} {getattr(row, 'feature', '(unknown)')} "
                    f"[{getattr(row, 'state', 'missing')}] -> {getattr(row, 'next_lever', '')}"
                )
        return "\n".join(lines)
    except Exception:
        return "Product-Parity Checklist: (render failed -- see harness/product_parity.py)"
# #EXT-041-REQ-1 End
