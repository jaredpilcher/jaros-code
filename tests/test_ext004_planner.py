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
    # multi-action -> route to /plan
    assert ms("fix the bug and run the tests")
    assert ms("implement factorial then verify")
    assert ms("find the bug, fix it and run the tests")
    # single-action -> fall through to the orchestrator's one-action routing
    assert not ms("fix foo.py")
    assert not ms("find the login handler")
    assert not ms("show me the status")
