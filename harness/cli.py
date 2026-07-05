"""Claude-Code-like interactive CLI (EXT-004).

A slash-command REPL over the Jaros runtime, modelled on Claude Code's terminal UX.
It is also how several single-purpose agents/tools get WIRED into real use: /find
drives the navigator agent -> fs.grep, /run drives the commander agent -> shell.exec
(safety-gated), /grep /ls /read /symbols drive the read tools. Every command routes a
Decision through the same gate + executor as everything else — the CLI never bypasses
the two planes.

Terminal UX (EXT-045): on a live terminal, tool calls stream a concise "→ call" / "✓ result"
line to stdout AS THEY HAPPEN (from the same seam that logs each Decision to the hash-chain) --
disabled automatically when stdout isn't a TTY or under --output-format json, and always
overridable via JCODE_STREAM_EVENTS=1|0. /statusline toggles a persistent one-line
"model · class · $0 · latency" status above every prompt.

Commands (Claude-Code-style):
  /help                         list commands
  /status                       model + latest pass rate + census
  /statusline [on|off]          toggle a persistent "model · class · $0 · latency" status line
                                 above every prompt (EXT-045); shows the CURRENT line either way
  /parity                       Product-Parity Checklist: CC-product-surface parity score (EXT-041)
  /doctor                        deterministic health check: Jetson/LLM endpoint + model served,
                                 git/docker/python presence, .jaros-data writability, config
                                 sanity (also: jcode doctor / jcode --doctor, headless, EXT-053)
  /agents  /tools               the live fleet/catalog (/agents also lists any user-authored
                                 subagents discovered under .jcode/agents/<name>.md, EXT-050)
  /report                       latest convergence report
  /trend                        pass-rate history (full runs)
  /find <term>                  navigator agent -> fs.grep (locate code)
  /grep <pattern> [path]        fs.grep tool
  /ls [path]                    fs.list tool
  /read <file>                  fs.read tool
  /symbols <file>               py.symbols tool
  /files <pattern> [path]       fs.find tool (locate files)
  /patch <file> :: <old> :: <new>   code.apply_patch tool (surgical edit)
  /run <task>                   commander agent -> shell.exec (gated)
  /fix <file> :: <instr> :: <testcmd>   run the edit->test->judge loop
  /fixrepo <instr> :: <testcmd> [:: <testfile>]   multi-file: locate the faulty file & fix it
  /plan <request>               multi-step: planner -> deterministic find/read/fix/run flow
  /map [path]                   ranked repo map (top-level symbols per file, Aider-style)
  /rename <old> <new>           test-gated rename refactor (reverts if the suite goes red)
  /move <symbol> <from> <to>    test-gated move-symbol refactor (re-exports; reverts on red)
  /usages <symbol>              AST find-usages across the repo (precise; ignores strings/comments)
  /defn <symbol>                go-to-definition: the def/class site(s) of a symbol
  /callers <symbol>             call hierarchy: functions that CALL a symbol (call sites only)
  /about <symbol>               one-view symbol summary (definition + callers + refs + dead?)
  /build <func> <intent>        behavioral solve: Gherkin(+comprehension)->self-tests->code (EXT-012 system)
  /buildsystem <sentence>        sentence-to-system: plan->build->assemble->acceptance (EXT-036)
  /modifysystem [<dir> ::] <sentence>   modify an existing system, regression-gated (EXT-036)
  /agent <request>              agentic loop: plan -> act -> observe -> replan over the tools (EXT-009)
  /diff                         show what the last /agent run changed vs its checkpoint
  /undo                         revert the last /agent run (restore the pre-run checkpoint)
  /checkpoints                  list the fine-grained per-edit checkpoint ring (EXT-049)
  /rewind <n|id>                restore the workspace N steps back (or to a checkpoint id);
                                 no arg lists the ring — finer-grained superset of /undo
  /gitstatus                    git.status tool: working-tree status (EXT-037 host toolbelt)
  /gitlog [n]                   git.log tool: recent commit history (default ~10)
  /gitdiff [file]               git.diff tool: working diff, optionally scoped to one file
  /gitbranch                    git.branch tool: list branches (current marked with '*')
  /commit <message>             git.commit tool: stage + commit tracked changes (secret-guarded)
  /explain <function|file>      plain-English summary of what code does
  /remember <note>              save a convention/learning to project memory (.jcode/memory.md);
                                 also captures it as a durable per-repo fact for memory-agent recall (EXT-036)
  /memory                       show the project memory + the per-repo long-term fact store
  /init                         write a starter JCODE.md from repo comprehension (EXT-042); auto-loaded
                                 into the orchestrator/planner context every session (project + user levels)
  /locate                       run tests + pinpoint the fault to file:line:function (deepest first)
  /deadcode [path]              public symbols referenced nowhere (dead-code candidates)
  /new                          start a fresh conversational session (EXT-036)
  /resume <id>                  resume a prior session by id (also: --resume <id> on the command line)
  /sessions                     list recent saved sessions
  /name <name>                  give the current session a display name (EXT-044; also: --name <name>
                                 on the one-shot command line)
  /fork [<id|name>]             branch a session into a NEW id (copies its transcript, leaves the
                                 original unchanged); no arg forks the current session (also:
                                 --fork [<id|name>] on the command line, EXT-044)
                                 (command line only, EXT-044): -c/--continue resumes the most recent
                                 session; -r <id|name> resumes a specific one by id OR by its /name
  /compact                      shrink the CURRENT session's transcript: folds older turns into a
                                 running summary via the SAME condense()/_summarize_turns()
                                 mechanism REQ-12/15 already built, but durably persists the result
                                 (an already-short session is an honest no-op, EXT-051)
  @path  @dir/                  in ANY plain request (typed or a skill template), inlines that
                                 file's content (bounded, truncation noted) or a bounded directory
                                 listing, read through the existing gated fs.read/fs.list tools; a
                                 missing/unreadable ref degrades to an honest "(not found)" note,
                                 never a crash (EXT-051)
  /task <text>                  add a TODO task for this repo (EXT-036)
  /tasks                        list tasks (id + status)
  /task done <id>                mark a task done
  /task doing <id>               mark a task in progress
  /skills                        list custom skills (drop a .jcode/skills/<name>.md file to add
                                 a new /name command; args substitute into the template via
                                 $ARGUMENTS/$1/$2..., which then routes through the orchestrator
                                 like any plain request; a built-in command always wins, EXT-046)
  /hooks                         list configured lifecycle hooks (drop a .jcode/hooks.json file
                                 mapping PreToolUse/PostToolUse/SessionStart/Stop to shell
                                 commands, run through the SAME gated shell.exec path every tool
                                 call uses; a PreToolUse hook exiting non-zero BLOCKS the tool
                                 call it gates, EXT-047)
  /mode [plan|default|acceptEdits]  cycle or set the REPL mode (EXT-048): plan = propose only, no
                                 side effects (writes/shell are withheld and described only);
                                 default = today's behavior; acceptEdits = auto-approve an
                                 ask-resolving WRITE Decision that already passed the hard gate
  /permissions                  list configured permission rules (drop a .jcode/permissions.json
                                 file with {tool, arg, action} entries, action = allow|ask|deny,
                                 first match wins; the built-in hard safety gates ALWAYS run
                                 first — a user allow rule can never widen what they refuse, EXT-048)
  /subagent <name> :: <task>    delegate to a user-authored subagent (drop a
                                 .jcode/agents/<name>.md file with description/tools/model
                                 frontmatter + a system-prompt body to add one; also reachable via
                                 plain "delegate to <name> subagent: <task>"; its tools: allowlist
                                 can only NARROW what the hard safety gates already permit, never
                                 widen past them, EXT-050)
  /experiment <hyp> :: <cmd>    define an experiment for this repo (EXT-036)
  /experiments                  list experiments (id + status + last result)
  /experiment run <id>          actually run the experiment (real subprocess, never faked)
  /jobs                          list background jobs (id/request/status/started/ended, EXT-052)
  /logs <id>                     print a background job's recorded output (EXT-052)
  /stop <id>                     cancel a running background job (kills its recorded pid/tree
                                 only, never by name, EXT-052)
  (interactive mode) genuinely ambiguous plain requests get ONE clarifying question first (REQ-8)
  /clear  /quit

  Command-line only (EXT-052): background runs surface --
    jcode --bg "<request>"       submit to run DETACHED; returns a job id immediately
    jcode jobs  (alias: jcode bg list)   list background jobs
    jcode logs <id>              print that job's output
    jcode attach <id>            stream a running job's output live (Ctrl-C detaches; the job
                                 keeps running -- it does NOT stop it)
    jcode stop <id>              cancel a running background job
"""

from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# #EXT-036-REQ-12 Start
def _augment_with_history(text: str, history: "list[dict] | None", project_md: str = "",
                           memory: "list[str] | None" = None, jcode_md: str = "") -> str:
    """Fold a BOUNDED recent transcript into `text` as conversation context (REQ-12), preceded
    by an optional ``JCODE.md`` preamble (EXT-042 REQ-2, already labeled by
    ``harness.jcode_md.load_jcode_md``), an optional JAROS.md ``PROJECT INSTRUCTIONS:`` preamble
    (REQ-17, EXT-036 TASK-2), and an optional memory-agent-selected ``RELEVANT MEMORY:`` block
    (REQ-16, EXT-036 TASK-3). Order is JCODE.md -> PROJECT INSTRUCTIONS -> RELEVANT MEMORY ->
    conversation history -> the request. Absent history AND absent project_md/jcode_md AND empty
    memory leaves `text` byte-identical — a fresh session / repo with no JAROS.md/JCODE.md / no
    recalled facts behaves exactly like the old stateless routing (a graceful no-op)."""
    # #EXT-042-REQ-2 Start
    parts: list[str] = []
    if jcode_md:
        parts.append(jcode_md)
    # #EXT-042-REQ-2 End
    # #EXT-036-REQ-17 Start
    if project_md:
        parts.append(f"PROJECT INSTRUCTIONS:\n{project_md}")
    # #EXT-036-REQ-17 End
    # #EXT-036-REQ-16 Start
    if memory:
        mem_block = "\n".join(f"- {f}" for f in memory)
        parts.append(f"RELEVANT MEMORY:\n{mem_block}")
    # #EXT-036-REQ-16 End
    if history:
        convo = "\n".join(f"{h.get('role', 'user')}: {h.get('text', '')}" for h in history)
        parts.append(f"(recent conversation)\n{convo}")
    if not parts:
        return text
    return "\n\n".join(parts) + f"\n\n(current request) {text}"


def _record_turn(cli, user_text: str, assistant_text: str) -> None:
    """Append the turn to the active session + persist it (best-effort — a missing/broken
    session or a save failure must NEVER crash handle(), REQ-12)."""
    try:
        session = cli.session
        session.append("user", user_text)
        session.append("assistant", assistant_text)
    except Exception:
        return
    try:
        from harness.session import save_session
        save_session(session)
    except Exception:
        pass
# #EXT-036-REQ-12 End


# #EXT-036-REQ-13 Start
# TASK-18: live CLI wiring for the offline hard-tier escalation core (harness.system_builder.
# build_system_escalating). "Configured" = the model registry has MEASURED coverage of the
# complex-system-build-specialist class (today: qwen2.5-coder-7b) AND a model-manager URL is
# available to swap the Jetson's served model. Absent either, /buildsystem behaves exactly as
# before (plain build_system, no swap_fn ever constructed) -- no regression when unconfigured.
_BUILDSYSTEM_SPECIALIST_CLASS = "complex-system-build-specialist"


def _buildsystem_escalation_config() -> "tuple[str, str, str] | None":
    """Return ``(manager_url, fallback_model_id, primary_model_id)`` when hard-tier escalation
    for ``/buildsystem`` is CONFIGURED, else ``None``. Never raises — any registry-load failure
    or an empty (honest, evidence-gated) ``lookup_by_class`` result means "not configured", so
    the caller falls back to plain ``build_system`` rather than escalating on a guess."""
    try:
        from harness.model_registry import load_registry
        registry = load_registry()
        candidates = registry.lookup_by_class(_BUILDSYSTEM_SPECIALIST_CLASS)
        if not candidates:
            return None
        manager_url = os.environ.get("JCODE_MODEL_MANAGER_URL", "http://192.168.1.183:8001")
        return manager_url, candidates[0], registry.default_model()
    except Exception:
        return None
# #EXT-036-REQ-13 End


# #EXT-037-REQ-5 Start
def _buildsystem_finalize_config() -> dict:
    """REQ-5 finalize-step gate/flag for ``/buildsystem`` -- env-var driven, sensible
    Claude-Code-like defaults: git-commit ON (versioning the shipped system is the
    safe, expected default), venv ``"auto"`` (a venv is created only when the shipped
    system actually declares a dependency), auto-run is ALWAYS off regardless of this
    config (``finalize_system`` never executes the built code). Never raises -- a bad
    env value falls back to the default rather than erroring.

    Set ``JCODE_FINALIZE_SYSTEM=0`` (or ``false``/``off``/``no``) to disable the whole
    finalize step; ``JCODE_FINALIZE_GIT=0`` to skip only the git half;
    ``JCODE_FINALIZE_VENV=always|off`` to override the venv default.
    """
    def _off(name: str, default: str = "1") -> bool:
        return os.environ.get(name, default).strip().lower() in ("0", "false", "off", "no")

    enabled = not _off("JCODE_FINALIZE_SYSTEM")
    git_on = not _off("JCODE_FINALIZE_GIT")
    venv_mode = os.environ.get("JCODE_FINALIZE_VENV", "auto").strip().lower()
    if venv_mode not in ("auto", "always", "off"):
        venv_mode = "auto"
    return {"enabled": enabled, "git": git_on, "venv": venv_mode}
# #EXT-037-REQ-5 End


class JcodeCli:
    """Slash-command dispatcher; each handler returns text to print."""

    def __init__(self, session_id: str | None = None, stream: bool = False,
                 # #EXT-048-REQ-3 Start
                 interactive: bool = False) -> None:
                 # #EXT-048-REQ-3 End
        # #EXT-014-REQ-1 Start
        # Primary default is llama.cpp + Gemma 4 2B (e2b) via JCODE_LLM_BACKEND="llamacpp".
        # Legacy Ollama path (gemma2:2b) only activates when JCODE_LLM_BACKEND=ollama explicitly.
        # Do NOT set JAROS_LLM_PROVIDER or OLLAMA_MODEL here — build_llm() already selects
        # the correct backend from JCODE_LLM_BACKEND (default "llamacpp").
        from harness.coding_loop import Runtime, build_llm, _load_agent, _active_model_label
        # #EXT-014-REQ-1 End
        from jaros.core import create_decision
        self._mk = create_decision
        # #EXT-045-REQ-1 Start
        # Streaming tool events (EXT-045): OFF by default (byte-identical to before this spec) --
        # a caller opts in (`stream=True`, wired from `repl()`/`_run_one_shot()` per
        # `harness.tool_stream.should_stream`). When on, every Decision this Runtime applies
        # narrates a concise call/result line to stdout as it happens.
        self.stream = bool(stream)
        _on_event = None
        if self.stream:
            from harness.tool_stream import make_printer
            _on_event = make_printer()
        # #EXT-047-REQ-1 Start
        # User-configurable lifecycle hooks (EXT-047): discovered ONCE per CLI instance (mirrors
        # the self.jcode_md/self.skills caching precedent below) -- a missing/unreadable
        # .jcode/hooks.json (either tier) or any discovery failure falls back to {} rather than
        # blocking construction, which keeps this Runtime's hook-firing a complete no-op.
        try:
            from harness.hooks import load_hooks
            self.hooks_config = load_hooks(".")
        except Exception:
            self.hooks_config = {}
        # #EXT-047-REQ-1 End
        # #EXT-048-REQ-1 Start
        # User-configurable permission rules (EXT-048): discovered ONCE per CLI instance, mirroring
        # the hooks_config precedent immediately above -- a missing/unreadable
        # .jcode/permissions.json (either tier) or any discovery failure falls back to `[]` rather
        # than blocking construction, keeping the Runtime's permission enforcement a complete
        # no-op. `self.mode` (EXT-048/REQ-4) is the REPL's `/mode` state, always starting at
        # `DEFAULT_MODE` ("default") -- byte-identical to pre-EXT-048 behavior until `/mode` is
        # used. `self._interactive` records whether THIS instance may prompt via input() (only
        # `repl()` passes `interactive=True`) -- a headless/one-shot run never blocks on a prompt.
        try:
            from harness.permissions import load_permission_rules
            self.permission_rules = load_permission_rules(".")
        except Exception:
            self.permission_rules = []
        from harness.permissions import DEFAULT_MODE
        self.mode = DEFAULT_MODE
        self._interactive = bool(interactive)
        # #EXT-048-REQ-1 End
        # #EXT-049-REQ-3 Start
        # Fine-grained checkpoint ring (EXT-049): wired ONLY into this primary Runtime, so direct
        # edit commands routed through it (e.g. /patch) populate the ring; /rewind and
        # /checkpoints read it back (see cmd_rewind/cmd_checkpoints below).
        from harness.checkpoint_ring import CheckpointRing
        self._checkpoint_ring = CheckpointRing()
        # #EXT-049-REQ-3 End
        self.rt = Runtime(
            on_event=_on_event, hooks_config=self.hooks_config,
            # #EXT-048-REQ-3 Start
            mode=self.mode, permission_rules=self.permission_rules,
            ask_callback=(self._ask_permission if self._interactive else None),
            # #EXT-048-REQ-3 End
            # #EXT-049-REQ-3 Start
            checkpoint_ring=self._checkpoint_ring,
            # #EXT-049-REQ-3 End
        )
        # #EXT-045-REQ-1 End
        self.llm = build_llm()
        self._load_agent = _load_agent
        # #EXT-014-REQ-1 Start
        # Report the model that is ACTUALLY serving inference (Tenet 3 — honest).
        self.model = _active_model_label()
        # #EXT-014-REQ-1 End
        # #EXT-036-REQ-12 Start
        # Conversational session (REQ-12 backbone): resume a prior transcript when a
        # session_id is given and found; otherwise start fresh (keeping the requested
        # id, if any, so a later /resume of that same id finds it once persisted).
        from harness.session import Session, load_session
        self.session = (load_session(session_id) if session_id else None) or Session(id=session_id)
        # #EXT-036-REQ-12 End
        # #EXT-036-REQ-17 Start
        # Per-repo JAROS.md project instructions (REQ-17): loaded ONCE per CLI instance (not
        # per keystroke) and cached here; injected into every plain-language turn via
        # _augment_with_history. Absent file -> "" -> a graceful no-op (see that function).
        from harness.project_md import load_project_md
        self.project_md = load_project_md(".")
        # #EXT-036-REQ-17 End
        # #EXT-042-REQ-2 Start
        # Per-repo + per-user JCODE.md project instructions (EXT-042 REQ-2): loaded ONCE per CLI
        # instance (mirrors the REQ-17 JAROS.md cache above) and injected into every
        # plain-language turn via _augment_with_history. Absent JCODE.md (both tiers) -> "" ->
        # a graceful no-op, exactly like the JAROS.md cache.
        from harness.jcode_md import load_jcode_md
        self.jcode_md = load_jcode_md(".")
        # #EXT-042-REQ-2 End
        # #EXT-036-REQ-16 Start
        # Per-repo long-term fact store (REQ-16): loaded ONCE per CLI instance (mirrors the
        # REQ-17 JAROS.md cache), NOT injected wholesale — _recall_memory asks the narrow
        # memory-agent to select the precise few facts relevant to each turn.
        from harness.repo_memory import load_facts
        self.repo_facts = load_facts(".")
        # #EXT-036-REQ-16 End
        # #EXT-036-REQ-14 Start
        # Last system built via /buildsystem (REQ-14): /modifysystem defaults to it when no
        # explicit dir is given. None until a /buildsystem call succeeds this session.
        self._last_built_dir: "Path | None" = None
        # #EXT-036-REQ-14 End
        # #EXT-045-REQ-2 Start
        # Statusline state (EXT-045): the last routed action ("problem class") and the wall-clock
        # latency of the last handle() turn, both updated at the end of every handle() call.
        # None until the first turn -- statusline() renders "-" for either field until then.
        self._last_action: "str | None" = None
        self._last_latency_s: "float | None" = None
        self._show_statusline = False  # toggled by /statusline; REPL prints it when True
        # #EXT-045-REQ-2 End
        # #EXT-046-REQ-1 Start
        # Custom skills (EXT-046): discovered ONCE per CLI instance (mirrors the self.jcode_md/
        # self.project_md caching precedent) -- a missing/unreadable .jcode/skills/ (either
        # tier) or any discovery failure falls back to {} rather than blocking construction.
        try:
            from harness.skills import discover_skills
            self.skills = discover_skills(".")
        except Exception:
            self.skills = {}
        # #EXT-046-REQ-1 End
        # #EXT-050-REQ-1 Start
        # User-authorable subagents (EXT-050): discovered ONCE per CLI instance (mirrors the
        # self.skills caching precedent immediately above) -- a missing/unreadable
        # .jcode/agents/ (either tier) or any discovery failure falls back to {} rather than
        # blocking construction.
        try:
            from harness.subagents import discover_subagents
            self.subagents = discover_subagents(".")
        except Exception:
            self.subagents = {}
        # #EXT-050-REQ-1 End
        # #EXT-047-REQ-3 Start
        # SessionStart lifecycle hooks (EXT-047): fire ONCE, here at construction -- a no-op
        # when no hooks are configured (self.hooks_config is {} in that case). `_stop_fired`
        # guards `on_stop()` (below) so a Stop hook can never double-fire for one session even
        # if a caller invokes it more than once (e.g. an interrupted REPL loop).
        self._stop_fired = False
        self._session_start_outcomes: "list" = []
        if self.hooks_config:
            try:
                from harness import hooks as _hooks
                self._session_start_outcomes = _hooks.fire_event(
                    "SessionStart", self.hooks_config, cwd=os.path.abspath("."))
            except Exception:
                self._session_start_outcomes = []
        # #EXT-047-REQ-3 End

    # #EXT-047-REQ-3 Start
    def on_stop(self) -> None:
        """Fire configured ``Stop`` lifecycle hooks (EXT-047) once, at session end -- called from
        `repl()` (on `/quit`/EOF/interrupt) and `_run_one_shot()` (after its single turn
        completes). A no-op when no hooks are configured, and idempotent (fires at most once per
        `JcodeCli` instance). Never raises."""
        if self._stop_fired or not getattr(self, "hooks_config", None):
            return
        self._stop_fired = True
        try:
            from harness import hooks as _hooks
            self._stop_outcomes = _hooks.fire_event(
                "Stop", self.hooks_config, cwd=os.path.abspath("."))
        except Exception:
            pass
    # #EXT-047-REQ-3 End

    # #EXT-048-REQ-3 Start
    def _ask_permission(self, tool_name: str, arg: "str | None") -> bool:
        """Interactive y/n prompt for an `"ask"`-resolving permission rule (EXT-048) -- wired as
        the `Runtime`'s `ask_callback` ONLY when this CLI was constructed with `interactive=True`
        (`repl()`). Any doubt (EOF, a declined/empty answer, an unreadable prompt) -> `False`
        (deny) -- never raises, and never approves by default."""
        try:
            suffix = f" ({arg})" if arg else ""
            answer = input(
                f"\033[33mpermission required for {tool_name}{suffix} -- allow? [y/N] \033[0m"
            ).strip().lower()
            return answer in ("y", "yes")
        except Exception:
            return False
    # #EXT-048-REQ-3 End

    # -- helpers -----------------------------------------------------------
    def _tool(self, dtype: str, payload: dict):
        return self.rt.apply(self._mk(id=f"cli-{uuid.uuid4().hex}", source="cli",
                                      type=dtype, payload=payload))

    # #EXT-051-REQ-1 Start
    def _at_ref_read(self, path: str) -> "tuple[str | None, bool]":
        """Adapter for ``@path`` expansion (EXT-051): reads a file through the EXISTING gated
        ``fs.read`` tool -- the SAME seam ``cmd_read``/``/read`` already uses -- rather than a raw
        ``open()``. Returns ``(content, truncated)``; ``(None, False)`` when the path isn't a
        readable file or the gated call raises for any reason (never propagates)."""
        try:
            out = self._tool("fs.read", {"path": path})
        except Exception:
            return None, False
        if not isinstance(out, dict) or out.get("error"):
            return None, False
        return out.get("content", ""), bool(out.get("truncated"))

    def _at_ref_list(self, path: str) -> "tuple[list[str] | None, bool]":
        """Adapter for ``@dir/`` expansion (EXT-051): lists a directory through the EXISTING gated
        ``fs.list`` tool -- the SAME seam ``cmd_ls``/``/ls`` already uses -- rather than a raw
        ``os.listdir()``. Returns ``(entry_lines, truncated)``; ``(None, False)`` when the path
        isn't a readable directory or the gated call raises for any reason (never propagates).
        Bounding the entry COUNT is `harness.atrefs.expand_at_refs`'s job (``max_dir_entries``),
        so this adapter always reports ``truncated=False`` and the full entry list."""
        try:
            out = self._tool("fs.list", {"path": path.rstrip("/\\") or "."})
        except Exception:
            return None, False
        if not isinstance(out, dict) or out.get("error"):
            return None, False
        entries = out.get("entries", [])
        lines = [f"{e.get('type', 'file'):<4} {e.get('name', '')}" for e in entries]
        return lines, False
    # #EXT-051-REQ-1 End

    # #EXT-042-REQ-5 Start
    def _write_runtime(self):
        """A root-anchored `Runtime` for host-project file-write Decisions (EXT-042 REQ-5) --
        mirrors `_git_tool`'s root-anchored-Runtime construction (EXT-037 REQ-5) so every
        product-surface write goes through the same gate + EXT-037 path-jail + hash-chain log,
        plus this instance's hooks/permission/mode wiring. Returns `None` on any construction
        failure -- callers degrade to their own safe (pre-Decision) fallback rather than crash."""
        try:
            from harness.coding_loop import Runtime
            _on_event = None
            if getattr(self, "stream", False):
                from harness.tool_stream import make_printer
                _on_event = make_printer()
            return Runtime(
                root=os.path.abspath("."), on_event=_on_event,
                hooks_config=getattr(self, "hooks_config", None),
                mode=getattr(self, "mode", "default"),
                permission_rules=getattr(self, "permission_rules", None),
                ask_callback=(self._ask_permission if getattr(self, "_interactive", False) else None),
            )
        except Exception:
            return None
    # #EXT-042-REQ-5 End

    # #EXT-050-REQ-3 Start
    def _subagent_runtime(self, tool_allowlist: "list[str] | None"):
        """A scoped `Runtime` for a subagent delegation (EXT-050): carries the SAME
        hooks/mode/permission_rules/ask_callback/checkpoint_ring wiring as the CLI's primary
        `self.rt`, narrowed by `tool_allowlist` (the subagent's `tools:` frontmatter). This
        narrowing is enforced at `Runtime.apply` STRICTLY AFTER the hard gate has already
        accepted a Decision (see `harness.coding_loop.Runtime.apply`) -- it can only reject a
        tool the subagent didn't list, never permit one the hard gates already refuse. Returns
        `None` on any construction failure -- `_run_subagent` then falls back to the CLI's
        primary (unnarrowed) `self.rt` rather than crash, exactly like `_write_runtime`."""
        try:
            from harness.coding_loop import Runtime
            _on_event = None
            if getattr(self, "stream", False):
                from harness.tool_stream import make_printer
                _on_event = make_printer()
            return Runtime(
                on_event=_on_event, hooks_config=getattr(self, "hooks_config", None),
                mode=getattr(self, "mode", "default"),
                permission_rules=getattr(self, "permission_rules", None),
                ask_callback=(self._ask_permission if getattr(self, "_interactive", False) else None),
                checkpoint_ring=getattr(self, "_checkpoint_ring", None),
                tool_allowlist=tool_allowlist,
            )
        except Exception:
            return None
    # #EXT-050-REQ-3 End

    # #EXT-050-REQ-2 Start
    def _run_subagent(self, name: str, task: str) -> str:
        """Delegate `task` to a user-authored subagent (EXT-050): its markdown body becomes a
        system-prompt prefix folded into ONE plain-language request, routed through
        `_route_plain` -- the SAME deterministic-fastpath -> orchestrator chain a typed
        non-slash request already uses (no second reasoning mechanism, mirrors EXT-046's
        `_run_skill`). The subagent's `tools:` allowlist narrows `self.rt` for the DURATION of
        this delegated turn only (restored in `finally`); an optional `model:` override
        similarly narrows/relabels `self.llm` for the duration only. An unregistered name
        degrades to an honest error, never a crash."""
        subagent = getattr(self, "subagents", {}).get(name)
        if subagent is None:
            return (f"no subagent named {name!r} is registered -- try /agents to see what's "
                     "discovered (drop a .jcode/agents/<name>.md file to add one)")
        from harness.subagents import render_subagent_prompt
        augmented = render_subagent_prompt(subagent, task)
        prior_rt = self.rt
        prior_llm = self.llm
        if getattr(subagent, "tools", None):
            scoped_rt = self._subagent_runtime(list(subagent.tools))
            if scoped_rt is not None:
                self.rt = scoped_rt
        if getattr(subagent, "model", None):
            try:
                from harness.coding_loop import build_llm
                self.llm = build_llm(model=subagent.model)
            except Exception:
                self.llm = prior_llm
        try:
            out, _action_label = self._route_plain(augmented)
        finally:
            self.rt = prior_rt
            self.llm = prior_llm
        return out

    def _match_subagent_delegation(self, line: str) -> "tuple[str, str] | None":
        """Deterministic, no-model-call detection of an explicit subagent-delegation phrasing
        (EXT-050): "delegate to <name> subagent: <task>" or "use the <name> subagent to <task>"
        (case-insensitive). Returns `(name, task)` ONLY when `name` is an actual key in
        `self.subagents` -- an unrelated plain request (or one naming an unregistered name) is
        never misrouted, and returns `None`."""
        subagents = getattr(self, "subagents", {}) or {}
        if not subagents:
            return None
        import re as _re
        m = _re.search(
            r"\b(?:delegate\s+to|use(?:\s+the)?)\s+(\w+)\s+subagent\b(?:\s+to)?\s*[:\-]?\s*(.*)",
            line, _re.I)
        if not m:
            return None
        name = m.group(1)
        if name not in subagents:
            return None
        task = m.group(2).strip() or line
        return name, task
    # #EXT-050-REQ-2 End

    # -- commands ----------------------------------------------------------
    def cmd_help(self, _arg: str) -> str:
        return __doc__.split("Commands (Claude-Code-style):", 1)[1].rstrip()

    def cmd_status(self, _arg: str) -> str:
        from harness.report import build_report, census
        rep = build_report()
        c = census()
        # #EXT-014-REQ-1 Start
        # Backend label is dynamic: llamacpp (default) or ollama (legacy, explicit only).
        _backend = os.environ.get("JCODE_LLM_BACKEND", "llamacpp").strip().lower()
        _backend_label = "llamacpp, local" if _backend.startswith("llama") else "ollama, local (legacy)"
        # #EXT-014-REQ-1 End
        # #EXT-040-REQ-1 Start
        # Live observability: what is jaros-code DOING right now (activity, elapsed, stalled?).
        # Owner directive 2026-07-04 -- so "stuck vs working" is answerable at a glance.
        try:
            from harness.heartbeat import format_status, status as _hb_status
            activity_line = format_status(_hb_status()) + "\n"
        except Exception:
            activity_line = ""
        # #EXT-040-REQ-1 End
        return (f"{activity_line}"
                f"model: {self.model} ({_backend_label})\n"
                f"latest: {rep.get('headline','(no eval yet)')}\n"
                f"census: agents={c['agents']} tools={c['tools']} capabilities={c['capabilities']} "
                f"evals={c['evals']}+{c['harnessEvals']} specs={c['specs']}")

    # #EXT-045-REQ-2 Start
    def statusline(self) -> str:
        """One-line ``model · problem-class · $0 · latency`` status (EXT-045 REQ-2) computed
        from CURRENT state -- the active model, the last routed action, and the last handle()
        turn's measured latency. Never raises (delegates to harness.statusline.statusline)."""
        from harness.statusline import statusline as _statusline
        return _statusline(self.model, self._last_action, self._last_latency_s)

    def cmd_statusline(self, arg: str) -> str:
        """``/statusline [on|off]``: toggle the persistent one-line status the REPL prints
        before every prompt, and show its CURRENT value immediately either way."""
        a = arg.strip().lower()
        if a in ("on", "show"):
            self._show_statusline = True
        elif a in ("off", "hide"):
            self._show_statusline = False
        else:
            self._show_statusline = not self._show_statusline
        return f"statusline: {'on' if self._show_statusline else 'off'}\n{self.statusline()}"
    # #EXT-045-REQ-2 End

    # #EXT-041-REQ-1 Start
    def cmd_parity(self, _arg: str) -> str:
        """Product-Parity Checklist (EXT-041): CC-product-surface parity score, honest baseline
        against docs/GAP-MAP.md's "## Product-surface parity" rows (#12-27). Deterministic --
        no model call -- and never raises (mirrors /status's observability discipline)."""
        try:
            from harness.product_parity import render as _render_parity
            return _render_parity()
        except Exception:
            return "Product-Parity Checklist: (unavailable -- see harness/product_parity.py)"
    # #EXT-041-REQ-1 End

    # #EXT-053-REQ-2 Start
    def cmd_doctor(self, _arg: str) -> str:
        """`/doctor` (EXT-053): deterministic health check -- Jetson/LLM endpoint reachability +
        model served, git/docker/python presence, .jaros-data writability, config sanity. Every
        check is pure execution-plane bookkeeping (no model call); never raises (mirrors
        /status's and /parity's observability discipline)."""
        try:
            from harness.doctor import render as _render_doctor, run_doctor as _run_doctor
            return _render_doctor(_run_doctor())
        except Exception as exc:
            return f"/doctor: (unavailable -- {exc})"
    # #EXT-053-REQ-2 End

    # #EXT-052-REQ-3 Start
    def cmd_jobs(self, _arg: str) -> str:
        """``/jobs`` (EXT-052): list background jobs (id, request, status, started/ended) --
        deterministic, no model call, never raises."""
        try:
            from harness.bg_jobs import format_jobs
            return format_jobs()
        except Exception:
            return "(background jobs list unavailable)"

    def cmd_logs(self, arg: str) -> str:
        """``/logs <id>`` (EXT-052): print that job's recorded output."""
        job_id = arg.strip()
        if not job_id:
            return "usage: /logs <id>  (see /jobs for known ids)"
        try:
            from harness.bg_jobs import read_log
            return read_log(job_id)
        except Exception as exc:
            return f"(could not read logs: {exc})"
    # #EXT-052-REQ-3 End

    # #EXT-052-REQ-5 Start
    def cmd_stop(self, arg: str) -> str:
        """``/stop <id>`` (EXT-052): cancel a running background job by its recorded pid/tree
        only (never by name); an unknown id or an already-finished job is refused honestly."""
        job_id = arg.strip()
        if not job_id:
            return "usage: /stop <id>  (see /jobs for known ids)"
        try:
            from harness.bg_jobs import stop_job
            return stop_job(job_id)["message"]
        except Exception as exc:
            return f"(could not stop job {job_id}: {exc})"
    # #EXT-052-REQ-5 End

    def cmd_agents(self, _arg: str) -> str:
        d = ROOT / ".jaros-data" / "agents"
        out = "agents: " + ", ".join(sorted(p.stem for p in d.glob("*.py") if not p.name.startswith("_")))
        # #EXT-050-REQ-4 Start
        # User-authored subagents (EXT-050): additive listing appended after the existing
        # built-in Python agent fleet (unchanged above) -- a repo with no `.jcode/agents/`
        # anywhere gets an honest empty note rather than a silent gap.
        subagents = getattr(self, "subagents", {}) or {}
        if subagents:
            lines = []
            for name in sorted(subagents):
                sub = subagents[name]
                desc = sub.description.strip() if sub.description else "(no description)"
                lines.append(f"  /{name}  —  {desc}")
            out += "\nuser-authored subagents (.jcode/agents/<name>.md):" + "".join(
                "\n" + line for line in lines)
        else:
            out += ("\n(no user-authored subagents found — drop a .jcode/agents/<name>.md file "
                     "with description/tools/model frontmatter to add one)")
        # #EXT-050-REQ-4 End
        return out

    def cmd_tools(self, _arg: str) -> str:
        d = ROOT / ".jaros-data" / "tools"
        return "tools: " + ", ".join(sorted(p.stem for p in d.glob("*.py") if not p.name.startswith("_")))

    def cmd_report(self, _arg: str) -> str:
        from harness.report import write_report
        return write_report()["markdown"]

    def cmd_trend(self, _arg: str) -> str:
        """Pass-rate history (full runs) — a Claude-Code-like status view."""
        import glob
        import json
        rows = []
        for line in open(ROOT / ".jaros-data" / "artifacts" / "eval" / "history.jsonl",
                         encoding="utf-8") if (ROOT / ".jaros-data" / "artifacts" / "eval" / "history.jsonl").is_file() else []:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        fulls = [r for r in rows if r.get("total", 0) >= 10][-12:]
        if not fulls:
            return "(no full-suite runs yet)"
        out = ["pass-rate trend (suite labeled — runs are not all the same benchmark):"]
        for r in fulls:
            pct = round(r["passRate"] * 100)
            bar = "#" * (pct // 5) + "." * (20 - pct // 5)
            out.append(f"  {r['timestamp'][:16]} {str(r.get('suite', '?'))[:11]:11} "
                       f"[{bar}] {r['solved']:>2}/{r['total']:<3} {pct}%")
        # Breadth (census) trend — MOVES even when pass@1 is pinned at the 2B ceiling, so it's the
        # honest day-to-day progress signal. Current counts + growth since the first recorded run.
        cens = [r["census"] for r in fulls if r.get("census")]
        if cens:
            first, last = cens[0], cens[-1]
            out.append("\nbreadth (census) — grows even while pass@1 is ceiling-bound:")
            for k in ("capabilities", "agents", "tools", "evals", "harnessEvals", "specs"):
                lv = last.get(k)
                if not isinstance(lv, int):
                    continue
                fv = first.get(k)
                d = lv - fv if isinstance(fv, int) else 0
                out.append(f"  {k:13} {lv}" + (f"  (+{d} over last {len(cens)} runs)" if d > 0 else ""))
        return "\n".join(out)

    def cmd_find(self, arg: str) -> str:
        """navigator agent decides a search term, then fs.grep runs (wired)."""
        if not arg.strip():
            return "usage: /find <what to locate>"
        nav = self._load_agent("navigator_agent.py", self.llm)
        [d] = nav.decide({"task": arg, "path": "."})
        if d.type != "fs.grep":
            return f"navigator: {d.payload.get('note','no term')}"
        out = self.rt.apply(d)
        ms = out.get("matches", []) if isinstance(out, dict) else []
        head = f"navigator searched '{d.payload['pattern']}' — {len(ms)} match(es):"
        return head + "".join(f"\n  {m['file']}:{m['line']}  {m['text']}" for m in ms[:15])

    def cmd_grep(self, arg: str) -> str:
        import os
        parts = arg.split()
        if not parts:
            return "usage: /grep <pattern> [path]"
        # A multi-word pattern (e.g. 'def fix_loop') was mis-split into pattern='def' path='fix_loop'.
        # Only peel off a trailing PATH arg if it actually exists; otherwise the whole input is the pattern.
        if len(parts) > 1 and os.path.exists(parts[-1]):
            pattern, path = " ".join(parts[:-1]), parts[-1]
        else:
            pattern, path = arg, "."
        out = self._tool("fs.grep", {"pattern": pattern, "path": path})
        ms = out.get("matches", []) if isinstance(out, dict) else []
        return f"{len(ms)} match(es):" + "".join(f"\n  {m['file']}:{m['line']}  {m['text']}" for m in ms[:15])

    def cmd_ls(self, arg: str) -> str:
        out = self._tool("fs.list", {"path": arg.strip() or "."})
        es = out.get("entries", []) if isinstance(out, dict) else []
        return "".join(f"\n  {e['type']:<4} {e['name']}" for e in es) or "(empty)"

    def cmd_read(self, arg: str) -> str:
        if not arg.strip():
            return "usage: /read <file>"
        out = self._tool("fs.read", {"path": arg.strip()})
        return out.get("content", out.get("error", "")) if isinstance(out, dict) else str(out)

    def cmd_symbols(self, arg: str) -> str:
        if not arg.strip():
            return "usage: /symbols <file.py>"
        out = self._tool("py.symbols", {"path": arg.strip()})
        ss = out.get("symbols", []) if isinstance(out, dict) else []
        return "".join(f"\n  {s['kind']:<8} {s['name']} (line {s['line']})" for s in ss) or "(no symbols)"

    def cmd_files(self, arg: str) -> str:
        """fs.find tool: locate files by glob pattern (wires fs.find)."""
        parts = arg.split()
        if not parts:
            return "usage: /files <pattern> [path]"
        pattern, path = parts[0], parts[1] if len(parts) > 1 else "."
        if len(parts) == 1 and "/" in pattern:   # natural path-glob 'harness/*.py' -> split dir + glob
            path, pattern = pattern.rsplit("/", 1)
        out = self._tool("fs.find", {"pattern": pattern, "path": path or "."})
        ms = out.get("matches", []) if isinstance(out, dict) else []
        return f"{len(ms)} file(s):" + "".join(f"\n  {m}" for m in ms[:25])

    def cmd_patch(self, arg: str) -> str:
        """code.apply_patch tool: surgical edit (wires apply_patch). Deterministic —
        the user supplies the exact old/new, so no unreliable 2B OLD/NEW generation."""
        bits = arg.split("::")
        if len(bits) < 3:
            return "usage: /patch <file> :: <old text> :: <new text>"
        path, old, new = bits[0].strip(), bits[1].strip(), bits[2].strip()
        try:
            out = self._tool("code.apply_patch", {"path": path, "old": old, "new": new})
        except RuntimeError as exc:
            return f"patch rejected: {exc}"
        return f"applied to {out.get('path')} ({out.get('bytesAfter')} bytes)" if isinstance(out, dict) else str(out)

    def cmd_run(self, arg: str) -> str:
        """commander agent proposes a command; shell.exec runs it (gated)."""
        if not arg.strip():
            return "usage: /run <task>"
        cmd = self._load_agent("commander_agent.py", self.llm)
        [d] = cmd.decide({"task": arg})
        if d.type != "shell.exec":
            return f"commander: {d.payload.get('note','no command')}"
        try:
            out = self.rt.apply(d)
        except RuntimeError as exc:
            return f"refused by safety gate: {exc}"
        return f"$ {d.payload['command']}\nexit={out.get('exitCode')}\n{out.get('stdout','')}{out.get('stderr','')}"

    def cmd_fix(self, arg: str) -> str:
        bits = [b.strip() for b in arg.split("::")]
        if len(bits) < 3:
            return "usage: /fix <file> :: <instruction> :: <test command>"
        from harness.coding_loop import fix_loop
        res = fix_loop(bits[0], bits[1], bits[2], max_iters=3, verbose=True)
        return f"{'solved' if res.success else 'not solved'} in {res.attempts} attempt(s)"

    def cmd_fixrepo(self, arg: str) -> str:
        """Multi-file fix: locate the faulty file (traceback + import graph) and fix it,
        even when the failing test is in a different file. Wires harness/multi_file.py."""
        bits = [b.strip() for b in arg.split("::")]
        if len(bits) < 2:
            return "usage: /fixrepo <instruction> :: <test command> [:: <test file>]"
        import os
        from harness.multi_file import multi_file_fix
        instr, testcmd = bits[0], bits[1]
        test_file = bits[2] if len(bits) > 2 else next(
            (f for f in os.listdir(".") if f.startswith("test") and f.endswith(".py")), "")
        # #EXT-037-REQ-10 Start
        # `runtime=self._write_runtime()` (Tenet 1) -- the same root-anchored `Runtime`
        # `/init`/`/rename`/`/move` already use -- so every revert this real-host command
        # performs is gated, EXT-037 root-jailed, and hash-chain logged.
        r = multi_file_fix(".", testcmd, instr, test_file, max_iters=3, verbose=True,
                            runtime=self._write_runtime())
        # #EXT-037-REQ-10 End
        where = f" (fixed {r['file']})" if r.get("file") else ""
        return f"{'solved' if r['solved'] else 'not solved'}{where}; tried: {', '.join(r['tried']) or '—'}"

    def cmd_map(self, arg: str) -> str:
        """Repo map (EXT-004): a ranked overview of the codebase's public surface — top-level
        functions/classes per file, most-referenced first (Aider-style). Deterministic; helps
        you (and the model) understand cross-file structure without reading everything."""
        from harness.repo_map import build_repo_map
        return build_repo_map(arg.strip() or ".", max_files=30, max_syms=8) or "(no Python files)"

    def cmd_rename(self, arg: str) -> str:
        """Test-gated rename refactoring (EXT-003): rename a symbol across the repo; the suite
        (green before) must stay green after, else it reverts. Deterministic edit + test gate —
        a refactor that can't silently break behavior. Wires harness/refactor.py."""
        bits = arg.split()
        if len(bits) < 2:
            return "usage: /rename <old> <new>"
        from harness.refactor import rename_symbol
        # #EXT-037-REQ-9 Start
        # `runtime=self._write_runtime()` (Tenet 1) -- the same root-anchored `Runtime`
        # `/init`/`/remember`/`/rewind` already use -- so every file this real-host command
        # writes is gated, EXT-037 root-jailed, and hash-chain logged.
        return rename_symbol(".", bits[0], bits[1], runtime=self._write_runtime())["note"]
        # #EXT-037-REQ-9 End

    def cmd_move(self, arg: str) -> str:
        """Test-gated move refactor (EXT-003): move a top-level symbol to another module; the
        source re-exports it so importers keep working, and it reverts if the suite goes red."""
        bits = arg.split()
        if len(bits) < 3:
            return "usage: /move <symbol> <from_file> <to_file>"
        from harness.refactor import move_symbol
        # #EXT-037-REQ-9 Start
        # `runtime=self._write_runtime()` (Tenet 1), mirroring `cmd_rename` above.
        return move_symbol(".", bits[0], bits[1], bits[2], runtime=self._write_runtime())["note"]
        # #EXT-037-REQ-9 End

    def cmd_usages(self, arg: str) -> str:
        """AST find-usages (EXT-004): every reference/definition of a symbol across the repo,
        ignoring strings/comments (precise, unlike grep). Wires harness/navigate.py."""
        if not arg.strip():
            return "usage: /usages <symbol>"
        from harness.navigate import find_usages
        us = find_usages(".", arg.strip())
        if not us:
            return f"no usages of {arg.strip()}"
        return f"{len(us)} usage(s) of {arg.strip()}:" + "".join(
            f"\n  {u['file']}:{u['line']} [{u['kind']}] {u['text'][:70]}" for u in us[:30])

    def cmd_about(self, arg: str) -> str:
        """Symbol summary (EXT-004): ONE view of a symbol — where it's defined, who calls it, how
        many references, and whether it looks dead. Composes the whole navigation suite
        (find_definition + find_callers + find_usages + find_dead_code) into a Claude-Code-like
        'tell me about X'. Max leverage of the nav layer, zero new primitives."""
        sym = arg.strip()
        if not sym:
            return "usage: /about <symbol>"
        from harness.navigate import find_definition, find_callers, find_usages, find_dead_code
        defs = find_definition(".", sym)
        callers = find_callers(".", sym)
        refs = [u for u in find_usages(".", sym) if u["kind"] == "ref"]
        dead = any(d["symbol"] == sym for d in find_dead_code("."))
        out = [f"about `{sym}`:"]
        out.append("  defined: " + (", ".join(f"{d['file']}:{d['line']} [{d['kind']}]"
                                              for d in defs[:3]) if defs else "(no top-level def/class found)"))
        out.append(f"  references: {len(refs)}   callers: {len(callers)}")
        if callers:
            out.append("  called by: " + ", ".join(sorted({c['caller'] for c in callers})[:8]))
        if dead:
            out.append("  ! flagged as a dead-code candidate (no references found)")
        return "\n".join(out)

    def cmd_build(self, arg: str) -> str:
        """Behavioral solve (EXT-012 system): turn an intent into a working function in the current
        dir via the canonical solve — the 2B writes a Gherkin behavior spec (comprehension step pins
        the exact case the intent names), derives its OWN tests, implements, and fixes against them.
        The SAME system the eval proved on held-out real commits (6/37 vs 4/37 baseline), now wired as
        the real product path via harness.behavioral_solve. Usage: /build <func_name> <intent>."""
        bits = arg.strip().split(None, 1)
        if len(bits) < 2 or not bits[0].isidentifier():
            return "usage: /build <func_name> <intent>   e.g. /build is_prime check if a number is prime"
        func, intent = bits[0], bits[1]
        from harness.intent_loop import build_in_dir
        # #EXT-037-REQ-13 Start
        # `runtime=self._write_runtime()` (Tenet 1) -- the same root-anchored `Runtime`
        # `/rename`/`/move`/`/fixrepo`/`/undo`/`/buildsystem`/`/agent` already use -- so a real
        # `/build` invocation's code + test writes are gated, EXT-037 root-jailed, and
        # hash-chain logged, closing the last real-host write path in this sweep (tracker #112).
        r = build_in_dir(".", intent, f"{func}.py", func, runtime=self._write_runtime())
        # #EXT-037-REQ-13 End
        return f"[build {'OK' if r['self_pass'] else 'partial'}] {r['note']}\n  files: {', '.join(r['files'])}"

    # #EXT-036-REQ-4 Start
    def cmd_buildsystem(self, arg: str) -> str:
        """Sentence-to-system (EXT-036): plan -> topological build (syntax-gated + repair) ->
        assemble -> run an executable acceptance checklist. A separate command from /build
        (which builds a single function) — this builds a whole multi-module system from one
        sentence into a subdirectory of the current directory. Wires harness.system_builder.
        When hard-tier escalation is CONFIGURED (REQ-13, TASK-18 — a measured
        complex-system-build-specialist is registered), routes through
        build_system_escalating so gemma runs first and only pays for the stronger fallback
        on a genuine ship-failure; otherwise behaves exactly as plain build_system (no
        regression when escalation is unconfigured)."""
        sentence = arg.strip()
        if not sentence:
            return "usage: /buildsystem <one-sentence spec>"
        subdir = Path(".") / ".jaros" / "built_systems" / f"sys_{uuid.uuid4().hex[:8]}"
        # #EXT-036-REQ-13 Start
        escalation = _buildsystem_escalation_config()
        model_label = None
        if escalation is not None:
            manager_url, fallback_model_id, primary_model_id = escalation
            from harness.system_builder import build_system_escalating
            from harness.collaborative_solve import _http_swap
            # #EXT-037-REQ-11 Start
            # `runtime=self._write_runtime()` (Tenet 1) -- the same root-anchored `Runtime`
            # `/init`/`/rename`/`/move`/`/fixrepo`/`/undo` already use -- so every module this
            # real-host command writes is gated and hash-chain logged.
            r = build_system_escalating(
                sentence, subdir,
                primary_llm=self.llm, fallback_llm=self.llm,
                swap_fn=_http_swap(manager_url),
                fallback_model_id=fallback_model_id,
                primary_model_id=primary_model_id,
                runtime=self._write_runtime(),
            )
            # #EXT-037-REQ-11 End
            model_label = fallback_model_id if r.get("model") == "fallback" else primary_model_id
        else:
            from harness.system_builder import build_system
            # #EXT-037-REQ-11 Start
            r = build_system(sentence, subdir, llm=self.llm, runtime=self._write_runtime())
            # #EXT-037-REQ-11 End
        # #EXT-036-REQ-13 End
        mods = ", ".join(r.get("modules", {})) or "(none)"
        status = "shipped" if r.get("shipped") else "NOT shipped"
        doneness = "DONE" if r.get("done") else "NOT done"
        unmet = r.get("unmet") or []
        # #EXT-036-REQ-14 Start
        if r.get("shipped"):
            self._last_built_dir = subdir
        # #EXT-036-REQ-14 End
        # #EXT-036-REQ-13 Start
        header = f"[buildsystem] {status}, {doneness}"
        if model_label:
            tag = " (escalated)" if r.get("escalated") else ""
            header += f" via {model_label}{tag}"
        header += f" — into {subdir}"
        # #EXT-036-REQ-13 End
        out = [header, f"  modules: {mods}"]
        if unmet:
            out.append("  unmet: " + ", ".join(unmet))
        if r.get("note"):
            out.append(f"  note: {r['note']}")
        # #EXT-037-REQ-5 Start
        # FINALIZE: wield the toolbelt to deliver a versioned, set-up project — not
        # just source files — after a shipped build. Config/flag-gated (default ON
        # for git, "auto" for venv, auto-run always off); never breaks the build
        # result on a finalize failure (finalize_system never raises).
        if r.get("shipped"):
            fin_cfg = _buildsystem_finalize_config()
            if fin_cfg["enabled"]:
                from harness.system_finalize import finalize_system
                fin = finalize_system(subdir, r.get("modules"), git=fin_cfg["git"], venv=fin_cfg["venv"])
                step_names = ", ".join(s["step"] for s in fin.get("steps", []))
                out.append(f"  finalize: {'ok' if fin.get('ok') else 'issues'} ({step_names})")
            else:
                out.append("  finalize: disabled (JCODE_FINALIZE_SYSTEM)")
        # #EXT-037-REQ-5 End
        return "\n".join(out)
    # #EXT-036-REQ-4 End

    # #EXT-036-REQ-14 Start
    def cmd_modifysystem(self, arg: str) -> str:
        """Modify an EXISTING system from a sentence (EXT-036 TASK-7, REQ-14) — regression-
        gated: existing acceptance behavior must survive, or the change is reverted. Operates
        on the last /buildsystem output by default, or an explicit ``<dir> :: <sentence>``.
        Usage: /modifysystem <sentence>   or   /modifysystem <dir> :: <sentence>."""
        arg = arg.strip()
        if not arg:
            return "usage: /modifysystem [<dir> ::] <modification sentence>"
        if "::" in arg:
            dir_part, _, sentence = arg.partition("::")
            target_dir, sentence = Path(dir_part.strip()), sentence.strip()
        else:
            target_dir, sentence = self._last_built_dir, arg
        if not sentence:
            return "usage: /modifysystem [<dir> ::] <modification sentence>"
        if target_dir is None:
            return ("no system to modify — build one first with /buildsystem, or give a dir: "
                     "/modifysystem <dir> :: <modification sentence>")
        if not target_dir.is_dir():
            return f"no such system directory: {target_dir}"
        modules = {p.name: p.read_text(encoding="utf-8") for p in sorted(target_dir.glob("*.py"))}
        if not modules:
            return f"no modules found in {target_dir}"
        from harness.system_builder import modify_system
        # #EXT-037-REQ-11 Start
        # `runtime=self._write_runtime()` (Tenet 1), mirroring `cmd_buildsystem` above.
        r = modify_system(modules, sentence, target_dir, llm=self.llm, runtime=self._write_runtime())
        # #EXT-037-REQ-11 End
        status = "applied" if r.get("applied") else "NOT applied (reverted)"
        out = [f"[modifysystem] {status} — {target_dir}"]
        regressed = r.get("regressed") or []
        if regressed:
            out.append("  regressed: " + ", ".join(regressed))
        out.append(f"  new behavior: {'confirmed' if r.get('new_behavior_ok') else 'not confirmed'}")
        if r.get("note"):
            out.append(f"  note: {r['note']}")
        return "\n".join(out)
    # #EXT-036-REQ-14 End

    def cmd_agent(self, arg: str) -> str:
        """Agentic master loop (EXT-009): give ONE plain request; the system plans a TODO, runs the
        deterministic tools step by step, OBSERVES each result, and REPLANS on failure — the
        Claude-Code 'nO' loop + TodoWrite working-memory on the local model. The agent that wields
        the tools so a human doesn't run them by hand. Wires harness/agent_loop.py."""
        a = arg.strip()
        if not a:
            return "usage: /agent <request>   |   /agent --plan <request>  (preview, no changes)"
        from harness.spec_loop import spec_driven_loop, plan_preview
        if a.startswith("--plan"):                   # plan mode (EXT-009 REQ-4): dry-run, no changes
            intent = a[len("--plan"):].strip()
            return ("[plan mode — no changes made]\n" + plan_preview(intent, ".")) if intent \
                else "usage: /agent --plan <request>"
        # Default to the STRUCTURED jarify-flow loop — it beat the free-form agent loop 3/3 vs 2/3
        # on the agentic eval (the 2B is unreliable at choosing steps; a fixed flow isn't).
        from harness.multi_file import _snapshot
        self._agent_snapshot = _snapshot(".")        # whole-run checkpoint (EXT-009 REQ-7)
        # #EXT-037-REQ-12 Start
        # `runtime=self._write_runtime()` (Tenet 1) -- the same root-anchored `Runtime`
        # `/fixrepo`/`/undo`/`/buildsystem` already use -- so every write a real `/agent`
        # invocation performs (FIX flow's multi_file_fix, and BUILD flow's module writes) is
        # gated, EXT-037 root-jailed, and hash-chain logged.
        r = spec_driven_loop(arg, ".", runtime=self._write_runtime())
        # #EXT-037-REQ-12 End
        status = "SOLVED" if r["solved"] else "unsolved"
        note = f" — {r['note']}" if r.get("note") else ""
        return f"agent [{r['flow']} flow]: {status}{note}\n  (/undo to revert this run)"

    def cmd_remember(self, arg: str) -> str:
        """Project memory (EXT-009 REQ-3): append a note/convention to .jcode/memory.md — persists
        across runs (Claude Code's CLAUDE.md analog, for jcode). Wires harness/project_memory.py.

        EXT-036 REQ-16: ALSO captures the note as a durable per-repo LONG-TERM fact
        (.jaros/memory.jsonl) so it becomes available to the memory-agent's selective recall
        on future plain-language turns (see _recall_memory / harness/repo_memory.py)."""
        if not arg.strip():
            return "usage: /remember <note or convention>"
        from harness.project_memory import append_memory
        # #EXT-042-REQ-5 Start
        # Route the .jcode/memory.md write through a real code.write_file Decision (Tenet 1) via
        # a root-anchored Runtime (mirrors cmd_init below / EXT-037 REQ-5's _git_tool pattern).
        path = append_memory('.', arg, runtime=self._write_runtime())
        if not path:
            return "remember refused: the write was rejected by the safety gate (see logs)"
        # #EXT-042-REQ-5 End
        # #EXT-036-REQ-16 Start
        from harness.repo_memory import add_fact
        if add_fact(arg, root="."):
            self.repo_facts = getattr(self, "repo_facts", []) + [arg.strip()]
        # #EXT-036-REQ-16 End
        return f"remembered -> {path}"

    def cmd_memory(self, _arg: str) -> str:
        """Show the project memory (.jcode/memory.md), plus the per-repo long-term FACT store
        (EXT-036 REQ-16, .jaros/memory.jsonl) that the memory-agent selects from."""
        from harness.project_memory import read_memory
        m = read_memory(".")
        out = m.rstrip() if m.strip() else "(no project memory yet — add one with /remember <note>)"
        # #EXT-036-REQ-16 Start
        from harness.repo_memory import load_facts
        facts = load_facts(".")
        if facts:
            out += "\n\nlong-term facts (recall-selectable):\n" + "\n".join(f"  - {f}" for f in facts)
        # #EXT-036-REQ-16 End
        return out

    # #EXT-042-REQ-4 Start
    def cmd_init(self, _arg: str) -> str:
        """`/init` (EXT-042 REQ-3/4): write a starter JCODE.md from deterministic repo
        comprehension (harness/repo_map.py) — Claude Code's `/init`, for jcode. Never overwrites
        an existing JCODE.md; the loaded content only takes effect on the NEXT CLI session (this
        instance's self.jcode_md was cached at construction, per REQ-2).

        EXT-042 REQ-5 (Tenet 1): the write is routed through a real `code.write_file` Decision
        via a root-anchored Runtime (`_write_runtime`), so it gets the gate + EXT-037 path-jail +
        hash-chain log every other host-project write goes through, instead of a raw
        `Path.write_text`. A gate rejection degrades to an honest message, never a crash."""
        from harness.jcode_md import init_jcode_md
        return init_jcode_md(".", runtime=self._write_runtime())
    # #EXT-042-REQ-4 End

    def cmd_undo(self, _arg: str) -> str:
        """Revert the last /agent run (EXT-009 REQ-7): restore the repo snapshot taken before it —
        Claude Code's checkpoints. Session-scoped (the most recent /agent run).

        EXT-037 REQ-10 (Tenet 1): the restore is routed through a real `code.write_file` Decision
        via a root-anchored Runtime (`_write_runtime`, the same helper `/rename`/`/move`/`/init`
        already use), so it gets the gate + EXT-037 path-jail + hash-chain log every other
        host-project write goes through, instead of a raw `Path.write_text`. A gate rejection
        degrades to an honest message, never a crash (and never clears the snapshot, so /undo
        can be retried)."""
        snap = getattr(self, "_agent_snapshot", None)
        if not snap:
            return "nothing to undo (no /agent run this session)"
        from harness.multi_file import _restore
        # #EXT-037-REQ-10 Start
        err = _restore(snap, runtime=self._write_runtime(), root=os.path.abspath("."))
        if err:
            return f"undo failed: {err}"
        # #EXT-037-REQ-10 End
        self._agent_snapshot = None
        return f"reverted the last agent run ({len(snap)} files restored)"

    def cmd_diff(self, _arg: str) -> str:
        """Show what the last /agent run CHANGED vs its checkpoint (Claude Code's diff view) — review
        before keeping it or running /undo. Session-scoped to the most recent /agent run; pairs with
        /undo (the same snapshot)."""
        snap = getattr(self, "_agent_snapshot", None)
        if not snap:
            return "nothing to diff (run /agent first; /diff shows its changes vs the checkpoint)"
        import difflib
        from pathlib import Path
        files = set(snap) | {str(p) for p in Path(".").rglob("*.py")}
        out: list[str] = []
        for path in sorted(files):
            before = snap.get(path, "")
            after = Path(path).read_text(encoding="utf-8") if Path(path).is_file() else ""
            if before == after:
                continue
            out.extend(difflib.unified_diff(before.splitlines(), after.splitlines(),
                                            fromfile=path, tofile=path, lineterm=""))
        if not out:
            return "no changes since the last /agent checkpoint"
        return "\n".join(out[:200]) + ("\n... (diff truncated)" if len(out) > 200 else "")

    # #EXT-049-REQ-3 Start
    def cmd_checkpoints(self, _arg: str) -> str:
        """List the fine-grained per-edit checkpoint ring (EXT-049), newest first — one entry per
        accepted write/edit Decision (e.g. /patch) made via this session's primary Runtime. Extends
        /undo's whole-run checkpoint (EXT-009) with per-edit granularity; pairs with /rewind."""
        ring = getattr(self, "_checkpoint_ring", None)
        if not ring or len(ring) == 0:
            return ("no checkpoints yet (the ring records edits made via /patch and other "
                    "tracked write Decisions as the session runs)")
        lines = [f"checkpoint ring ({len(ring)}/{ring.maxlen}, 1 = most recent):"]
        for i, entry in enumerate(ring.entries_newest_first(), start=1):
            lines.append(f"  [{i}] {entry.summary()}  (id {entry.id})")
        return "\n".join(lines)

    def cmd_rewind(self, arg: str) -> str:
        """Restore the workspace N steps back (or to a specific checkpoint id) — the finer-grained
        superset of /undo (EXT-009 REQ-7 keeps working unchanged). Each restore is applied through
        a REAL `code.write_file` Decision (Tenet 1: never a raw file write) via
        `self._write_runtime()`, so it is gated, EXT-037 root-jailed, and hash-chain-logged exactly
        like any other product-surface write. A creation (no prior content — the toolbelt has no
        delete-file Decision type) is reported honestly rather than faked as undone."""
        ring = getattr(self, "_checkpoint_ring", None)
        a = arg.strip()
        if not a:
            return self.cmd_checkpoints(a)
        if not ring or len(ring) == 0:
            return "nothing to rewind (no checkpoints yet this session)"
        if a.lstrip("-").isdigit():
            n = int(a)
        else:
            n = ring.position_from_newest(a)
            if n is None:
                return f"no checkpoint matching id {a!r} (see /checkpoints)"
        if n < 1 or n > len(ring):
            return f"checkpoint ring only has {len(ring)} entr{'y' if len(ring) == 1 else 'ies'} — can't rewind {n} step(s)"
        entries = ring.last_n(n)
        rt = self._write_runtime()
        lines = [f"rewinding {n} step(s):"]
        for entry in entries:
            if not entry.existed:
                lines.append(f"  {entry.path}: created by this checkpoint — cannot fully "
                              "un-create (no delete tool); left as-is")
                continue
            if rt is None:
                lines.append(f"  {entry.path}: FAILED — no runtime available to apply the restore")
                continue
            decision = self._mk(
                id=f"rewind-{entry.id}-{uuid.uuid4().hex[:6]}", source="cli",
                type="code.write_file",
                payload={"path": entry.path, "content": entry.before_content or ""})
            try:
                rt.apply(decision)
                lines.append(f"  {entry.path}: restored")
            except Exception as exc:
                lines.append(f"  {entry.path}: FAILED — {exc}")
        ring.drop_last_n(n)
        return "\n".join(lines)
    # #EXT-049-REQ-3 End

    # #EXT-037-REQ-5 Start
    def _git_tool(self, dtype: str, payload: dict):
        """Dispatch a git.* Decision through a root-anchored Runtime (REQ-5: the toolbelt
        WIELDED by the interactive CLI, the same two-plane path as
        harness/system_finalize.py — build a real Decision, apply it through
        Runtime(root=...), never call the tool class directly). ``root`` defaults to the
        CLI's cwd ('.', resolved to an absolute path), mirroring how /agent's ``edit`` step
        and /run resolve their working directory.

        NEVER raises to the REPL: any gate rejection (a not-a-repo root, a bad payload, or
        git.commit's secret/ignored-path guard refusing the whole commit) or executor
        failure is caught here and returned as an honest error string instead — the
        caller's handler decides how to present it, but a git failure can never produce an
        uncaught traceback in the REPL.

        Returns ``(output, None)`` on success or ``(None, error_text)`` on any failure.
        """
        root = payload.get("root") or os.path.abspath(".")
        full_payload = {**payload, "root": root}
        try:
            from harness.coding_loop import Runtime
            # #EXT-045-REQ-1 Start
            _on_event = None
            if getattr(self, "stream", False):
                from harness.tool_stream import make_printer
                _on_event = make_printer()
            # #EXT-047-REQ-2 Start
            rt = Runtime(
                root=root, on_event=_on_event,
                hooks_config=getattr(self, "hooks_config", None),
                # #EXT-048-REQ-4 Start
                mode=getattr(self, "mode", "default"),
                permission_rules=getattr(self, "permission_rules", None),
                ask_callback=(self._ask_permission if getattr(self, "_interactive", False) else None),
                # #EXT-048-REQ-4 End
            )
            # #EXT-047-REQ-2 End
            # #EXT-045-REQ-1 End
            out = rt.apply(self._mk(id=f"cli-{dtype}-{uuid.uuid4().hex}", source="cli",
                                     type=dtype, payload=full_payload))
            return out, None
        except Exception as exc:
            return None, str(exc)

    @staticmethod
    def _git_read_failed(out: dict) -> "str | None":
        """For a read-only git tool's output: None if the underlying git command
        succeeded (exitCode 0), else an honest one-line failure reason (e.g. 'not a git
        repository') — never raises, never assumes a key is present."""
        if not isinstance(out, dict):
            return "git command returned no output"
        if out.get("exitCode") == 0:
            return None
        return (out.get("stderr") or out.get("stdout") or "git command failed").strip() \
            or "not a git repository"

    def cmd_gitstatus(self, _arg: str) -> str:
        """git.status tool (EXT-037 REQ-5): working-tree status of the current project
        root — porcelain status made readable, never raises on a non-repo directory."""
        out, err = self._git_tool("git.status", {})
        if err:
            return f"git status unavailable: {err}"
        failed = self._git_read_failed(out)
        if failed:
            return f"git status failed: {failed}"
        entries = out.get("entries", [])
        if not entries:
            return "clean (no changes)"
        lines = [f"  {e.get('indexStatus', '?')}{e.get('worktreeStatus', '?')} {e.get('path', '')}"
                 for e in entries]
        return f"{len(entries)} change(s):\n" + "\n".join(lines)

    def cmd_gitlog(self, arg: str) -> str:
        """git.log tool (EXT-037 REQ-5): recent commit history (default ~10), optionally
        an explicit count — never raises on a non-repo/empty repo (reports honestly)."""
        arg = arg.strip()
        payload: dict = {"max_count": 10}
        if arg:
            try:
                n = int(arg)
            except ValueError:
                return "usage: /gitlog [n]"
            if n <= 0:
                return "usage: /gitlog [n]"
            payload["max_count"] = n
        out, err = self._git_tool("git.log", payload)
        if err:
            return f"git log unavailable: {err}"
        if not out.get("hasCommits"):
            return "(no commits yet)"
        commits = out.get("commits", [])
        return "\n".join(f"  {c.get('hash', '')[:10]}  {c.get('date', '')}  {c.get('subject', '')}"
                         for c in commits)

    def cmd_gitdiff(self, arg: str) -> str:
        """git.diff tool (EXT-037 REQ-5): working diff, optionally scoped to one file —
        never raises on a non-repo directory (reports honestly)."""
        arg = arg.strip()
        payload: dict = {}
        if arg:
            payload["paths"] = [arg]
        out, err = self._git_tool("git.diff", payload)
        if err:
            return f"git diff unavailable: {err}"
        failed = self._git_read_failed(out)
        if failed:
            return f"git diff failed: {failed}"
        if not out.get("hasChanges"):
            return "no changes"
        return out.get("diff", "")

    def cmd_gitbranch(self, _arg: str) -> str:
        """git.branch tool (EXT-037 REQ-5): list branches, current marked with '*' — never
        raises on a non-repo directory (reports honestly)."""
        out, err = self._git_tool("git.branch", {"action": "list"})
        if err:
            return f"git branch unavailable: {err}"
        failed = self._git_read_failed(out)
        if failed:
            return f"git branch failed: {failed}"
        branches = out.get("branches", [])
        if not branches:
            return "(no branches yet)"
        current = out.get("current")
        return "\n".join(("* " if b == current else "  ") + b for b in branches)

    def cmd_commit(self, arg: str) -> str:
        """git.commit tool (EXT-037 REQ-5): stage every tracked/untracked change and commit
        with the given message. The tool's own secret guard refuses the WHOLE commit
        (before any host effect) if a candidate staged path looks like a secret/ignored
        path (.env, keys, credentials, logs, __pycache__, ...) — that rejection reason is
        surfaced honestly here, never forced through. Requires a non-empty message."""
        message = arg.strip()
        if not message:
            return "usage: /commit <message>"
        out, err = self._git_tool("git.commit", {"message": message})
        if err:
            return f"commit refused: {err}"
        if not out.get("committed"):
            commit_result = out.get("commit") if isinstance(out.get("commit"), dict) else {}
            reason = (commit_result.get("stderr") or commit_result.get("stdout")
                      or "commit failed").strip()
            return f"commit failed: {reason}"
        staged = out.get("staged", [])
        commit_hash = (out.get("commitHash") or "")[:12]
        return f"committed {commit_hash} ({len(staged)} file(s)): {message}"
    # #EXT-037-REQ-5 End

    def cmd_explain(self, arg: str) -> str:
        """Explain a function or file in plain English — Claude-Code's 'what does this do'. For a
        symbol, finds its definition and extracts the function/class; for a file path, reads it;
        then the model summarizes. Generative (the 2B explains code well), not a hard guarantee."""
        a = arg.strip()
        if not a:
            return "usage: /explain <function|file>"
        import ast
        from pathlib import Path
        from jaros.llm import LlmRequest
        if Path(a).is_file():
            code, target = Path(a).read_text(encoding="utf-8"), a
        else:
            from harness.navigate import find_definition
            ds = find_definition(".", a)
            if not ds:
                return f"no definition of {a} found (pass a file path to explain a whole file)"
            src = Path(ds[0]["file"]).read_text(encoding="utf-8")
            seg = None
            try:
                for node in ast.walk(ast.parse(src)):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                            and node.name == a:
                        seg = ast.get_source_segment(src, node)
                        break
            except SyntaxError:
                pass
            code, target = (seg or src), f"{a} ({ds[0]['file']})"
        prompt = ("Explain in plain English what this Python code does (2-3 sentences, no code):\n\n"
                  + code[:2500] + "\n\nExplanation:")
        out = self.llm.complete(LlmRequest(prompt=prompt, params={"max_tokens": 180})).text
        return f"explain {target}:\n  {out.strip()}"

    def cmd_callers(self, arg: str) -> str:
        """Call hierarchy (EXT-004): functions that CALL a symbol — only call sites, each with its
        enclosing function (distinct from /usages' all-references). Composes harness/navigate.py."""
        if not arg.strip():
            return "usage: /callers <symbol>"
        from harness.navigate import find_callers
        cs = find_callers(".", arg.strip())
        if not cs:
            return f"no callers of {arg.strip()}"
        return f"{len(cs)} caller(s) of {arg.strip()}:" + "".join(
            f"\n  {c['file']}:{c['line']} in {c['caller']}()" for c in cs[:30])

    def cmd_locate(self, arg: str) -> str:
        """Fault localization (EXT-002, Agentless-style): run the tests and pinpoint the failure to
        file:line:function, DEEPEST FRAME FIRST — so a fix can target the exact function, not the
        whole file. Deterministic (the traceback names the function). Composes
        harness/multi_file.localize_fault."""
        # #EXT-005-REQ-12 Start
        from harness.proc_treekill import run_with_treekill
        from harness.multi_file import localize_fault
        try:
            ok, output = run_with_treekill("python -m pytest -q", ".", timeout=60, capture=True)
        except Exception as e:
            return f"locate: could not run tests: {e}"
        # #EXT-005-REQ-12 End
        if ok:
            return "tests pass — nothing to localize"
        frames = localize_fault(output)
        if not frames:
            return "tests failed but no traceback frames found"
        return "fault localization (deepest frame first):" + "".join(
            f"\n  {x['file']}:{x['line']} in {x['function']}()" for x in frames[:15])

    def cmd_defn(self, arg: str) -> str:
        """Go-to-definition (EXT-004): the def/class site(s) of a symbol (complement of /usages,
        composes harness/navigate.py)."""
        if not arg.strip():
            return "usage: /defn <symbol>"
        from harness.navigate import find_definition
        ds = find_definition(".", arg.strip())
        if not ds:
            return f"no definition of {arg.strip()} found"
        return f"{len(ds)} definition(s) of {arg.strip()}:" + "".join(
            f"\n  {d['file']}:{d['line']} [{d['kind']}] {d['text'][:70]}" for d in ds)

    def cmd_deadcode(self, arg: str) -> str:
        """Dead-code candidates (EXT-004): public top-level functions/classes referenced NOWHERE
        in the repo (composes the find-usages pass). Run on the project ROOT for accuracy —
        scoping to a subdir flags symbols used from sibling dirs."""
        from harness.navigate import find_dead_code
        d = find_dead_code(arg.strip() or ".")
        if not d:
            return "no dead-code candidates"
        return (f"{len(d)} dead-code candidate(s) (caveat: public API / entry points may appear):"
                + "".join(f"\n  {x['file']}:{x['line']} {x['symbol']}" for x in d[:30]))

    def cmd_plan(self, arg: str) -> str:
        """Multi-step (EXT-004): the `planner` agent turns a request into an ordered plan, then
        each step runs deterministically — model PLANS, tools/agents ACT. `fix` -> multi_file_fix,
        `run` -> the test suite, `find`/`read` -> the navigator/reader. Wires planner_agent.py."""
        if not arg.strip():
            return "usage: /plan <natural-language request>"
        import os
        [d] = self._load_agent("planner_agent.py", self.llm).decide({"request": arg})
        plan = d.payload.get("plan", [])
        if not plan:
            return "planner: couldn't form a plan"
        test_file = next((f for f in os.listdir(".") if f.startswith("test") and f.endswith(".py")), "")
        out = ["plan: " + " -> ".join(s["action"] for s in plan)]
        for i, s in enumerate(plan, 1):
            act, a = s["action"], s.get("arg", "")
            if act == "fix":
                from harness.multi_file import multi_file_fix
                # #EXT-037-REQ-12 Start
                # `runtime=self._write_runtime()` (Tenet 1) -- the same root-anchored `Runtime`
                # `/fixrepo`/`/undo` already use -- so a real `/plan`'s `fix` step is gated,
                # EXT-037 root-jailed, and hash-chain logged.
                r = multi_file_fix(".", "python -m pytest -q", a or arg, test_file, verbose=False,
                                    runtime=self._write_runtime())
                # #EXT-037-REQ-12 End
                out.append(f"  {i}. fix  -> " + (f"solved {r.get('fixed')}" if r["solved"] else "not solved"))
            elif act == "run":
                from harness.multi_file import _run
                ok, res = _run(".", "python -m pytest -q")
                tail = res.strip().splitlines()[-1] if res.strip() else ""
                out.append(f"  {i}. run  -> {'PASS' if ok else 'FAIL'}  {tail}")
            elif act == "find":
                out.append(f"  {i}. find -> " + self.cmd_find(a).replace(chr(10), " | ")[:160])
            elif act == "read":
                m = re.search(r"[\w./\\-]+\.\w+", a)
                out.append(f"  {i}. read -> " + (self.cmd_read(m.group(0))[:120] if m else "(no file named)"))
        return "\n".join(out)

    # #EXT-036-REQ-12 Start
    def cmd_new(self, _arg: str) -> str:
        """Start a fresh conversational session (REQ-12): the in-memory transcript is
        discarded; anything already persisted for the old session stays on disk (findable
        later via /resume). Deterministic state reset — no model involved."""
        from harness.session import Session
        old_id = self.session.id
        self.session = Session()
        return f"started a new session {self.session.id} (previous: {old_id})"

    def cmd_resume(self, arg: str) -> str:
        """Resume a prior session by id (REQ-12): loads its transcript from
        .jaros-data/sessions/<id>.json and continues it — the bounded recent-transcript
        context (used by plain-language routing) now includes those prior turns."""
        sid = arg.strip()
        if not sid:
            return "usage: /resume <session-id>   (see /sessions for recent ids)"
        from harness.session import load_session
        s = load_session(sid)
        if s is None:
            return f"no saved session found for id {sid!r}"
        self.session = s
        return f"resumed session {sid} ({len(s.turns)} turn(s))"

    def cmd_sessions(self, _arg: str) -> str:
        """List recently saved sessions (id + turn count), newest first (REQ-12)."""
        from harness.session import list_sessions
        rows = list_sessions(limit=10)
        if not rows:
            return "(no saved sessions yet)"
        return "recent sessions:" + "".join(
            f"\n  {r['id']}"
            + (f" ({r['name']!r})" if r.get("name") else "")  # #EXT-044-REQ-1
            + f"  ({r['turns']} turn(s))"
            for r in rows
        )
    # #EXT-036-REQ-12 End

    # #EXT-044-REQ-3 Start
    def cmd_name(self, arg: str) -> str:
        """Give the CURRENT session a display name (EXT-044) so it can later be resumed by
        that name via ``-r <name>``/``--fork <name>`` on the command line, not just its id."""
        name = arg.strip()
        if not name:
            return "usage: /name <name>   (names the CURRENT session, see /sessions for ids)"
        from harness.session import set_session_name
        set_session_name(self.session, name)
        return f"session {self.session.id} named {name!r}"
    # #EXT-044-REQ-3 End

    # #EXT-044-REQ-4 Start
    def cmd_fork(self, arg: str) -> str:
        """Branch a session into a NEW id (EXT-044): the new session's transcript is a COPY of
        the referenced session's transcript (an id or a /name; no argument forks the CURRENT
        session) -- the source session's persisted transcript is left completely unchanged, and
        the REPL switches to the new fork."""
        from harness.session import fork_session
        ref = arg.strip() or self.session.id
        forked = fork_session(ref)
        if forked is None:
            return f"no saved session found for {ref!r} (id or name) -- nothing to fork"
        self.session = forked
        return f"forked {ref!r} -> new session {forked.id} ({len(forked.turns)} turn(s))"
    # #EXT-044-REQ-4 End

    # #EXT-051-REQ-2 Start
    def cmd_compact(self, _arg: str) -> str:
        """``/compact`` (EXT-051): deterministically shrink the CURRENT session's transcript by
        folding its older turns into a running summary -- reuses the SAME `_summarize_turns()`
        mechanism `condense()` (EXT-036 REQ-15) already built for its transient routing view, but
        durably mutates + persists `self.session` (unlike `condense()`). Reports before/after
        turn + character counts; an already-short session is an honest no-op."""
        from harness.session import compact_session
        result = compact_session(self.session, llm=self.llm)
        return result.get("message", "")
    # #EXT-051-REQ-2 End

    # #EXT-036-REQ-18 Start
    def cmd_task(self, arg: str) -> str:
        """TODO task management (REQ-18): ``/task <text>`` adds a task for this repo,
        ``/task done <id>`` / ``/task doing <id>`` update its status. Deterministic —
        wires harness/task_store.py; never touches the model."""
        arg = arg.strip()
        if not arg:
            return "usage: /task <text>   |   /task done <id>   |   /task doing <id>"
        bits = arg.split(None, 1)
        verb = bits[0].lower()
        if verb in ("done", "doing"):
            if len(bits) < 2 or not bits[1].strip():
                return f"usage: /task {verb} <id>"
            task_id = bits[1].strip()
            status = "done" if verb == "done" else "in_progress"
            from harness.task_store import update_task
            t = update_task(task_id, root=".", status=status)
            if t is None:
                return f"no task found with id {task_id!r}"
            return f"[{t['id']}] {t['status']}: {t['text']}"
        from harness.task_store import add_task
        t = add_task(arg, root=".")
        if t is None:
            return "could not add task"
        return f"added [{t['id']}] {t['text']}"

    def cmd_tasks(self, _arg: str) -> str:
        """List this repo's tracked tasks (id + status), oldest first (REQ-18)."""
        from harness.task_store import list_tasks
        tasks = list_tasks(root=".")
        if not tasks:
            return "(no tasks yet — add one with /task <text>)"
        return "tasks:" + "".join(f"\n  [{t['id']}] {t['status']:<11} {t['text']}" for t in tasks)
    # #EXT-036-REQ-18 End

    # #EXT-036-REQ-19 Start
    def cmd_experiment(self, arg: str) -> str:
        """Experiment management (REQ-19): ``/experiment <hypothesis> :: <run_cmd>`` defines an
        experiment for this repo, ``/experiment run <id>`` actually RUNS it (a real guarded
        subprocess — never fabricated) and reports the real exit code + output. Deterministic —
        wires harness/experiment_store.py; never touches the model."""
        arg = arg.strip()
        if not arg:
            return ("usage: /experiment <hypothesis> :: <run_cmd>   |   /experiment run <id>")
        bits = arg.split(None, 1)
        if bits[0].lower() == "run":
            if len(bits) < 2 or not bits[1].strip():
                return "usage: /experiment run <id>"
            exp_id = bits[1].strip()
            from harness.experiment_store import run_experiment
            e = run_experiment(exp_id, root=".")
            if e is None:
                return f"no experiment found with id {exp_id!r}"
            return (
                f"[{e['id']}] ran: {e['run_cmd']}\nexit_code={e['exit_code']}\n{e['output']}"
            )
        parts = [p.strip() for p in arg.split("::")]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            return "usage: /experiment <hypothesis> :: <run_cmd> [:: <measure>]"
        hypothesis, run_cmd = parts[0], parts[1]
        measure = parts[2] if len(parts) > 2 else ""
        from harness.experiment_store import define_experiment
        e = define_experiment(hypothesis, run_cmd, root=".", measure=measure)
        if e is None:
            return "could not define experiment"
        return f"defined [{e['id']}] {e['hypothesis']}  (run: {e['run_cmd']})"

    def cmd_experiments(self, _arg: str) -> str:
        """List this repo's defined/run experiments (id + status + last result), oldest first
        (REQ-19)."""
        from harness.experiment_store import list_experiments
        exps = list_experiments(root=".")
        if not exps:
            return "(no experiments yet — define one with /experiment <hypothesis> :: <run_cmd>)"
        lines = []
        for e in exps:
            row = f"  [{e['id']}] {e['status']:<8} {e['hypothesis']}"
            if e.get("status") == "run":
                row += f"  (exit_code={e.get('exit_code')})"
            lines.append(row)
        return "experiments:" + "".join("\n" + line for line in lines)
    # #EXT-036-REQ-19 End

    # #EXT-046-REQ-3 Start
    def cmd_skills(self, _arg: str) -> str:
        """List discovered custom skills (EXT-046): a `.jcode/skills/<name>.md` (or
        `~/.jcode/skills/<name>.md`) file registers `/name` as a real command whose body is
        substituted with any given args and routed through the orchestrator like a plain
        request. Reports an honest empty message when none are discovered."""
        skills = getattr(self, "skills", {}) or {}
        if not skills:
            return "(no custom skills found — drop a .md file into .jcode/skills/ to add one)"
        lines = []
        for name in sorted(skills):
            skill = skills[name]
            desc = skill.description.strip() if skill.description else "(no description)"
            lines.append(f"  /{name}  —  {desc}")
        return "custom skills:" + "".join("\n" + line for line in lines)
    # #EXT-046-REQ-3 End

    # #EXT-047-REQ-4 Start
    def cmd_hooks(self, _arg: str) -> str:
        """List configured lifecycle hooks (EXT-047): drop a `.jcode/hooks.json` (or
        `~/.jcode/hooks.json`) file mapping PreToolUse/PostToolUse/SessionStart/Stop to shell
        commands (optionally `matcher`-scoped to a tool name for Pre/PostToolUse). Reports an
        honest empty message when none are configured."""
        cfg = getattr(self, "hooks_config", {}) or {}
        if not cfg:
            return ("(no hooks configured — drop a .jcode/hooks.json file with "
                     "PreToolUse/PostToolUse/SessionStart/Stop entries to add one)")
        lines = ["configured hooks:"]
        from harness.hooks import VALID_EVENTS
        for event in VALID_EVENTS:
            for hd in cfg.get(event, []):
                scope = f" (matcher={hd.matcher!r})" if hd.matcher else ""
                lines.append(f"  {event}{scope}: {hd.command}")
        return "\n".join(lines)
    # #EXT-047-REQ-4 End

    # #EXT-048-REQ-4 Start
    def cmd_mode(self, arg: str) -> str:
        """Cycle or set the REPL mode (EXT-048): `plan` (propose only — every write/shell
        Decision is withheld and described, never executed), `default` (today's behavior,
        unchanged), `acceptEdits` (auto-approve an `ask`-resolving WRITE Decision that already
        passed the hard gate — never `shell.exec`). `/mode` with no argument cycles
        plan -> default -> acceptEdits -> plan; `/mode <name>` sets it directly. Wired at the SAME
        `Runtime.apply` gate seam EXT-047's hooks use — the change takes effect immediately via
        `Runtime.set_mode`, with no need to reconstruct the CLI."""
        from harness.permissions import MODES
        arg = (arg or "").strip()
        if not arg:
            idx = MODES.index(self.mode) if self.mode in MODES else 0
            self.mode = MODES[(idx + 1) % len(MODES)]
        elif arg in MODES:
            self.mode = arg
        else:
            return f"unknown mode {arg!r} — choose one of {', '.join(MODES)}"
        self.rt.set_mode(self.mode)
        note = " (writes/shell withheld — propose only)" if self.mode == "plan" else ""
        return f"mode: {self.mode}{note}"

    def cmd_permissions(self, _arg: str) -> str:
        """List configured permission rules (EXT-048): drop a `.jcode/permissions.json` (or
        `~/.jcode/permissions.json`) file with `{tool, arg, action}` entries (`action` one of
        `allow`/`ask`/`deny`, first match wins). Reports an honest empty message when none are
        configured. The built-in hard safety gates (egress/destructive-ops denylist, secrets,
        path-jail) always apply first, regardless of any rule here."""
        rules = getattr(self, "permission_rules", []) or []
        if not rules:
            return ("(no permission rules configured — drop a .jcode/permissions.json file with "
                     "{tool, arg, action} entries to add one; hard safety gates always apply)")
        lines = ["configured permission rules (first match wins):"]
        for i, r in enumerate(rules, start=1):
            tool = r.tool or "*"
            arg_part = f" arg={r.arg!r}" if r.arg else ""
            lines.append(f"  {i}. tool={tool!r}{arg_part} -> {r.action}")
        return "\n".join(lines)
    # #EXT-048-REQ-4 End

    # #EXT-050-REQ-2 Start
    def cmd_subagent(self, arg: str) -> str:
        """Delegate a task to a user-authored subagent (EXT-050): `/subagent <name> :: <task>`
        (mirrors the `::`-separated argument convention `/fix`/`/experiment` already use). See
        `/agents` for what's discovered (drop a `.jcode/agents/<name>.md` file to add one)."""
        bits = [b.strip() for b in (arg or "").split("::", 1)]
        if len(bits) < 2 or not bits[0] or not bits[1]:
            return "usage: /subagent <name> :: <task>   (see /agents for discovered subagents)"
        return self._run_subagent(bits[0], bits[1])
    # #EXT-050-REQ-2 End

    # #EXT-036-REQ-8 Start
    def _maybe_ask(self, request: str) -> str:
        """Interactive-only ambiguity check (REQ-8, Claude Code's AskUserQuestion analog):
        if `detect_ambiguity` judges `request` genuinely ambiguous, PRINT its question, read
        the user's answer via input(), record the Q+A as session turns (best-effort), and
        fold the answer into the returned request (routing sees the augmented text). Any
        doubt (no question, no/empty answer, an interrupt) -> `request` returned unchanged
        -- conservative, never blocks headless callers (this is only ever invoked from the
        interactive REPL path, see handle())."""
        try:
            from harness.ask_user import detect_ambiguity
            question = detect_ambiguity(request, llm=self.llm)
        except Exception:
            question = None
        if not question:
            return request
        print(f"\033[33m?\033[0m {question}")
        try:
            answer = input("\033[36m  > \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            return request
        if not answer:
            return request
        try:
            self.session.append("assistant", question)
            self.session.append("user", answer)
        except Exception:
            pass
        return f"{request}\n\nClarification: {answer}"
    # #EXT-036-REQ-8 End

    # #EXT-036-REQ-16 Start
    def _recall_memory(self, request: str) -> list[str]:
        """Memory-AGENT recall (REQ-16): ask the narrow memory-selection judgment which of
        the cached per-repo facts (``self.repo_facts``) are relevant to `request`. Guarded —
        no facts, an unreachable model, or unparseable output all fall through to [] so
        NOTHING is injected; this must never dump the whole store (the measured
        retrieval-negative regression — noisy context hurts the small model)."""
        facts = getattr(self, "repo_facts", None)
        if not facts:
            return []
        try:
            from harness.repo_memory import select_relevant
            return select_relevant(request, facts, llm=self.llm) or []
        except Exception:
            return []
    # #EXT-036-REQ-16 End

    def _nl_fix(self, request: str, arg: str, history: "list[dict] | None" = None,
                memory: "list[str] | None" = None) -> str:
        """Natural-language fix. If the request names a specific file, fix that file; if it
        names NONE (e.g. 'fix the failing tests'), fall back to the multi-file fixer, which
        LOCATES the faulty file(s) across the repo. The branch is a deterministic file-token
        check — no fragile single-vs-repo judgement by the model.

        ``history`` (EXT-036 REQ-12) is a BOUNDED recent transcript folded into the
        instruction text so a follow-up like "now add error handling to that" resolves
        against the prior turn; it does NOT change the file-detection regex above, and is a
        no-op (byte-identical instruction) when there is no prior history. The cached
        ``self.project_md`` (EXT-036 REQ-17, JAROS.md) is folded in as a preamble the same way,
        and `memory` (EXT-036 REQ-16, the memory-agent's selected facts) as a block after it."""
        m = re.search(r"[\w./\\-]+\.\w+", arg) or re.search(r"[\w./\\-]+\.\w+", request)
        # #EXT-036-REQ-12 Start
        # #EXT-036-REQ-17 Start
        # #EXT-036-REQ-16 Start
        # #EXT-042-REQ-2 Start
        instruction = _augment_with_history(request, history, getattr(self, "project_md", ""), memory,
                                             getattr(self, "jcode_md", ""))
        # #EXT-042-REQ-2 End
        # #EXT-036-REQ-16 End
        # #EXT-036-REQ-17 End
        # #EXT-036-REQ-12 End
        if not m:   # no file named -> locate it across the repo
            import os
            from harness.multi_file import multi_file_fix
            test_file = next((f for f in os.listdir(".") if f.startswith("test") and f.endswith(".py")), "")
            # #EXT-037-REQ-12 Start
            # `runtime=self._write_runtime()` (Tenet 1), mirroring `cmd_fixrepo`/`cmd_plan` above.
            r = multi_file_fix(".", "python -m pytest -q", instruction, test_file, max_iters=3,
                                verbose=True, runtime=self._write_runtime())
            # #EXT-037-REQ-12 End
            where = f" (fixed {', '.join(r['fixed'])})" if r.get("fixed") else ""
            return f"{'solved' if r['solved'] else 'not solved'}{where} — multi-file"
        from harness.coding_loop import fix_loop
        res = fix_loop(m.group(0), instruction, "python -m pytest -q", max_iters=3, verbose=True)
        return f"{'solved' if res.success else 'not solved'} in {res.attempts} attempt(s)"

    _ACTION_VERBS = {"fix", "find", "implement", "add", "create", "run",
                     "refactor", "write", "debug", "build"}

    @classmethod
    def _is_multistep(cls, request: str) -> bool:
        """DETERMINISTIC: does the plain request describe MULTIPLE actions? Two distinct
        action verbs (e.g. 'fix the bug and run the tests'), or one verb sequenced with
        then/after ('implement X then verify'). Conservative — single-action requests fall
        through to the orchestrator's reliable one-action routing; /plan degrades to a 1-step
        plan anyway if this over-triggers, so the cost of a false positive is just one extra
        planner call."""
        import re as _re
        r = request.lower()
        verbs = {v for v in cls._ACTION_VERBS if _re.search(rf"\b{v}\b", r)}
        return len(verbs) >= 2 or (bool(verbs) and (" then " in r or " after " in r))

    @classmethod
    def _route_intent(cls, request: str):
        """DETERMINISTIC fast-path: map unambiguous refactor/navigation phrasings straight to
        their command, skipping the orchestrator (2B) call. Returns (action, arg) or None to
        fall through. Reliable for these exact patterns; everything else still routes via the
        orchestrator. This WIRES the nav/refactor commands into plain NL (Claude-Code-like:
        'rename X to Y', 'where is X used') without a model call or a slash prefix."""
        import re as _re
        r = request.strip()
        rl = r.lower()
        m = _re.search(r"\brename\s+(\w+)\s+(?:to|->|→|into)\s+(\w+)", r, _re.I)
        if m:
            return ("rename", f"{m.group(1)} {m.group(2)}")
        m = _re.search(r"\bmove\s+(\w+)\s+from\s+(\S+)\s+to\s+(\S+)", r, _re.I)
        if m:
            return ("move", f"{m.group(1)} {m.group(2)} {m.group(3)}")
        m = _re.search(r"\btell me about\s+(\w+)", rl)
        if m:
            return ("about", m.group(1))
        m = _re.search(r"\b(?:explain|describe|what\s+does)\s+(?:the\s+|a\s+)?(\w+)", rl)
        if m:
            return ("explain", m.group(1))
        m = _re.search(r"\b(?:callers\s+(?:of|for)|what\s+calls)\s+(\w+)", rl)
        if m:
            return ("callers", m.group(1))
        m = _re.search(r"\b(?:usages|references)\s+(?:of|to|for)\s+(\w+)", rl)
        if m:
            return ("usages", m.group(1))
        m = _re.search(r"\bwhere\s+(?:is|are)\s+(\w+)\s+(?:used|referenced|called)\b", rl)
        if m:
            return ("usages", m.group(1))
        m = _re.search(r"\b(?:definition|defined)\s+(?:of|for)\s+(\w+)", rl)
        if m:
            return ("defn", m.group(1))
        m = _re.search(r"\bwhere\s+(?:is|are)\s+(\w+)\s+defined\b", rl)
        if m:
            return ("defn", m.group(1))
        if _re.search(r"\b(?:dead code|unused (?:code|functions?|symbols?))\b", rl):
            return ("deadcode", "")
        if _re.search(r"\b(?:repo|repository|code)\s+map\b", rl):
            return ("map", "")
        return None

    # #EXT-046-REQ-2 Start
    def _route_plain(self, line: str) -> "tuple[str, str]":
        """The plain-language routing chain -- deterministic multistep detection, then the
        deterministic intent fast-path, then the orchestrator agent -- extracted from
        ``handle()``'s else-branch so a skill's SUBSTITUTED template text (``_run_skill``) can
        be routed through the EXACT SAME chain a typed non-slash request uses, rather than a
        second reasoning mechanism (EXT-046 REQ-2). Returns ``(response_text, action_label)``,
        where ``action_label`` feeds the EXT-045 statusline bookkeeping."""
        if self._is_multistep(line):   # multi-action plain request -> the STRUCTURED agent (REQ-7)
            # spec_driven_loop beat the free-form planner 3/3 vs 2/3; it also checkpoints (/undo).
            out = "\033[2m[agent → structured flow]\033[0m\n" + self.cmd_agent(line)
            return out, "agent"
        # #EXT-050-REQ-2 Start
        # Named subagent delegation (EXT-050): a deterministic, no-model-call fast path -- mirrors
        # `_route_intent`'s refactor/nav style -- lets a plain request explicitly delegate to a
        # REGISTERED user-authored subagent ("delegate to <name> subagent: <task>" / "use the
        # <name> subagent to <task>"). Only fires when <name> is an actual key in `self.subagents`,
        # so ordinary prose naming no subagent is never misrouted.
        delegated = self._match_subagent_delegation(line)
        if delegated is not None:
            name, task = delegated
            out = f"\033[2m[subagent → {name}]\033[0m\n" + self._run_subagent(name, task)
            return out, f"subagent:{name}"
        # #EXT-050-REQ-2 End
        intent = self._route_intent(line)   # deterministic refactor/nav routing (no 2B call)
        if intent:
            action, arg = intent
            out = f"\033[2m[intent → /{action} {arg}]\033[0m\n" + getattr(self, "cmd_" + action)(arg)
            return out, action
        # #EXT-036-REQ-12 Start
        # #EXT-036-REQ-15 Start
        # condense() is the raw recent() slice (byte-identical) for under-budget sessions, and
        # a [summary] + recent-turns view once the transcript grows past the budget (REQ-15) —
        # the router always gets ONE consistent shape.
        from harness.session import condense
        history = condense(self.session, llm=self.llm)
        # #EXT-036-REQ-15 End
        # #EXT-036-REQ-16 Start
        memory = self._recall_memory(line)
        # #EXT-036-REQ-16 End
        orch = self._load_agent("orchestrator_agent.py", self.llm)
        # #EXT-051-REQ-1 Start
        # @path / @dir/ reference expansion (EXT-051): a deterministic, no-model-call string
        # composition -- inlines each referenced file's content (bounded, truncation noted) or a
        # bounded directory listing, read through the EXISTING gated fs.read/fs.list tools (the
        # same seam /read and /ls already use). Runs on the raw `line`, AFTER the deterministic
        # multistep/subagent-delegation/intent-fast-path checks above (which keep matching the RAW
        # line so a referenced file's own prose content can never spuriously trigger one of those
        # regexes) -- only the text that reaches the orchestrator/planner is expanded. A `line`
        # with no `@` reference at all is returned byte-identical (a complete no-op).
        from harness.atrefs import expand_at_refs
        expanded_line = expand_at_refs(line, self._at_ref_read, self._at_ref_list)
        # #EXT-051-REQ-1 End
        # #EXT-036-REQ-17 Start
        # #EXT-042-REQ-2 Start
        augmented = _augment_with_history(expanded_line, history, getattr(self, "project_md", ""),
                                           memory, getattr(self, "jcode_md", ""))
        # #EXT-042-REQ-2 End
        # #EXT-036-REQ-17 End
        [d] = orch.decide({"request": augmented, "history": history})
        action, arg = d.payload.get("action", "help"), d.payload.get("arg", "")
        banner = f"\033[2m[orchestrator → {action} {arg}]\033[0m"
        if action == "fix":
            out = banner + "\n" + self._nl_fix(line, arg, history=history, memory=memory)
        else:
            handler = getattr(self, "cmd_" + ("ls" if action == "list" else action), self.cmd_help)
            out = banner + "\n" + handler(arg)
        return out, action
        # #EXT-036-REQ-12 End

    def _run_skill(self, text: str) -> str:
        """Route a skill's substituted template text through ``_route_plain`` -- the SAME
        plain-language chain ``handle()`` runs for a typed non-slash request (EXT-046 REQ-2).
        The template is never re-entered as a literal ``/slash`` line, even if its body happens
        to start with ``/`` — it is always treated as ONE plain-language request."""
        out, _action_label = self._route_plain(text)
        return out
    # #EXT-046-REQ-2 End

    def handle(self, line: str, *, interactive: bool = False) -> str:
        """Top-level: slash commands run directly; plain language is ROUTED — first a
        deterministic intent fast-path (refactor/nav phrasings), then the orchestrator agent.

        EXT-036 REQ-12: every turn (slash or plain) is appended to the session transcript
        and persisted (best-effort). Plain-language routing (the orchestrator path and its
        NL-fix branch) additionally sees a BOUNDED recent transcript as context, so it stays
        conversation-aware, plus a memory-agent-selected ``RELEVANT MEMORY:`` block (REQ-16)
        when the per-repo fact store has something relevant; slash-command dispatch is
        unchanged — still direct/stateless.

        ``interactive`` (EXT-036 REQ-8) gates the ask-the-user check: ONLY the interactive
        REPL (``repl()``) passes ``interactive=True``. Headless/one-shot callers (``main()``'s
        argument path, and the default here) never ask -- they proceed with the request
        as-is, so a headless run can never block waiting on input()."""
        # #EXT-045-REQ-2 Start
        # Statusline bookkeeping (EXT-045): time the whole turn and record the routed action
        # ("problem class") -- both read back by statusline(). Best-effort; a failure here must
        # never affect what handle() actually returns (see the try/finally-style update below).
        _t0 = time.time()
        _action_label = "chat"
        # #EXT-045-REQ-2 End
        line = line.strip()
        if not line:
            return ""
        if line.startswith("/"):
            out = self.dispatch(line)
            # #EXT-045-REQ-2 Start
            _action_label = line.partition(" ")[0].lstrip("/") or "chat"
            # #EXT-045-REQ-2 End
        else:
            # #EXT-036-REQ-8 Start
            # Interactive-only: check + resolve genuine ambiguity BEFORE any routing below,
            # folding the user's answer into `line` so every routing path downstream (the
            # structured agent, the deterministic intent fast-path, and the orchestrator)
            # sees the clarified request. Headless/non-interactive callers (the default)
            # skip this entirely -- never blocks on input().
            if interactive:
                line = self._maybe_ask(line)
            # #EXT-036-REQ-8 End
            # #EXT-046-REQ-2 Start
            out, _action_label = self._route_plain(line)
            # #EXT-046-REQ-2 End
        # #EXT-036-REQ-12 Start
        _record_turn(self, line, out)
        # #EXT-036-REQ-12 End
        # #EXT-045-REQ-2 Start
        # Statusline bookkeeping: record this turn's routed action + measured latency. Best-
        # effort -- must never raise or change `out` (a broken clock/attr must never break the
        # response the caller is about to receive).
        try:
            self._last_action = _action_label
            self._last_latency_s = time.time() - _t0
        except Exception:
            pass
        # #EXT-045-REQ-2 End
        return out

    # -- dispatch ----------------------------------------------------------
    _ALIASES = {"/exit": "/quit", "/q": "/quit", "/h": "/help"}

    def dispatch(self, line: str) -> str:
        line = line.strip()
        if not line:
            return ""
        if not line.startswith("/"):
            return "commands start with '/'. Try /help. (Or just type a request — the orchestrator will route it.)"
        head, _, arg = line.partition(" ")
        head = self._ALIASES.get(head, head)
        handler = getattr(self, "cmd_" + head[1:], None)
        if handler is not None:
            return handler(arg)
        # #EXT-046-REQ-2 Start
        # A built-in command ALWAYS wins (checked above); only when NO built-in matches does a
        # discovered custom skill (EXT-046) get a chance — a skill can never shadow a built-in.
        skill = getattr(self, "skills", {}).get(head[1:])
        if skill is not None:
            from harness.skills import render_template
            rendered = render_template(skill.body, arg)
            return self._run_skill(rendered)
        # #EXT-046-REQ-2 End
        return f"unknown command {head!r}. Try /help."


def repl(session_id: str | None = None) -> int:
    """Interactive Claude-Code-like prompt loop.

    ``session_id`` (EXT-036 REQ-12) resumes a prior conversation (from --resume);
    when omitted a fresh session starts (also resumable later via /resume).

    NOTE (EXT-045): this signature is DELIBERATELY unchanged (one keyword argument, mirroring
    the EXT-044 backward-compat constraint some tests stub `repl` against) -- tool-event
    streaming is decided INTERNALLY (stdout-is-a-tty, never under JSON since the REPL has no
    JSON mode) rather than threaded in as a new parameter."""
    # #EXT-045-REQ-1 Start
    from harness.tool_stream import should_stream
    _stream = should_stream("text", _stdout_is_tty())
    # #EXT-048-REQ-3 Start
    # The REPL is the ONE genuinely interactive surface (it already reads via input() for
    # /quit-detection and _maybe_ask) -- so it's the only caller that opts into `interactive=True`,
    # wiring an `input()`-based permission prompt as the Runtime's `ask_callback`. The headless
    # one-shot path (`_run_one_shot`, below) never passes this -- an `ask` there safely degrades
    # to deny rather than blocking on a prompt with no terminal attached.
    cli = JcodeCli(session_id=session_id, stream=_stream, interactive=True)
    # #EXT-048-REQ-3 End
    # #EXT-045-REQ-1 End
    # #EXT-014-REQ-1 Start
    # Banner reflects the active model (Gemma 4 2B e2b via llamacpp by default; gemma2:2b only if JCODE_LLM_BACKEND=ollama).
    print(f"\n\033[1m jaros-code \033[0m  local coding harness on {cli.model}")
    # #EXT-014-REQ-1 End
    # #EXT-036-REQ-12 Start
    print(f"  session {cli.session.id}"
          + (f" — resumed, {len(cli.session.turns)} turn(s)" if session_id and cli.session.turns else " — new"))
    # #EXT-036-REQ-12 End
    print("  slash-command REPL — type /help, /quit to exit\n")
    while True:
        # #EXT-045-REQ-2 Start
        if getattr(cli, "_show_statusline", False):
            print(f"\033[2m{cli.statusline()}\033[0m")
        # #EXT-045-REQ-2 End
        try:
            line = input("\033[36mjcode›\033[0m ")
        except (EOFError, KeyboardInterrupt):
            print()
            # #EXT-047-REQ-3 Start
            cli.on_stop()  # Stop hooks fire once at session end
            # #EXT-047-REQ-3 End
            return 0
        if line.strip() in ("/quit", "/exit", "/q"):
            # #EXT-047-REQ-3 Start
            cli.on_stop()  # Stop hooks fire once at session end
            # #EXT-047-REQ-3 End
            return 0
        if line.strip() == "/clear":
            print("\033[2J\033[H", end="")
            continue
        try:
            # #EXT-036-REQ-8 Start
            out = cli.handle(line, interactive=True)
            # #EXT-036-REQ-8 End
        except Exception as exc:            # one bad command must NOT kill the interactive session
            out = f"\033[31merror:\033[0m {exc}"
        if out:
            print(out)


# #EXT-043-REQ-1 Start
# #EXT-043-REQ-2 Start
# #EXT-043-REQ-3 Start
# #EXT-043-REQ-4 Start
def _parse_headless_args(args: "list[str]") -> "tuple[str | None, str, int | None, list[str]]":
    """Parse ``sys.argv[1:]`` for the headless/one-shot surface (EXT-043): a linear scan that
    recognizes ``--resume <id>`` (unchanged from before this spec), ``--output-format
    text|json``, and ``--max-turns N`` WHEREVER they occur, and leaves every other token, in its
    original relative order, in ``rest``. When none of the three flags are present, ``rest ==
    args`` exactly -- the input to the existing one-shot join is byte-identical to before this
    spec, which is what makes the "no new flags -> no behavior change" guarantee mechanical.

    Never raises: an unrecognized ``--output-format`` value falls back to ``"text"``; a
    non-integer ``--max-turns`` value falls back to ``None`` ("no cap") -- a malformed flag value
    degrades gracefully rather than crashing a headless/scripted caller before it even runs.

    Returns ``(session_id, output_format, max_turns, rest)``.
    """
    session_id: "str | None" = None
    output_format = "text"
    max_turns: "int | None" = None
    rest: "list[str]" = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--resume" and i + 1 < len(args):
            session_id = args[i + 1]
            i += 2
            continue
        if a == "--output-format" and i + 1 < len(args):
            val = args[i + 1].strip().lower()
            output_format = val if val in ("text", "json") else "text"
            i += 2
            continue
        if a == "--max-turns" and i + 1 < len(args):
            try:
                max_turns = int(args[i + 1])
            except ValueError:
                max_turns = None
            i += 2
            continue
        rest.append(a)
        i += 1
    return session_id, output_format, max_turns, rest


def _stdin_is_tty() -> bool:
    """Best-effort stdin-is-a-terminal check. Any detection failure conservatively answers
    ``True`` ("assume interactive") so a broken/unusual stdin can never silently swallow what
    would otherwise have been a real interactive REPL session into a stdin read."""
    import sys
    try:
        return sys.stdin.isatty()
    except Exception:
        return True


# #EXT-045-REQ-1 Start
def _stdout_is_tty() -> bool:
    """Best-effort stdout-is-a-terminal check (EXT-045) -- used to decide whether tool-event
    streaming/the statusline default on. Any detection failure conservatively answers ``False``
    (the quiet default), never assuming a live terminal it can't confirm."""
    import sys
    try:
        return sys.stdout.isatty()
    except Exception:
        return False
# #EXT-045-REQ-1 End


def _read_stdin_request() -> str:
    """Read + strip the piped request from stdin. Never raises -- any read failure degrades to
    ``""`` (an empty request), letting the caller decide what an empty piped request means."""
    import sys
    try:
        return sys.stdin.read().strip()
    except Exception:
        return ""


def _run_one_shot(request: str, session_id: "str | None", output_format: str,
                   max_turns: "int | None",
                   name_to_set: "str | None" = None,
                   stream: bool = False) -> "tuple[str, int]":
    """Run exactly ONE headless turn and return ``(text_to_print, exit_code)``.

    ``name_to_set`` (EXT-044 REQ-1/3, optional, defaulted so pre-EXT-044 callers are
    unaffected): when given, applied to the session AFTER construction (so it names whichever
    session this run ends up using -- fresh, resumed, or forked) via ``set_session_name``.

    ``stream`` (EXT-045 REQ-1, optional, defaulted ``False`` so pre-EXT-045 callers -- including
    every existing 4-positional-argument test call -- are byte-identical): when the caller (see
    ``main()``) has already decided streaming should be active (never under ``"json"``, see
    ``harness.tool_stream.should_stream``), threaded straight into ``JcodeCli``.

    ``max_turns`` (REQ-4): the one-shot path already performs exactly one turn, so ``N >= 1`` (or
    ``None``, no cap) has no further effect beyond that existing ceiling -- documented honestly,
    not silently ignored. ``N < 1`` is enforced as a genuine refusal: ``JcodeCli`` is never even
    constructed, so a caller that caps at zero turns gets an honest, observable failure rather
    than a flag that quietly does nothing.

    ``output_format`` (REQ-2): ``"text"`` reproduces the exact pre-EXT-043 one-shot
    ``try/except`` contract (same success text, same red ``error:`` text, same exit codes) --
    this is what keeps the default/no-flags invocation byte-identical to before this spec.
    ``"json"`` emits one machine-parseable object with ``request``/``response``/``ok``/``model``
    (plus ``error`` when ``ok`` is false) instead (REQ-3: the exit code carries the same
    success/failure signal a script would otherwise have to parse out of the text).
    """
    import json

    if max_turns is not None and max_turns < 1:
        msg = f"--max-turns {max_turns} < 1 -- refusing to run (0 turns permitted)"
        if output_format == "json":
            return json.dumps({"request": request, "response": None, "ok": False,
                                "model": None, "error": msg}), 1
        return f"\033[31merror:\033[0m {msg}", 1

    try:
        cli = JcodeCli(session_id=session_id, stream=stream)   # #EXT-045-REQ-1
        if name_to_set:                 # #EXT-044-REQ-3
            from harness.session import set_session_name
            set_session_name(cli.session, name_to_set)
        response = cli.handle(request)
        model = cli.model
        # #EXT-047-REQ-3 Start
        cli.on_stop()  # a one-shot run both starts and stops within this call
        # #EXT-047-REQ-3 End
    except Exception as exc:            # a headless run must report cleanly, not dump a traceback
        if output_format == "json":
            return json.dumps({"request": request, "response": None, "ok": False,
                                "model": None, "error": str(exc)}), 1
        return f"\033[31merror:\033[0m {exc}", 1

    if output_format == "json":
        return json.dumps({"request": request, "response": response, "ok": True,
                            "model": model}), 0
    return response, 0
# #EXT-043-REQ-4 End
# #EXT-043-REQ-3 End
# #EXT-043-REQ-2 End
# #EXT-043-REQ-1 End


# #EXT-044-REQ-2 Start
# #EXT-044-REQ-3 Start
# #EXT-044-REQ-4 Start
def _parse_session_flags(rest: "list[str]") -> "tuple[bool, str | None, str | None, str | None, list[str]]":
    """Parse the EXT-044 session-continuity flags out of ``rest`` (the tokens
    ``_parse_headless_args`` -- EXT-043, unmodified -- left after stripping ``--resume``/
    ``--output-format``/``--max-turns``): ``-c``/``--continue`` (resume the most-recently-active
    session), ``-r <id|name>`` (an alias for ``--resume`` that also accepts a session NAME),
    ``--fork [<id|name>]`` (branch a session into a brand-new id -- the value is OPTIONAL: the
    following token is consumed only when it resolves to a real, existing session, otherwise
    ``--fork`` takes no value and that token is left as ordinary request text), and ``--name
    <name>`` (assign a display name to whichever session this run ends up using). Every other
    token is left, in original order, in the returned ``rest``.

    Returns ``(continue_flag, resume_ref, fork_ref, name_to_set, rest)``. ``fork_ref`` is
    ``None`` when ``--fork`` was not given at all, and ``""`` when ``--fork`` was given with no
    (or an unresolvable) following value -- both meaningfully different from "don't fork".

    Never raises: probing whether the next token is a real session reference
    (``resolve_session_ref``) is guarded -- any lookup failure is treated as "not a value"
    (conservative -- the token stays in ``rest``) rather than crashing argument parsing.
    """
    from harness.session import resolve_session_ref

    continue_flag = False
    resume_ref: "str | None" = None
    fork_ref: "str | None" = None
    name_to_set: "str | None" = None
    out: "list[str]" = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in ("-c", "--continue"):
            continue_flag = True
            i += 1
            continue
        if a == "-r" and i + 1 < len(rest):
            resume_ref = rest[i + 1]
            i += 2
            continue
        if a == "--name" and i + 1 < len(rest):
            name_to_set = rest[i + 1]
            i += 2
            continue
        if a == "--fork":
            nxt = rest[i + 1] if i + 1 < len(rest) else None
            try:
                resolvable = bool(nxt) and not nxt.startswith("-") and resolve_session_ref(nxt) is not None
            except Exception:
                resolvable = False
            if resolvable:
                fork_ref = nxt
                i += 2
            else:
                fork_ref = ""
                i += 1
            continue
        out.append(a)
        i += 1
    return continue_flag, resume_ref, fork_ref, name_to_set, out


def _resolve_session_target(continue_flag: bool, resume_ref: "str | None", fork_ref: "str | None",
                             legacy_resume_id: "str | None") -> "tuple[str | None, str | None]":
    """Turn the parsed session-continuity flags into ONE concrete session id to hand to
    ``JcodeCli``/``repl()``, or an honest error message. Priority order: ``--fork`` > ``-c`` >
    ``-r`` > the OLD ``--resume <id>`` flag (passed through UNCHANGED -- no existence check, so
    an unknown id still creates a fresh session under that literal id exactly as before this
    spec) > a fresh session (``None``, the pre-EXT-044 default).

    Returns ``(session_id, error)``; at most one is non-``None``. Never raises -- any lookup
    failure is surfaced as an error string, never a crash.
    """
    from harness.session import resolve_session_ref, most_recent_session_id, fork_session

    try:
        if fork_ref is not None:
            source = fork_ref or resume_ref or legacy_resume_id or most_recent_session_id()
            if not source:
                return None, "no saved sessions exist to --fork"
            forked = fork_session(source)
            if forked is None:
                return None, f"--fork: no saved session found for {source!r} (id or name)"
            return forked.id, None

        if continue_flag:
            rid = most_recent_session_id()
            if not rid:
                return None, "no saved sessions to continue (-c / --continue) -- start one first"
            return rid, None

        if resume_ref:
            rid = resolve_session_ref(resume_ref)
            if rid is None:
                return None, f"no saved session found for {resume_ref!r} (id or name)"
            return rid, None
    except Exception as exc:
        return None, f"session lookup failed: {exc}"

    return legacy_resume_id, None
# #EXT-044-REQ-4 End
# #EXT-044-REQ-3 End
# #EXT-044-REQ-2 End


# #EXT-052-REQ-3 Start
def _dispatch_bg_subcommand(args: "list[str]") -> "int | None":
    """Recognize the EXT-052 background-jobs subcommands (``--bg``/``jobs``/``bg list``/
    ``logs <id>``/``attach <id>``/``stop <id>``) as LEADING tokens, exactly like ``-c``/
    ``--resume`` already take priority over being read as plain request text. Returns ``None``
    (no match) for every other invocation -- the caller then falls through to today's exact
    existing parsing, byte-identically (see design.md's "reserved bare-subcommand words" note for
    the deliberate, narrow collision trade-off this implies).
    """
    if not args:
        return None
    head = args[0]

    if head == "--bg":
        from harness.bg_jobs import submit_job
        request = " ".join(args[1:]).strip()
        if not request:
            print("\033[31merror:\033[0m --bg requires a request, e.g. "
                  'jcode --bg "run the suite"')
            return 1
        rec = submit_job(request)
        print(f"job {rec.id} submitted (pid {rec.pid}, status={rec.status}) "
              f"-- request: {request[:60]!r}")
        print(f"  jcode logs {rec.id}     # view output so far")
        print(f"  jcode attach {rec.id}   # stream live (Ctrl-C detaches, job keeps running)")
        print(f"  jcode stop {rec.id}     # cancel")
        return 0

    if args == ["jobs"] or (len(args) >= 2 and args[0] == "bg" and args[1] in ("list", "jobs")):
        from harness.bg_jobs import format_jobs
        print(format_jobs())
        return 0

    if head == "logs" and len(args) == 2:
        from harness.bg_jobs import read_log
        print(read_log(args[1]))
        return 0

    if head == "attach" and len(args) == 2:
        from harness.bg_jobs import attach_job
        return attach_job(args[1])

    if head == "stop" and len(args) == 2:
        from harness.bg_jobs import stop_job
        result = stop_job(args[1])
        print(result["message"])
        return 0 if result["ok"] else 1

    return None
# #EXT-052-REQ-3 End


# #EXT-053-REQ-2 Start
def _dispatch_doctor_subcommand(args: "list[str]") -> "int | None":
    """Recognize the EXT-053 headless health-check entry (`jcode doctor` / `jcode --doctor`) as
    a LEADING token, exactly like EXT-052's `--bg`/`jobs` family already takes priority over
    being read as plain request text. Returns `None` (no match) for every other invocation, so
    the caller falls through to today's existing parsing byte-identically -- an ordinary
    plain-language request (e.g. "fix the bug") is never misrouted."""
    if not args:
        return None
    if args == ["doctor"] or args[0] == "--doctor":
        from harness.doctor import render as _render_doctor, run_doctor as _run_doctor
        report = _run_doctor()
        print(_render_doctor(report))
        return 0 if report.get("overall") != "fail" else 1
    return None
# #EXT-053-REQ-2 End


def main() -> int:
    """Entry point: a one-shot request if given as args or piped via stdin, else the
    interactive REPL.

      python -m harness.cli                          # interactive REPL (Claude-Code-like)
      python -m harness.cli /status                  # run one command and exit
      python -m harness.cli "fix the bug in foo.py"   # one plain-language request
      python -m harness.cli --bg "fix the bug"       # EXT-052: submit to run DETACHED, returns
                                                      # a job id immediately (never blocks)
      python -m harness.cli jobs                     # EXT-052: list background jobs (alias:
                                                      # "jcode bg list")
      python -m harness.cli logs <id>                # EXT-052: print a background job's output
      python -m harness.cli attach <id>              # EXT-052: stream a running job's output
                                                      # live (Ctrl-C detaches, job keeps running)
      python -m harness.cli stop <id>                # EXT-052: cancel a running background job
                                                      # (kills its recorded pid/tree only)
      python -m harness.cli doctor                    # EXT-053: deterministic health check
      python -m harness.cli --doctor                  # (same; also installed as `jcode doctor` /
                                                      # `jcode --doctor` via pyproject.toml)
      python -m harness.cli --resume <id>            # resume a prior session (REPL, or with a
                                                      # trailing one-shot request after the id)
      echo "fix foo.py" | python -m harness.cli       # headless: request piped via stdin (EXT-043)
      python -m harness.cli -                        # headless: read stdin unconditionally
      python -m harness.cli --output-format json "req"   # machine-parseable JSON on stdout
      python -m harness.cli --max-turns 0 "req"       # refuse to run (0 turns) -- exit non-zero
      python -m harness.cli -c                       # EXT-044: resume the most-recently-active
                                                      # session ("--continue")
      python -m harness.cli -r <id|name>             # EXT-044: resume a specific session by id
                                                      # OR by its assigned /name
      python -m harness.cli --fork [<id|name>]       # EXT-044: branch a session into a NEW id
                                                      # (copies its transcript; original untouched)
      python -m harness.cli --name <name> "req"      # EXT-044: name the session this run uses

    EXT-045 (terminal UX): on a live terminal (never under --output-format json), tool calls
    stream a concise progress line as they happen; JCODE_STREAM_EVENTS=1|0 forces it on/off.
    The REPL's /statusline toggles a persistent "model · class · $0 · latency" status line.
    """
    import sys
    from harness.tool_stream import should_stream  # #EXT-045-REQ-1
    args = sys.argv[1:]
    # #EXT-052-REQ-3 Start
    # Background-jobs subcommands (EXT-052) are recognized FIRST, before any other flag parsing --
    # exactly like -c/--resume already take priority over being read as plain request text. A
    # non-match (None) falls through to the existing parsing below, byte-identically.
    bg_result = _dispatch_bg_subcommand(args)
    if bg_result is not None:
        return bg_result
    # #EXT-052-REQ-3 End
    # #EXT-053-REQ-2 Start
    doctor_result = _dispatch_doctor_subcommand(args)
    if doctor_result is not None:
        return doctor_result
    # #EXT-053-REQ-2 End
    # #EXT-043-REQ-1 Start
    session_id, output_format, max_turns, rest0 = _parse_headless_args(args)
    # #EXT-044-REQ-2 Start
    # #EXT-044-REQ-3 Start
    # #EXT-044-REQ-4 Start
    continue_flag, resume_ref, fork_ref, name_to_set, rest = _parse_session_flags(rest0)

    resolved_session_id, session_err = _resolve_session_target(
        continue_flag, resume_ref, fork_ref, session_id
    )
    if session_err:
        # An unresolvable -c/-r/--fork reference is an honest, reported failure -- JcodeCli is
        # NEVER constructed with a bogus id, in either output format (REQ-2/3/4 acceptance).
        import json as _json
        if output_format == "json":
            print(_json.dumps({"request": None, "response": None, "ok": False,
                                "model": None, "error": session_err}))
        else:
            print(f"\033[31merror:\033[0m {session_err}")
        return 1
    session_id = resolved_session_id
    # #EXT-044-REQ-4 End
    # #EXT-044-REQ-3 End
    # #EXT-044-REQ-2 End

    request: "str | None" = None
    if rest == ["-"]:
        request = _read_stdin_request()
    elif rest:
        request = " ".join(rest)
    elif not _stdin_is_tty():
        piped = _read_stdin_request()
        if piped:
            request = piped

    if request is None:
        return repl(session_id=session_id)

    # #EXT-043-REQ-3 Start
    # #EXT-045-REQ-1 Start
    do_stream = should_stream(output_format, _stdout_is_tty())
    # #EXT-045-REQ-1 End
    text, code = _run_one_shot(request, session_id, output_format, max_turns, name_to_set, do_stream)
    print(text)
    return code
    # #EXT-043-REQ-3 End
    # #EXT-043-REQ-1 End


if __name__ == "__main__":
    raise SystemExit(main())

