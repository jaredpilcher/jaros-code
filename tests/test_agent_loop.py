"""Agentic master loop (EXT-009) — deterministic loop mechanics, planner injected (no model)."""
from harness.agent_loop import Step, agent_loop, execute_step


def test_execute_step_find_read_run(tmp_path):
    (tmp_path / "m.py").write_text("def foo():\n    return 1\n\nx = foo()\n", encoding="utf-8")
    ok, obs = execute_step(Step("find", "foo"), str(tmp_path))
    assert ok and "usage" in obs
    ok, _ = execute_step(Step("read", "m.py"), str(tmp_path))
    assert ok
    ok, _ = execute_step(Step("read", "nope.py"), str(tmp_path))
    assert not ok


def test_agent_loop_runs_plan_to_completion(tmp_path):
    (tmp_path / "m.py").write_text("def foo():\n    return 1\n\nx = foo()\n", encoding="utf-8")
    r = agent_loop("explore foo", str(tmp_path),
                   planner=lambda req: [Step("find", "foo"), Step("read", "m.py")])
    assert r["done"] is True and r["steps_run"] == 2


def test_agent_loop_replans_on_failure(tmp_path):
    (tmp_path / "m.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    calls = {"n": 0}

    def planner(req):
        calls["n"] += 1
        return [Step("read", "m.py")] if "Progress" in req else [Step("read", "missing.py")]

    r = agent_loop("do it", str(tmp_path), planner=planner, max_steps=5)
    assert calls["n"] >= 2  # the failed step triggered a replan
    assert any(s["action"] == "read" and s["arg"] == "m.py" and s["status"] == "done"
               for s in r["todo"])
