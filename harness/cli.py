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
  /find <term>                  navigator agent -> fs.grep (locate code)
  /grep <pattern> [path]        fs.grep tool
  /ls [path]                    fs.list tool
  /read <file>                  fs.read tool
  /symbols <file>               py.symbols tool
  /run <task>                   commander agent -> shell.exec (gated)
  /fix <file> :: <instr> :: <testcmd>   run the edit->test->judge loop
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
                f"census: agents={c['agents']} tools={c['tools']} evals={c['evals']} specs={c['specs']}")

    def cmd_agents(self, _arg: str) -> str:
        d = ROOT / ".jaros-data" / "agents"
        return "agents: " + ", ".join(sorted(p.stem for p in d.glob("*.py") if not p.name.startswith("_")))

    def cmd_tools(self, _arg: str) -> str:
        d = ROOT / ".jaros-data" / "tools"
        return "tools: " + ", ".join(sorted(p.stem for p in d.glob("*.py") if not p.name.startswith("_")))

    def cmd_report(self, _arg: str) -> str:
        from harness.report import write_report
        return write_report()["markdown"]

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

    def _nl_fix(self, request: str, arg: str) -> str:
        """Natural-language fix: find a file token, use the request as the instruction."""
        m = re.search(r"[\w./\\-]+\.\w+", arg) or re.search(r"[\w./\\-]+\.\w+", request)
        if not m:
            return ("orchestrator chose 'fix' but I couldn't spot a file. "
                    "Try: /fix <file> :: <instruction> :: <test command>")
        from harness.coding_loop import fix_loop
        res = fix_loop(m.group(0), request, "python -m pytest -q", max_iters=3, verbose=True)
        return f"{'solved' if res.success else 'not solved'} in {res.attempts} attempt(s)"

    def handle(self, line: str) -> str:
        """Top-level: slash commands run directly; plain language is ROUTED by the
        orchestrator agent, which decides which agent/tool serves the request."""
        line = line.strip()
        if not line:
            return ""
        if line.startswith("/"):
            return self.dispatch(line)
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

