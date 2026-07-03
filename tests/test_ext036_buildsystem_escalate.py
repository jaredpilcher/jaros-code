"""EXT-036 TASK-18: wire /buildsystem to the escalating harness (REQ-13).

MEASURED (TASK-13, commit c182c33): the offline escalation core (``build_system_escalating``)
lifts the hard-tier creation ship-rate 25% -> 58% (3/12 -> 7/12) by escalating to
Qwen2.5-Coder-7B ONLY when gemma-4-e2b fails to ship. This file proves the LIVE CLI wiring
(``harness.cli.cmd_buildsystem``): when escalation is genuinely CONFIGURED (a measured
complex-system-build-specialist is registered) it routes through
``harness.system_builder.build_system_escalating`` with a real swap_fn; when it is NOT
configured it falls back to plain ``build_system`` with byte-for-byte the old behavior (no
swap_fn ever constructed).

OFFLINE — no live model, no network, no Jetson. ``harness.cli._buildsystem_escalation_config``
is monkeypatched directly (the honest "is escalation configured" judgment — its own registry
plumbing is exercised separately in ``test_ext036_escalate.py`` via ``ModelRegistry``), and
``harness.system_builder.build_system_escalating`` / ``build_system`` /
``harness.collaborative_solve._http_swap`` are monkeypatched with recording stubs, mirroring
the stubbing patterns used across the other ``tests/test_ext036_*.py`` CLI tests.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

import harness.cli as cli_mod
import harness.collaborative_solve as collab_mod
import harness.system_builder as sb_mod
from harness.cli import JcodeCli

MANAGER_URL = "http://fake-manager:8001"
FALLBACK_ID = "qwen2.5-coder-7b"
PRIMARY_ID = "gemma-4-e2b"

SHIPPED_DONE = {"modules": {"a.py": "code"}, "shipped": True, "done": True, "unmet": [],
                "plan": {"entrypoint": "a.py"}, "note": ""}
NOT_SHIPPED = {"modules": {}, "shipped": False, "done": False, "unmet": [], "plan": None,
               "note": "planner produced no parseable JSON plan"}


@pytest.fixture(autouse=True)
def _isolate_sessions_dir(tmp_path, monkeypatch):
    """Never touch the real .jaros-data/sessions/ from these tests (mirrors the other
    EXT-036 test files)."""
    import harness.session as sess_mod
    monkeypatch.setattr(sess_mod, "SESSIONS_DIR", tmp_path / "_sessions")
    yield


def _configured(monkeypatch) -> None:
    monkeypatch.setattr(cli_mod, "_buildsystem_escalation_config",
                         lambda: (MANAGER_URL, FALLBACK_ID, PRIMARY_ID))


def _not_configured(monkeypatch) -> None:
    monkeypatch.setattr(cli_mod, "_buildsystem_escalation_config", lambda: None)


# --- (a) escalation configured -> calls build_system_escalating with the right wiring -----

def test_configured_calls_build_system_escalating_with_right_kwargs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _configured(monkeypatch)

    calls: list[dict] = []

    def _fake_escalating(spec, root, *, primary_llm, fallback_llm=None, swap_fn=None,
                          fallback_model_id=None, primary_model_id=None):
        calls.append(dict(spec=spec, root=root, primary_llm=primary_llm,
                           fallback_llm=fallback_llm, swap_fn=swap_fn,
                           fallback_model_id=fallback_model_id, primary_model_id=primary_model_id))
        return dict(SHIPPED_DONE, escalated=True, model="fallback")

    build_system_calls: list = []
    monkeypatch.setattr(sb_mod, "build_system_escalating", _fake_escalating)
    monkeypatch.setattr(sb_mod, "build_system", lambda *a, **k: build_system_calls.append(1))

    swap_urls: list[str] = []

    def _fake_http_swap(manager_url):
        swap_urls.append(manager_url)
        def _swap(model_id):
            pass
        return _swap
    monkeypatch.setattr(collab_mod, "_http_swap", _fake_http_swap)

    cli = JcodeCli()
    out = cli.dispatch("/buildsystem a tiny job-queue system")

    assert len(calls) == 1
    call = calls[0]
    assert call["spec"] == "a tiny job-queue system"
    assert call["primary_llm"] is cli.llm
    assert call["fallback_llm"] is cli.llm
    assert call["fallback_model_id"] == FALLBACK_ID
    assert call["primary_model_id"] == PRIMARY_ID
    assert callable(call["swap_fn"])
    assert swap_urls == [MANAGER_URL]
    assert build_system_calls == []   # plain build_system never invoked on this path
    assert "shipped" in out


# --- (b) NOT configured -> falls back to plain build_system, no swap_fn constructed --------

def test_not_configured_falls_back_to_plain_build_system(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _not_configured(monkeypatch)

    escalating_calls: list = []
    monkeypatch.setattr(sb_mod, "build_system_escalating",
                         lambda *a, **k: escalating_calls.append(1))

    plain_calls: list[dict] = []

    def _fake_build_system(spec, root, *, llm=None):
        plain_calls.append(dict(spec=spec, root=root, llm=llm))
        return dict(SHIPPED_DONE)
    monkeypatch.setattr(sb_mod, "build_system", _fake_build_system)

    def _boom_http_swap(manager_url):
        raise AssertionError("swap_fn must never be constructed when unconfigured")
    monkeypatch.setattr(collab_mod, "_http_swap", _boom_http_swap)

    cli = JcodeCli()
    out = cli.dispatch("/buildsystem a tiny job-queue system")

    assert escalating_calls == []
    assert len(plain_calls) == 1
    assert plain_calls[0]["spec"] == "a tiny job-queue system"
    assert plain_calls[0]["llm"] is cli.llm
    assert "shipped" in out


# --- (c) CLI output reflects escalated vs not, and which model shipped --------------------

def test_output_labels_escalated_fallback_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _configured(monkeypatch)
    monkeypatch.setattr(sb_mod, "build_system_escalating",
                         lambda *a, **k: dict(SHIPPED_DONE, escalated=True, model="fallback"))
    monkeypatch.setattr(collab_mod, "_http_swap", lambda url: (lambda model_id: None))

    cli = JcodeCli()
    out = cli.dispatch("/buildsystem a tiny job-queue system")
    assert FALLBACK_ID in out
    assert "(escalated)" in out


def test_output_labels_primary_model_when_not_escalated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _configured(monkeypatch)
    monkeypatch.setattr(sb_mod, "build_system_escalating",
                         lambda *a, **k: dict(SHIPPED_DONE, escalated=False, model="primary"))
    monkeypatch.setattr(collab_mod, "_http_swap", lambda url: (lambda model_id: None))

    cli = JcodeCli()
    out = cli.dispatch("/buildsystem a tiny job-queue system")
    assert PRIMARY_ID in out
    assert "(escalated)" not in out


def test_output_plain_when_not_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _not_configured(monkeypatch)
    monkeypatch.setattr(sb_mod, "build_system", lambda *a, **k: dict(SHIPPED_DONE))

    cli = JcodeCli()
    out = cli.dispatch("/buildsystem a tiny job-queue system")
    assert "via" not in out
    assert "(escalated)" not in out


# --- (d) unreachable-manager / raising-swap path never crashes cmd_buildsystem ------------

def test_raising_swap_never_crashes_cmd_buildsystem(tmp_path, monkeypatch):
    """Uses the REAL build_system_escalating (its own never-raise guarantee is proven in
    test_ext036_escalate.py) with a raising swap_fn and a canned failing `build_system`, and
    just asserts cmd_buildsystem still returns a result instead of propagating an exception."""
    monkeypatch.chdir(tmp_path)
    _configured(monkeypatch)
    monkeypatch.setattr(sb_mod, "build_system", lambda spec, root, *, llm=None: dict(NOT_SHIPPED))

    def _raising_http_swap(manager_url):
        def _swap(model_id):
            raise RuntimeError("jetson unreachable")
        return _swap
    monkeypatch.setattr(collab_mod, "_http_swap", _raising_http_swap)

    cli = JcodeCli()
    out = cli.dispatch("/buildsystem a tiny job-queue system")
    assert isinstance(out, str)
    assert "NOT shipped" in out
    assert PRIMARY_ID in out
    assert "(escalated)" not in out


# --- slash-command dispatch unaffected for other commands ---------------------------------

def test_modifysystem_command_untouched(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _not_configured(monkeypatch)
    cli = JcodeCli()
    out = cli.dispatch("/modifysystem some sentence")
    assert "no system to modify" in out
