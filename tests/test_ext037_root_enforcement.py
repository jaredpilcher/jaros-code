"""EXT-037 / REQ-1 (TASK-2) -- root-jail ENFORCEMENT: the two real write paths that now

thread a project ``root`` so ``path_jail`` actually fires in production, instead of
sitting dormant behind an unused ``root`` payload key (TASK-1's honest gap).

Covers:
  (a) ``harness.coding_loop.Runtime`` -- an opt-in ``root`` stamped onto every write
      Decision just before ``validate_decision`` (the Jaros-native gate/executor/log
      choke point every write Decision passes through).
  (b) ``harness.system_builder.build_system`` / ``modify_system`` -- the sentence-to-
      system product path, which writes module files directly (bypassing the Decision
      layer) so it gets its own direct ``path_jail`` guard.
  (c) ``harness.agent_loop.execute_step``'s ``edit`` action -- the one live interactive
      write path where the loop's ``cwd`` is already the unambiguous project root.

Offline, deterministic, no network/Jetson: pure filesystem + canned-LLM checks.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from jaros.core import create_decision

# #EXT-037-REQ-1 Start


# --- (a) Runtime(root=...) stamps a write Decision -------------------------------------

def _runtime(tmp_path, root=None):
    from harness.coding_loop import Runtime
    return Runtime(data_dir=tmp_path / "state", root=root)


def test_runtime_root_rejects_out_of_root_write(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    outside = tmp_path / "outside.py"
    rt = _runtime(tmp_path, root=str(proj))
    d = create_decision(id="t1", source="test", type="code.write_file",
                        payload={"path": str(outside), "content": "leak\n"})
    with pytest.raises(RuntimeError, match="root"):
        rt.apply(d)
    assert not outside.exists()


def test_runtime_root_accepts_in_root_write(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    inside = proj / "inside.py"
    rt = _runtime(tmp_path, root=str(proj))
    d = create_decision(id="t2", source="test", type="code.write_file",
                        payload={"path": str(inside), "content": "ok\n"})
    out = rt.apply(d)
    assert out["applied"] is True
    assert inside.read_text(encoding="utf-8") == "ok\n"


def test_runtime_without_root_is_unchanged(tmp_path):
    """No regression: the many existing Runtime() callers that never pass `root` see
    exactly the old, unjailed behavior -- a write anywhere still succeeds."""
    elsewhere = tmp_path / "anywhere" / "file.py"
    rt = _runtime(tmp_path, root=None)
    d = create_decision(id="t3", source="test", type="code.write_file",
                        payload={"path": str(elsewhere), "content": "ok\n"})
    out = rt.apply(d)
    assert out["applied"] is True
    assert elsewhere.read_text(encoding="utf-8") == "ok\n"


def test_runtime_root_does_not_override_explicit_payload_root(tmp_path):
    """A caller that already supplies its own `root` in the payload keeps it -- Runtime
    only fills in a MISSING key, never overrides an explicit one."""
    proj_a = tmp_path / "a"
    proj_a.mkdir()
    proj_b = tmp_path / "b"
    proj_b.mkdir()
    target = proj_b / "f.py"
    rt = _runtime(tmp_path, root=str(proj_a))
    d = create_decision(id="t4", source="test", type="code.write_file",
                        payload={"path": str(target), "content": "ok\n", "root": str(proj_b)})
    out = rt.apply(d)  # explicit root (proj_b) contains target -> accepted
    assert out["applied"] is True


# --- (b) system_builder: build_system / modify_system reject an escaping module name --

_PLAN_ESCAPE_JSON = """{
  "modules": [
    {"name": "../evil.py", "responsibility": "escape",
     "exports": [{"name": "f", "signature": "def f():"}], "imports": []}
  ],
  "entrypoint": "../evil.py",
  "acceptance": "python ../evil.py runs"
}"""


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _EscapePlanLlm:
    """Plans a single module whose NAME escapes root -- proves the ASSEMBLE-step jail,
    never reaches the acceptance-checklist stage (assembly fails first)."""

    def complete(self, request):
        prompt = request.prompt
        if "build PLAN" in prompt:
            return _Resp(_PLAN_ESCAPE_JSON)
        if "COMPLETE Python module" in prompt:
            return _Resp("def f():\n    return 1\n")
        return _Resp("")


def test_build_system_rejects_escaping_module_name(tmp_path):
    from harness.system_builder import build_system

    root = tmp_path / "built"
    result = build_system("a tiny system", root, llm=_EscapePlanLlm())

    assert result["shipped"] is False
    assert "refused" in result["note"]
    # never written outside `built/` (would have landed at tmp_path/evil.py)
    assert not (tmp_path / "evil.py").exists()
    assert not (root / "evil.py").exists()


def test_modify_system_rejects_escaping_module_name(tmp_path):
    from harness.system_builder import modify_system

    root = tmp_path / "built"
    # the pre-existing `modules` dict itself carries an escaping key -- the very first
    # (baseline-assemble) write must refuse it before any model call.
    result = modify_system({"../evil.py": "x = 1\n"}, "anything", root, llm=object())

    assert result["applied"] is False
    assert "refused" in result["note"]
    assert not (tmp_path / "evil.py").exists()


def test_build_system_still_ships_in_root(tmp_path):
    """No regression: a normal, in-root plan still assembles and ships fine."""
    from harness.system_builder import build_system

    class _OkLlm:
        def complete(self, request):
            prompt = request.prompt
            if "build PLAN" in prompt:
                return _Resp("""{
  "modules": [
    {"name": "helper.py", "responsibility": "add",
     "exports": [{"name": "add", "signature": "def add(a, b):"}], "imports": []}
  ],
  "entrypoint": "helper.py",
  "acceptance": "add(1, 2) == 3"
}""")
            if "ACCEPTANCE CHECKS" in prompt:
                return _Resp('[{"name": "adds", "code": "from helper import add\\nassert add(1, 2) == 3\\n"}]')
            if "COMPLETE Python module" in prompt:
                return _Resp("def add(a, b):\n    return a + b\n")
            return _Resp("")

    root = tmp_path / "built"
    result = build_system("adder", root, llm=_OkLlm())
    assert result["shipped"] is True
    assert (root / "helper.py").is_file()


# --- (c) agent_loop.execute_step: the `edit` action threads `cwd` as root --------------

def test_execute_step_edit_refuses_escaping_target(tmp_path, monkeypatch):
    import harness.coding_loop as cl
    from harness.agent_loop import Step, execute_step

    class _FakeEditor:
        def decide(self, context):
            escaping = str(tmp_path / ".." / "evil.py")
            return [create_decision(
                id="edit-escape", source="editor", type="code.write_file",
                payload={"path": escaping, "content": "pwned\n"})]

    monkeypatch.setattr(cl, "_load_agent", lambda filename, llm: _FakeEditor())
    with pytest.raises(RuntimeError, match="root"):
        execute_step(Step("edit", "../evil.py: pwn it"), str(tmp_path))
    assert not (tmp_path.parent / "evil.py").exists()


def test_execute_step_edit_still_succeeds_in_cwd(tmp_path, monkeypatch):
    """No regression: an in-cwd edit still applies (mirrors the existing
    test_execute_step_edit_accepts_apply_patch/search_replace coverage)."""
    import harness.coding_loop as cl
    from harness.agent_loop import Step, execute_step

    f = tmp_path / "m.py"
    f.write_text("x = 1\n", encoding="utf-8")

    class _FakeEditor:
        def decide(self, context):
            return [create_decision(
                id="edit-ok", source="editor", type="code.write_file",
                payload={"path": str(f), "content": "x = 2\n"})]

    monkeypatch.setattr(cl, "_load_agent", lambda filename, llm: _FakeEditor())
    ok, obs = execute_step(Step("edit", "m.py: change x"), str(tmp_path))
    assert ok, obs
    assert f.read_text(encoding="utf-8") == "x = 2\n"
# #EXT-037-REQ-1 End
