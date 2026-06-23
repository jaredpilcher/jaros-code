"""Agentic master loop (EXT-009): the missing AGENT that WIELDS the tools.

jaros-code has the tools (fix, find, run, refactor, build, locate, ...) but a human won't run
them by hand. This is the Claude-Code-style master loop — the 'nO' single-threaded loop plus a
TodoWrite-style working memory — on the small local model: from ONE natural-language request the
planner lays out a TODO, the loop executes each step with the DETERMINISTIC tools, OBSERVES the
result, and REPLANS when a step fails (plan -> act -> observe -> replan). Two-plane discipline:
the model only PLANS/REPLANS (inert Decisions); the tools ACT (deterministic, test-gated).
Planning quality is capped by the 2B; execution is reliable because the tools are.

The planner is INJECTABLE so the loop mechanics are deterministically testable without the model;
the default planner is the gemma planner_agent.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

_KNOWN = {"find", "read", "run", "fix", "edit", "build"}


@dataclass
class Step:
    action: str
    arg: str = ""
    status: str = "pending"          # pending | done | failed
    observation: str = ""


def _editor_for(fname: str) -> str:
    """Map a file to the right Jaros specialist editor agent — so the loop WIELDS the agent swarm
    (EXT-002 specialists) rather than one generic editor."""
    name = Path(fname).name
    if name == "Dockerfile" or name.endswith(".dockerfile"):
        return "dockerfile_editor_agent.py"
    ext = Path(fname).suffix.lower()
    if ext == ".md":
        return "markdown_editor_agent.py"
    if ext in (".yaml", ".yml", ".ini", ".cfg", ".toml"):
        return "config_editor_agent.py"
    return "editor_agent.py"


_SKIP = {".git", "__pycache__", ".venv", "node_modules", ".jaros-data", "datasets"}


def repo_files(cwd: str, limit: int = 40) -> list[str]:
    """The repo's .py files, relative — GROUNDING for the planner so it references files that
    actually EXIST instead of hallucinating names (the agentic-eval finding). Claude Code's
    planner sees the repo; this is the small-model analogue."""
    root = Path(cwd)
    out = []
    for p in root.rglob("*.py"):
        if any(s in p.parts for s in _SKIP):
            continue
        try:
            out.append(p.relative_to(root).as_posix())
        except ValueError:
            out.append(p.name)
    return sorted(out)[:limit]


def _ground(request: str, cwd: str) -> str:
    """Prefix the request with the real file list so the planner's read/find/edit args are real."""
    files = repo_files(cwd)
    return (f"Files in the repo: {', '.join(files)}\n\n{request}") if files else request


def _default_planner(request: str) -> list[Step]:
    """Plan via the gemma planner_agent (inert plan over the verb set); empty on failure."""
    from harness.coding_loop import build_llm, _load_agent
    [d] = _load_agent("planner_agent.py", build_llm()).decide({"request": request})
    return [Step(s.get("action", ""), s.get("arg", "")) for s in d.payload.get("plan", [])]


# #EXT-009-REQ-1 Start
def execute_step(step: Step, cwd: str) -> tuple[bool, str]:
    """Run one step's tool, returning (ok, observation). Side effects go through the tool plane
    (deterministic tools) or a specialist agent's gated code.write_file — never raw model output."""
    a, arg = step.action, (step.arg or "").strip()
    if a == "edit":                                  # route file-edits to the right SPECIALIST
        if ":" not in arg:
            return (False, "edit needs '<file>: <instruction>'")
        from harness.coding_loop import Runtime, build_llm, _load_agent
        fname, _, instr = arg.partition(":")
        fname, instr = fname.strip(), instr.strip()
        p = Path(cwd) / fname
        content = p.read_text(encoding="utf-8") if p.is_file() else ""
        agent_file = _editor_for(fname)
        [d] = _load_agent(agent_file, build_llm()).decide(
            {"path": str(p), "content": content, "instruction": instr, "feedback": ""})
        if d.type != "code.write_file":
            return (False, f"{agent_file.replace('_agent.py', '')} produced no edit")
        Runtime().apply(d)                           # two-plane: the tool performs the write
        return (True, f"edited {fname} via {agent_file.replace('_agent.py', '')}")
    if a == "build":                                 # generative spine
        from harness.intent_loop import build_in_dir
        parts = arg.split(None, 1)
        if len(parts) < 2:
            return (False, "build needs '<func> <intent>'")
        func, intent = parts[0].rstrip(":"), parts[1]
        r = build_in_dir(cwd, intent, f"{func}.py", func)
        return (bool(r["self_pass"]), r["note"])
    if a == "find":
        from harness.navigate import find_usages
        us = find_usages(cwd, arg)
        return (bool(us), f"{len(us)} usage(s) of {arg}" if us else f"no usages of {arg}")
    if a == "read":
        p = Path(cwd) / arg
        if not p.is_file():
            return (False, f"{arg}: not found")
        return (True, f"read {arg} ({len(p.read_text(encoding='utf-8').splitlines())} lines)")
    if a == "run":
        try:
            r = subprocess.run(arg or "python -m pytest -q", cwd=cwd, shell=True,
                               capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return (False, "tests fail (timed out after 60s)")   # slow suite -> non-green, not a crash
        return (r.returncode == 0, "tests pass" if r.returncode == 0 else "tests fail")
    if a == "fix":
        from harness.multi_file import multi_file_fix
        tf = next((f for f in os.listdir(cwd) if f.startswith("test") and f.endswith(".py")), "")
        res = multi_file_fix(cwd, "python -m pytest -q", arg or "fix the failing test",
                             str(Path(cwd) / tf) if tf else "")
        return (bool(res.get("solved")), res.get("note", ""))
    return (False, f"unknown action '{a}'")


def agent_loop(request: str, cwd: str, *, planner: Callable[[str], list[Step]] | None = None,
               max_steps: int = 8, verbose: bool = False) -> dict:
    """plan -> act -> observe -> replan, with a TODO working-memory. Returns {todo, done,
    steps_run}. On a failed step, REPLAN the remaining work given progress so far (the observe->
    replan cycle that the one-shot /plan lacks). max_steps bounds total tool calls."""
    plan = planner or _default_planner
    todo: list[Step] = plan(_ground(request, cwd))
    if not todo:
        return {"todo": [], "done": False, "steps_run": 0, "note": "planner produced no plan"}
    steps_run = 0
    while steps_run < max_steps:
        pending = next((s for s in todo if s.status == "pending"), None)
        if pending is None:
            break
        ok, obs = execute_step(pending, cwd)
        pending.status = "done" if ok else "failed"
        pending.observation = obs
        steps_run += 1
        if verbose:
            print(f"  [{pending.status}] {pending.action} {pending.arg} -> {obs}", flush=True)
        if not ok and steps_run < max_steps:                 # OBSERVE -> REPLAN the rest
            progress = "; ".join(f"{s.action} {s.arg}: {s.observation}"
                                 for s in todo if s.status != "pending")
            todo.extend(plan(_ground(f"{request}\nProgress: {progress}\nThe last step failed; "
                                     f"plan the remaining steps to finish the request.", cwd)))
    return {"todo": [asdict(s) for s in todo],
            "done": all(s.status == "done" for s in todo), "steps_run": steps_run}
# #EXT-009-REQ-1 End
