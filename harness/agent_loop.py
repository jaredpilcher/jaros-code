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

_KNOWN = {"find", "read", "run", "fix"}


@dataclass
class Step:
    action: str
    arg: str = ""
    status: str = "pending"          # pending | done | failed
    observation: str = ""


def _default_planner(request: str) -> list[Step]:
    """Plan via the gemma planner_agent (inert plan over the verb set); empty on failure."""
    from harness.coding_loop import build_llm, _load_agent
    [d] = _load_agent("planner_agent.py", build_llm()).decide({"request": request})
    return [Step(s.get("action", ""), s.get("arg", "")) for s in d.payload.get("plan", [])]


def execute_step(step: Step, cwd: str) -> tuple[bool, str]:
    """Run one step's DETERMINISTIC tool, returning (ok, observation). The model never runs here."""
    a, arg = step.action, (step.arg or "").strip()
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
        r = subprocess.run(arg or "python -m pytest -q", cwd=cwd, shell=True,
                           capture_output=True, text=True, timeout=60)
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
    todo: list[Step] = plan(request)
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
            todo.extend(plan(f"{request}\nProgress: {progress}\nThe last step failed; "
                             f"plan the remaining steps to finish the request."))
    return {"todo": [asdict(s) for s in todo],
            "done": all(s.status == "done" for s in todo), "steps_run": steps_run}
