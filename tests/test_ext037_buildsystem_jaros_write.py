"""EXT-037 REQ-11: harness/system_builder.py's `/buildsystem`/`/modifysystem` writes are
Jaros-native (Tenet 1).

Mirrors the proven REQ-9/REQ-10 test pattern (`tests/test_ext037_refactor_jaros_write.py`,
`tests/test_ext037_fixrepo_jaros_write.py`): a fake recording runtime proves every write is
routed through a real `code.write_file` Decision, the existing local `path_jail` pre-check is
proven unchanged regardless of `runtime`, a real `harness.coding_loop.Runtime` proves the write
actually lands through the gate + hash-chain log, and `runtime=None` (the default) proves
byte-identical behavior for every pre-existing eval/test/suite caller. Fully offline/deterministic
-- a canned stub `llm` (the same `.complete(LlmRequest) -> .text` convention
`tests/test_ext036_system_builder.py` uses) drives every `build_system`/`modify_system` call,
never reaching the Jetson.
"""
from __future__ import annotations

import os
import re

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.cli import JcodeCli
from harness.system_builder import (
    _jailed_write,
    build_system,
    build_system_best_of_k,
    modify_system,
)

_MODULE_NAME_RE = re.compile(r"module `([^`]+)`")

SPEC = "A tiny two-module system: a helper module that adds two numbers, and a CLI that prints the sum."

PLAN_JSON = """{
  "modules": [
    {"name": "helper.py", "responsibility": "define add(a, b)",
     "exports": [{"name": "add", "signature": "def add(a, b):"}], "imports": []},
    {"name": "cli.py", "responsibility": "CLI entrypoint that prints the sum",
     "exports": [{"name": "main", "signature": "def main():"}], "imports": ["helper.py"]}
  ],
  "entrypoint": "cli.py",
  "acceptance": "python cli.py prints 3"
}"""

HELPER_OK = "def add(a, b):\n    return a + b\n"
CLI_OK = (
    "from helper import add\n\n\n"
    "def main():\n    print(add(1, 2))\n\n\n"
    "if __name__ == '__main__':\n    main()\n"
)

CHECKLIST_PASSING = """[
  {"name": "adds correctly", "code": "from helper import add\\nassert add(1, 2) == 3\\n"}
]"""


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _CannedLlm:
    """A clean, always-passing two-module build -- mirrors `tests/test_ext036_system_builder.py`'s
    `_CannedLlm` (same `.complete(LlmRequest) -> .text` convention), simplified: no syntax repair
    needed, so a `build_system`/`modify_system` call here always ships + is done."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "build PLAN" in prompt:
            return _Resp(PLAN_JSON)
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp(CHECKLIST_PASSING)
        if "MODIFICATION TARGET" in prompt:
            return _Resp('["helper.py"]')
        if "APPLY MODIFICATION" in prompt:
            return _Resp("def add(a, b):\n    return a + b  # modified\n")
        if "COMPLETE Python module" in prompt:
            m = _MODULE_NAME_RE.search(prompt)
            name = m.group(1) if m else None
            return _Resp({"helper.py": HELPER_OK, "cli.py": CLI_OK}.get(name, ""))
        return _Resp("")


class _FakeApplyRuntime:
    """Records every Decision passed to `.apply()` -- does NOT touch the filesystem itself, so a
    test using it proves the CALLER built a `code.write_file` Decision without depending on the
    real Jaros gate/executor plumbing."""

    def __init__(self) -> None:
        self.applied: list = []

    def apply(self, decision):
        self.applied.append(decision)
        return {"tool": "code.write_file", "path": decision.payload["path"], "applied": True}


class _RejectingRuntime:
    def apply(self, decision):
        raise RuntimeError("gate rejected code.write_file: refused path outside root")


# --- _jailed_write: the single chokepoint -------------------------------------------------------

def test_jailed_write_runtime_builds_write_file_decision(tmp_path):
    rt = _FakeApplyRuntime()
    err = _jailed_write(tmp_path, "mod.py", "print('hi')\n", rt)
    assert err is None
    assert len(rt.applied) == 1
    d = rt.applied[0]
    assert d.type == "code.write_file"
    assert d.payload["root"] == str(tmp_path)
    assert d.payload["content"] == "print('hi')\n"
    assert d.payload["path"] == str(tmp_path / "mod.py")
    # the FAKE runtime never wrote anything to disk -- proves the write really goes THROUGH
    # `runtime`, not a raw Path.write_text alongside it.
    assert not (tmp_path / "mod.py").exists()


def test_jailed_write_runtime_gate_rejection_is_honest_not_a_crash(tmp_path):
    err = _jailed_write(tmp_path, "mod.py", "print('hi')\n", _RejectingRuntime())
    assert err is not None
    assert "failed to write" in err
    assert not (tmp_path / "mod.py").exists()


def test_jailed_write_local_pathjail_rejection_unchanged_regardless_of_runtime(tmp_path):
    """The local `path_jail` pre-check (REQ-1) runs UNCONDITIONALLY first -- an escaping `name`
    is refused with the exact same rejection whether or not a `runtime` is supplied, and no
    Decision is ever built for it."""
    err_none = _jailed_write(tmp_path, "../../evil.py", "pwned\n", None)
    assert err_none is not None
    assert not (tmp_path.parent.parent / "evil.py").exists()

    rt = _FakeApplyRuntime()
    err_rt = _jailed_write(tmp_path, "../../evil.py", "pwned\n", rt)
    assert err_rt is not None
    assert err_rt == err_none  # identical rejection reason regardless of runtime
    assert rt.applied == []  # never even built a Decision for a rejected path
    assert not (tmp_path.parent.parent / "evil.py").exists()


def test_jailed_write_runtime_none_is_byte_identical(tmp_path):
    err = _jailed_write(tmp_path, "mod.py", "print('hi')\n", None)
    assert err is None
    assert (tmp_path / "mod.py").read_text(encoding="utf-8") == "print('hi')\n"


# --- build_system: runtime threaded through ASSEMBLE + the REQ-5 repair loop --------------------

def test_build_system_runtime_none_is_byte_identical(tmp_path):
    root = tmp_path / "built"
    result = build_system(SPEC, root, llm=_CannedLlm())
    assert result["shipped"] is True
    assert result["done"] is True
    assert (root / "helper.py").is_file()
    assert (root / "cli.py").is_file()


def test_build_system_fake_runtime_routes_assemble_through_decisions(tmp_path):
    root = tmp_path / "built"
    rt = _FakeApplyRuntime()
    result = build_system(SPEC, root, llm=_CannedLlm(), runtime=rt)
    # The FAKE runtime never actually writes to disk (by design, see the assertion below), so
    # the acceptance step's real import/run of the assembled modules honestly fails and
    # `done` is False here -- this test's point is that ASSEMBLE genuinely routed through the
    # Decision, not that a non-writing fake produces a full done=True build.
    assert result["shipped"] is True
    assert {"helper.py", "cli.py"} == set(result["modules"])
    paths = {d.payload["path"] for d in rt.applied}
    assert any(p.endswith("helper.py") for p in paths)
    assert any(p.endswith("cli.py") for p in paths)
    for d in rt.applied:
        assert d.type == "code.write_file"
        assert d.payload["root"] == str(root)
    # the FAKE runtime never wrote anything to disk -- assembly genuinely went THROUGH it.
    assert not (root / "helper.py").exists()
    assert not (root / "cli.py").exists()


def test_build_system_real_runtime_records_decision_on_hash_chain(tmp_path):
    from harness.coding_loop import Runtime
    from jaros.state import DecisionLog

    seen_types: list = []
    orig_append_decision = DecisionLog.append_decision

    def _spy_append_decision(self, record):
        seen_types.append(record.get("type"))
        return orig_append_decision(self, record)

    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(DecisionLog, "append_decision", _spy_append_decision)
        root = tmp_path / "built"
        rt = Runtime(data_dir=tmp_path / "state", root=str(root))
        result = build_system(SPEC, root, llm=_CannedLlm(), runtime=rt)

    assert result["shipped"] is True
    assert (root / "helper.py").is_file()
    assert (root / "cli.py").is_file()
    assert "code.write_file" in seen_types


# --- modify_system: runtime threaded through assemble/regenerate/revert -------------------------

def test_modify_system_fake_runtime_routes_writes_through_decisions(tmp_path):
    root = tmp_path / "sys"
    modules = {"helper.py": HELPER_OK, "cli.py": CLI_OK}
    rt = _FakeApplyRuntime()
    result = modify_system(modules, "add a docstring to helper", root, llm=_CannedLlm(), runtime=rt)
    assert result["applied"] is True
    assert len(rt.applied) >= 2  # baseline assembly + the regenerated module
    for d in rt.applied:
        assert d.type == "code.write_file"
        assert d.payload["root"] == str(root)


def test_modify_system_runtime_none_is_byte_identical(tmp_path):
    root = tmp_path / "sys"
    modules = {"helper.py": HELPER_OK, "cli.py": CLI_OK}
    result = modify_system(modules, "add a docstring to helper", root, llm=_CannedLlm())
    assert result["applied"] is True
    assert (root / "helper.py").is_file()


# --- build_system_best_of_k: per-attempt raw, final winner-assembly through runtime --------------

def test_best_of_k_final_assembly_uses_runtime_while_attempts_stay_raw(tmp_path):
    from jaros.state import DecisionLog

    seen_types: list = []
    orig_append_decision = DecisionLog.append_decision

    def _spy_append_decision(self, record):
        seen_types.append(record.get("type"))
        return orig_append_decision(self, record)

    from harness.coding_loop import Runtime

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(DecisionLog, "append_decision", _spy_append_decision)
        root = tmp_path / "winner"
        rt = Runtime(data_dir=tmp_path / "state", root=str(root))
        result = build_system_best_of_k(SPEC, root, llm=_CannedLlm(), k=1, runtime=rt)

    assert result["shipped"] is True
    # the final winner assembly onto the caller's real `root` genuinely went through a real
    # code.write_file Decision, hash-chain logged.
    assert "code.write_file" in seen_types
    assert (root / "helper.py").is_file()
    assert (root / "cli.py").is_file()


def test_best_of_k_runtime_none_is_byte_identical(tmp_path):
    root = tmp_path / "winner"
    result = build_system_best_of_k(SPEC, root, llm=_CannedLlm(), k=1)
    assert result["shipped"] is True
    assert (root / "helper.py").is_file()


# --- CLI wiring: /buildsystem and /modifysystem thread a root-anchored Runtime -------------------

def _stub_cli() -> JcodeCli:
    return JcodeCli()


def test_slash_buildsystem_passes_a_runtime_to_build_system(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen: dict = {}

    def fake_build_system(spec, root, *, llm=None, runtime=None):
        seen["runtime"] = runtime
        return {"modules": {"helper.py": "code"}, "shipped": True, "done": True,
                "unmet": [], "plan": {"entrypoint": "cli.py"}, "note": "DONE"}

    monkeypatch.setattr("harness.system_builder.build_system", fake_build_system)
    cli = _stub_cli()
    out = cli.dispatch("/buildsystem a tiny CLI")
    assert "shipped" in out
    assert seen["runtime"] is not None


def test_slash_modifysystem_passes_a_runtime_to_modify_system(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "sys"
    target.mkdir()
    (target / "helper.py").write_text(HELPER_OK, encoding="utf-8")
    seen: dict = {}

    def fake_modify_system(modules, mod_sentence, root, *, llm=None, runtime=None):
        seen["runtime"] = runtime
        return {"modules": modules, "applied": True, "regressed": [],
                "new_behavior_ok": False, "note": "applied"}

    monkeypatch.setattr("harness.system_builder.modify_system", fake_modify_system)
    cli = _stub_cli()
    out = cli.dispatch(f"/modifysystem {target} :: add a docstring")
    assert "applied" in out.lower()
    assert seen["runtime"] is not None
