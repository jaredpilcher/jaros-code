"""EXT-004 multi-step: deterministic parsing/validation of the planner's output (the model
call is separate)."""
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_spec = importlib.util.spec_from_file_location(
    "planner_agent", Path(__file__).resolve().parents[1] / ".jaros-data" / "agents" / "planner_agent.py")
planner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(planner)


def test_parse_plan_basic():
    raw = '[{"action": "run", "arg": "tests"}, {"action": "fix", "arg": "the bug"}]'
    plan = planner.parse_plan(raw)
    assert plan == [{"action": "run", "arg": "tests"}, {"action": "fix", "arg": "the bug"}]


def test_parse_plan_strips_fences_and_prose():
    raw = 'Here is the plan:\n```json\n[{"action":"find","arg":"x"}]\n```\nDone.'
    assert planner.parse_plan(raw) == [{"action": "find", "arg": "x"}]


def test_parse_plan_drops_unknown_verbs():
    raw = '[{"action": "deploy", "arg": "prod"}, {"action": "read", "arg": "main.py"}]'
    assert planner.parse_plan(raw) == [{"action": "read", "arg": "main.py"}]  # deploy dropped


def test_parse_plan_garbage_is_empty():
    assert planner.parse_plan("I cannot help with that") == []
    assert planner.parse_plan("") == []


def test_is_multistep_routing():
    from harness.cli import JcodeCli
    ms = JcodeCli._is_multistep
    # multi-action -> route to the structured agent (REQ-7)
    assert ms("fix the bug and run the tests")
    assert ms("implement factorial then verify")
    assert ms("find the bug, fix it and run the tests")
    # single-action -> fall through to the orchestrator's one-action routing
    assert not ms("fix foo.py")
    assert not ms("find the login handler")
    assert not ms("show me the status")


def test_multistep_routes_to_structured_agent():
    """EXT-009 REQ-7: a multi-action plain request routes to the STRUCTURED agent (spec_driven_loop
    via cmd_agent — which also checkpoints for /undo), NOT the old free-form planner (cmd_plan)."""
    from harness.cli import JcodeCli
    calls = []

    class Stub:
        _is_multistep = JcodeCli._is_multistep

        def cmd_agent(self, line):
            calls.append(("agent", line))
            return "ok"

        def cmd_plan(self, line):
            calls.append(("plan", line))
            return "ok"

    out = JcodeCli.handle(Stub(), "fix the bug and run the tests")
    assert calls == [("agent", "fix the bug and run the tests")]   # structured agent, not the planner
    assert "structured flow" in out


def test_route_intent():
    from harness.cli import JcodeCli
    ri = JcodeCli._route_intent
    # deterministic refactor/nav fast-path (no 2B call)
    assert ri("rename foo to bar") == ("rename", "foo bar")
    assert ri("rename oldName into newName") == ("rename", "oldName newName")
    assert ri("move helper from a.py to b.py") == ("move", "helper a.py b.py")
    assert ri("find usages of build_repo_map") == ("usages", "build_repo_map")
    assert ri("references to parse_plan") == ("usages", "parse_plan")
    assert ri("where is fix_loop used") == ("usages", "fix_loop")
    assert ri("tell me about fix_loop") == ("about", "fix_loop")
    assert ri("callers of fix_loop") == ("callers", "fix_loop")
    assert ri("what calls build_repo_map") == ("callers", "build_repo_map")
    assert ri("definition of build_repo_map") == ("defn", "build_repo_map")
    assert ri("where is fix_loop defined") == ("defn", "fix_loop")
    assert ri("find dead code") == ("deadcode", "")
    assert ri("any unused functions?") == ("deadcode", "")
    assert ri("show the repo map") == ("map", "")
    # unrelated requests fall through (None) -> orchestrator routes them
    assert ri("fix foo.py") is None
    assert ri("implement a factorial function") is None
    assert ri("what is the status") is None
