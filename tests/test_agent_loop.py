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


def test_editor_for_routing():
    from harness.agent_loop import _editor_for
    assert _editor_for("README.md") == "markdown_editor_agent.py"
    assert _editor_for("Dockerfile") == "dockerfile_editor_agent.py"
    assert _editor_for("settings.yaml") == "config_editor_agent.py"
    assert _editor_for("conf.ini") == "config_editor_agent.py"
    assert _editor_for("app.py") == "editor_agent.py"


def test_agent_checkpoint_undo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "x.py"
    f.write_text("original\n", encoding="utf-8")
    from harness.cli import JcodeCli
    from harness.multi_file import _snapshot
    cli = JcodeCli()
    cli._agent_snapshot = _snapshot(".")          # simulate /agent's pre-run checkpoint
    f.write_text("MODIFIED\n", encoding="utf-8")   # simulate the agent editing the file
    out = cli.cmd_undo("")
    assert "restored" in out.lower()
    assert f.read_text(encoding="utf-8") == "original\n"
    assert "nothing to undo" in cli.cmd_undo("").lower()
