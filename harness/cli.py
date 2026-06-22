"""Claude-Code-like interactive CLI (EXT-004).

A slash-command REPL over the Jaros runtime, modelled on Claude Code's terminal UX.
It is also how several single-purpose agents/tools get WIRED into real use: /find
drives the navigator agent -> fs.grep, /run drives the commander agent -> shell.exec
(safety-gated), /grep /ls /read /symbols drive the read tools. Every command routes a
Decision through the same gate + executor as everything else — the CLI never bypasses
the two planes.

Commands (Claude-Code-style):
  /help                         list commands
  /status                       model + latest pass rate + census
  /agents  /tools               the live fleet/catalog
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
  /build <func> <intent>        generative: write tests from intent, then implement (EXT-008)
  /agent <request>              agentic loop: plan -> act -> observe -> replan over the tools (EXT-009)
  /undo                         revert the last /agent run (restore the pre-run checkpoint)
  /remember <note>              save a convention/learning to project memory (.jcode/memory.md)
  /memory                       show the project memory
  /locate                       run tests + pinpoint the fault to file:line:function (deepest first)
  /deadcode [path]              public symbols referenced nowhere (dead-code candidates)
  /clear  /quit
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class JcodeCli:
    """Slash-command dispatcher; each handler returns text to print."""

    def __init__(self) -> None:
        os.environ.setdefault("JAROS_LLM_PROVIDER", "ollama")
        os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")
        from harness.coding_loop import Runtime, build_llm, _load_agent
        from jaros.core import create_decision
        self._mk = create_decision
        self.rt = Runtime()
        self.llm = build_llm()
        self._load_agent = _load_agent
        self.model = os.environ.get("OLLAMA_MODEL", "gemma2:2b")

    # -- helpers -----------------------------------------------------------
    def _tool(self, dtype: str, payload: dict):
        return self.rt.apply(self._mk(id=f"cli-{uuid.uuid4().hex}", source="cli",
                                      type=dtype, payload=payload))

    # -- commands ----------------------------------------------------------
    def cmd_help(self, _arg: str) -> str:
        return __doc__.split("Commands (Claude-Code-style):", 1)[1].rstrip()

    def cmd_status(self, _arg: str) -> str:
        from harness.report import build_report, census
        rep = build_report()
        c = census()
        return (f"model: {self.model} (ollama, local)\n"
                f"latest: {rep.get('headline','(no eval yet)')}\n"
                f"census: agents={c['agents']} tools={c['tools']} capabilities={c['capabilities']} "
                f"evals={c['evals']}+{c['harnessEvals']} specs={c['specs']}")

    def cmd_agents(self, _arg: str) -> str:
        d = ROOT / ".jaros-data" / "agents"
        return "agents: " + ", ".join(sorted(p.stem for p in d.glob("*.py") if not p.name.startswith("_")))

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
        parts = arg.split()
        if not parts:
            return "usage: /grep <pattern> [path]"
        out = self._tool("fs.grep", {"pattern": parts[0], "path": parts[1] if len(parts) > 1 else "."})
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
        out = self._tool("fs.find", {"pattern": parts[0], "path": parts[1] if len(parts) > 1 else "."})
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
        r = multi_file_fix(".", testcmd, instr, test_file, max_iters=3, verbose=True)
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
        return rename_symbol(".", bits[0], bits[1])["note"]

    def cmd_move(self, arg: str) -> str:
        """Test-gated move refactor (EXT-003): move a top-level symbol to another module; the
        source re-exports it so importers keep working, and it reverts if the suite goes red."""
        bits = arg.split()
        if len(bits) < 3:
            return "usage: /move <symbol> <from_file> <to_file>"
        from harness.refactor import move_symbol
        return move_symbol(".", bits[0], bits[1], bits[2])["note"]

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
        """Generative build (EXT-008): turn an intent into a working function + its OWN tests in
        the current dir — the system writes tests from the intent, then implements against them
        (test-writer grain + fix_loop). The generative counterpart to /fix. Wires the EXT-008
        spine (build_from_intent) into the CLI. Usage: /build <func_name> <intent>."""
        bits = arg.strip().split(None, 1)
        if len(bits) < 2 or not bits[0].isidentifier():
            return "usage: /build <func_name> <intent>   e.g. /build is_prime check if a number is prime"
        func, intent = bits[0], bits[1]
        from harness.intent_loop import build_in_dir
        r = build_in_dir(".", intent, f"{func}.py", func)
        return f"[build {'OK' if r['self_pass'] else 'partial'}] {r['note']}\n  files: {', '.join(r['files'])}"

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
        r = spec_driven_loop(arg, ".")
        status = "SOLVED" if r["solved"] else "unsolved"
        note = f" — {r['note']}" if r.get("note") else ""
        return f"agent [{r['flow']} flow]: {status}{note}\n  (/undo to revert this run)"

    def cmd_remember(self, arg: str) -> str:
        """Project memory (EXT-009 REQ-3): append a note/convention to .jcode/memory.md — persists
        across runs (Claude Code's CLAUDE.md analog, for jcode). Wires harness/project_memory.py."""
        if not arg.strip():
            return "usage: /remember <note or convention>"
        from harness.project_memory import append_memory
        return f"remembered -> {append_memory('.', arg)}"

    def cmd_memory(self, _arg: str) -> str:
        """Show the project memory (.jcode/memory.md)."""
        from harness.project_memory import read_memory
        m = read_memory(".")
        return m.rstrip() if m.strip() else "(no project memory yet — add one with /remember <note>)"

    def cmd_undo(self, _arg: str) -> str:
        """Revert the last /agent run (EXT-009 REQ-7): restore the repo snapshot taken before it —
        Claude Code's checkpoints. Session-scoped (the most recent /agent run)."""
        snap = getattr(self, "_agent_snapshot", None)
        if not snap:
            return "nothing to undo (no /agent run this session)"
        from harness.multi_file import _restore
        _restore(snap)
        self._agent_snapshot = None
        return f"reverted the last agent run ({len(snap)} files restored)"

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
        import subprocess
        from harness.multi_file import localize_fault
        try:
            r = subprocess.run("python -m pytest -q", cwd=".", shell=True,
                               capture_output=True, text=True, timeout=60)
        except Exception as e:
            return f"locate: could not run tests: {e}"
        if r.returncode == 0:
            return "tests pass — nothing to localize"
        frames = localize_fault(r.stdout + r.stderr)
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
                r = multi_file_fix(".", "python -m pytest -q", a or arg, test_file, verbose=False)
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

    def _nl_fix(self, request: str, arg: str) -> str:
        """Natural-language fix. If the request names a specific file, fix that file; if it
        names NONE (e.g. 'fix the failing tests'), fall back to the multi-file fixer, which
        LOCATES the faulty file(s) across the repo. The branch is a deterministic file-token
        check — no fragile single-vs-repo judgement by the model."""
        m = re.search(r"[\w./\\-]+\.\w+", arg) or re.search(r"[\w./\\-]+\.\w+", request)
        if not m:   # no file named -> locate it across the repo
            import os
            from harness.multi_file import multi_file_fix
            test_file = next((f for f in os.listdir(".") if f.startswith("test") and f.endswith(".py")), "")
            r = multi_file_fix(".", "python -m pytest -q", request, test_file, max_iters=3, verbose=True)
            where = f" (fixed {', '.join(r['fixed'])})" if r.get("fixed") else ""
            return f"{'solved' if r['solved'] else 'not solved'}{where} — multi-file"
        from harness.coding_loop import fix_loop
        res = fix_loop(m.group(0), request, "python -m pytest -q", max_iters=3, verbose=True)
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

    def handle(self, line: str) -> str:
        """Top-level: slash commands run directly; plain language is ROUTED — first a
        deterministic intent fast-path (refactor/nav phrasings), then the orchestrator agent."""
        line = line.strip()
        if not line:
            return ""
        if line.startswith("/"):
            return self.dispatch(line)
        if self._is_multistep(line):   # multi-action plain request -> the STRUCTURED agent (REQ-7)
            # spec_driven_loop beat the free-form planner 3/3 vs 2/3; it also checkpoints (/undo).
            return "\033[2m[agent → structured flow]\033[0m\n" + self.cmd_agent(line)
        intent = self._route_intent(line)   # deterministic refactor/nav routing (no 2B call)
        if intent:
            action, arg = intent
            return f"\033[2m[intent → /{action} {arg}]\033[0m\n" + getattr(self, "cmd_" + action)(arg)
        orch = self._load_agent("orchestrator_agent.py", self.llm)
        [d] = orch.decide({"request": line})
        action, arg = d.payload.get("action", "help"), d.payload.get("arg", "")
        banner = f"\033[2m[orchestrator → {action} {arg}]\033[0m"
        if action == "fix":
            return banner + "\n" + self._nl_fix(line, arg)
        handler = getattr(self, "cmd_" + ("ls" if action == "list" else action), self.cmd_help)
        return banner + "\n" + handler(arg)

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
        if handler is None:
            return f"unknown command {head!r}. Try /help."
        return handler(arg)


def repl() -> int:
    """Interactive Claude-Code-like prompt loop."""
    cli = JcodeCli()
    print(f"\n\033[1m jaros-code \033[0m  local coding harness on {cli.model} (gemma2:2b)")
    print("  slash-command REPL — type /help, /quit to exit\n")
    while True:
        try:
            line = input("\033[36mjcode›\033[0m ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line.strip() in ("/quit", "/exit", "/q"):
            return 0
        if line.strip() == "/clear":
            print("\033[2J\033[H", end="")
            continue
        out = cli.handle(line)
        if out:
            print(out)


def main() -> int:
    """Entry point: a one-shot request if given as args, else the interactive REPL.

      python -m harness.cli                 # interactive REPL (Claude-Code-like)
      python -m harness.cli /status         # run one command and exit
      python -m harness.cli "fix the bug in foo.py"   # one plain-language request
    """
    import sys
    args = sys.argv[1:]
    if args:
        print(JcodeCli().handle(" ".join(args)))
        return 0
    return repl()


if __name__ == "__main__":
    raise SystemExit(main())

