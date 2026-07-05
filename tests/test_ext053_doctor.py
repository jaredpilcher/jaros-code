"""EXT-053: `/doctor` deterministic health-check instrument -- fully hermetic. No real network
call, no real subprocess/docker spawn: `harness.llamacpp_client.health`, `subprocess.run`, and
`shutil.which` are all monkeypatched at the `harness.doctor` module level (mirrors how
`tests/test_ext052_background.py` monkeypatches `harness.bg_jobs` functions imported lazily
inside the function under test)."""
from __future__ import annotations

import subprocess

import pytest

import harness.doctor as doctor
import harness.llamacpp_client as llamacpp_client
from harness.cli import JcodeCli, _dispatch_doctor_subcommand
from harness.doctor import DoctorCheck, VALID_STATUSES, render, run_doctor


# --- DoctorCheck / status plumbing -------------------------------------------------------


def test_all_statuses_are_valid_members():
    assert VALID_STATUSES == ("pass", "warn", "fail")


def test_check_helper_falls_back_to_warn_on_bad_status():
    c = doctor._check("x", "not-a-real-status", "detail")
    assert c.status == "warn"


# --- python version -----------------------------------------------------------------------


def test_python_version_pass_when_at_or_above_minimum():
    c = doctor._check_python_version(minimum=(2, 0))
    assert c.status == "pass"


def test_python_version_fail_when_below_minimum():
    c = doctor._check_python_version(minimum=(99, 0))
    assert c.status == "fail"
    assert c.remedy


# --- git ------------------------------------------------------------------------------------


def test_git_fail_when_binary_missing(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    c = doctor._check_git(".")
    assert c.status == "fail"
    assert "git" in c.detail.lower()


def test_git_pass_when_present_and_inside_work_tree(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/git")

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="true\n", stderr="")

    monkeypatch.setattr(doctor.subprocess, "run", _fake_run)
    c = doctor._check_git(".")
    assert c.status == "pass"


def test_git_warn_when_present_but_not_a_work_tree(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/git")

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 128, stdout="false\n", stderr="fatal: not a git repo")

    monkeypatch.setattr(doctor.subprocess, "run", _fake_run)
    c = doctor._check_git(".")
    assert c.status == "warn"


def test_git_warn_when_probe_raises(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/git")

    def _raise(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=5.0)

    monkeypatch.setattr(doctor.subprocess, "run", _raise)
    c = doctor._check_git(".")
    assert c.status == "warn"


# --- docker ---------------------------------------------------------------------------------


def test_docker_warn_not_fail_when_absent(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    c = doctor._check_docker()
    assert c.status == "warn"


def test_docker_pass_when_present(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/docker")

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="Docker version 24.0\n", stderr="")

    monkeypatch.setattr(doctor.subprocess, "run", _fake_run)
    c = doctor._check_docker()
    assert c.status == "pass"


def test_docker_warn_when_present_but_probe_fails(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/docker")

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="boom")

    monkeypatch.setattr(doctor.subprocess, "run", _fake_run)
    c = doctor._check_docker()
    assert c.status == "warn"


# --- .jaros-data writability / dirs present (tmp_path -- never touches the real repo) -------


def test_data_dir_writable_pass(tmp_path):
    (tmp_path / ".jaros-data").mkdir()
    c = doctor._check_data_dir_writable(str(tmp_path))
    assert c.status == "pass"


def test_data_dir_writable_warn_when_missing(tmp_path):
    c = doctor._check_data_dir_writable(str(tmp_path))
    assert c.status == "warn"


def test_data_dir_writable_never_performs_a_real_write(tmp_path, monkeypatch):
    """Placement rule (design.md): writability is a PERMISSION QUERY, never an actual write."""
    data_dir = tmp_path / ".jaros-data"
    data_dir.mkdir()
    calls = []
    real_access = doctor.os.access
    monkeypatch.setattr(doctor.os, "access", lambda *a, **k: (calls.append(a) or real_access(*a, **k)))
    doctor._check_data_dir_writable(str(tmp_path))
    assert calls  # os.access was actually consulted
    assert list(data_dir.iterdir()) == []  # and nothing was written into it


def test_dirs_present_pass(tmp_path):
    base = tmp_path / ".jaros-data"
    (base / "tools").mkdir(parents=True)
    (base / "agents").mkdir(parents=True)
    c = doctor._check_dirs_present(str(tmp_path))
    assert c.status == "pass"


def test_dirs_present_warn_when_missing(tmp_path):
    (tmp_path / ".jaros-data").mkdir()
    c = doctor._check_dirs_present(str(tmp_path))
    assert c.status == "warn"
    assert "tools" in c.detail or "agents" in c.detail


# --- config sanity ----------------------------------------------------------------------------


def test_config_backend_pass_for_llamacpp(monkeypatch):
    monkeypatch.setenv("JCODE_LLM_BACKEND", "llamacpp")
    assert doctor._check_config().status == "pass"


def test_config_backend_pass_for_ollama(monkeypatch):
    monkeypatch.setenv("JCODE_LLM_BACKEND", "ollama")
    assert doctor._check_config().status == "pass"


def test_config_backend_default_is_pass(monkeypatch):
    monkeypatch.delenv("JCODE_LLM_BACKEND", raising=False)
    assert doctor._check_config().status == "pass"


def test_config_backend_warn_on_unrecognized_value(monkeypatch):
    monkeypatch.setenv("JCODE_LLM_BACKEND", "some-cloud-thing")
    c = doctor._check_config()
    assert c.status == "warn"


# --- llm endpoint / model served (mocked harness.llamacpp_client.health -- no real network) --


def test_endpoint_reachable_with_models_is_pass_pass(monkeypatch):
    monkeypatch.setattr(
        llamacpp_client, "health",
        lambda host=None, timeout=8.0: {"ok": True, "host": host, "models": ["gemma-4-e2b"]},
    )
    endpoint, served = doctor._check_llm_endpoint()
    assert endpoint.status == "pass"
    assert served.status == "pass"
    assert "gemma-4-e2b" in served.detail


def test_endpoint_reachable_no_models_is_pass_warn(monkeypatch):
    monkeypatch.setattr(
        llamacpp_client, "health",
        lambda host=None, timeout=8.0: {"ok": True, "host": host, "models": []},
    )
    endpoint, served = doctor._check_llm_endpoint()
    assert endpoint.status == "pass"
    assert served.status == "warn"


def test_endpoint_unreachable_is_warn_warn_never_fail(monkeypatch):
    monkeypatch.setattr(
        llamacpp_client, "health",
        lambda host=None, timeout=8.0: {"ok": False, "host": host, "error": "connection refused"},
    )
    endpoint, served = doctor._check_llm_endpoint()
    assert endpoint.status == "warn"
    assert served.status == "warn"
    assert endpoint.status != "fail"


def test_endpoint_probe_raising_degrades_to_warn_never_raises(monkeypatch):
    def _raise(host=None, timeout=8.0):
        raise RuntimeError("socket exploded")

    monkeypatch.setattr(llamacpp_client, "health", _raise)
    endpoint, served = doctor._check_llm_endpoint()
    assert endpoint.status == "warn"
    assert served.status == "warn"


# --- run_doctor: overall verdict + never-raises orchestration --------------------------------


def _all_pass_monkeypatches(monkeypatch, tmp_path):
    (tmp_path / ".jaros-data" / "tools").mkdir(parents=True)
    (tmp_path / ".jaros-data" / "agents").mkdir(parents=True)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        doctor.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="true\n", stderr=""),
    )
    monkeypatch.setattr(
        llamacpp_client, "health",
        lambda host=None, timeout=8.0: {"ok": True, "host": host, "models": ["gemma-4-e2b"]},
    )


def test_run_doctor_all_pass_overall_pass(monkeypatch, tmp_path):
    _all_pass_monkeypatches(monkeypatch, tmp_path)
    report = run_doctor(str(tmp_path))
    assert report["overall"] == "pass"
    assert all(c.status == "pass" for c in report["checks"])


def test_run_doctor_any_warn_overall_warn(monkeypatch, tmp_path):
    _all_pass_monkeypatches(monkeypatch, tmp_path)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None if name == "docker" else f"/usr/bin/{name}")
    report = run_doctor(str(tmp_path))
    assert report["overall"] == "warn"
    assert not any(c.status == "fail" for c in report["checks"])


def test_run_doctor_any_fail_overall_fail(monkeypatch, tmp_path):
    _all_pass_monkeypatches(monkeypatch, tmp_path)
    monkeypatch.setattr(doctor, "_check_python_version", lambda *a, **k: doctor._check("python_version", "fail", "too old"))
    report = run_doctor(str(tmp_path))
    assert report["overall"] == "fail"


def test_run_doctor_one_check_raising_degrades_others_unaffected(monkeypatch, tmp_path):
    _all_pass_monkeypatches(monkeypatch, tmp_path)

    def _boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(doctor, "_check_docker", _boom)
    report = run_doctor(str(tmp_path))
    names = {c.name for c in report["checks"]}
    assert "docker" in names  # the placeholder still appears
    docker_check = next(c for c in report["checks"] if c.name == "docker")
    assert docker_check.status == "warn"
    # every other check still ran normally
    assert any(c.name == "python_version" and c.status == "pass" for c in report["checks"])


# --- render() ----------------------------------------------------------------------------------


def test_render_default_calls_run_doctor(monkeypatch, tmp_path):
    _all_pass_monkeypatches(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    text = render()
    assert "jcode doctor" in text
    assert "overall:" in text


def test_render_includes_remedy_for_non_pass_checks():
    report = {
        "checks": [DoctorCheck(name="thing", status="fail", detail="broke", remedy="fix it")],
        "overall": "fail",
    }
    text = render(report)
    assert "thing" in text
    assert "fix it" in text
    assert "FAIL" in text


def test_render_never_raises_on_malformed_report():
    assert isinstance(render({"not": "a valid report"}), str)
    assert isinstance(render({"checks": [], "overall": "pass"}), str)


# --- JcodeCli.cmd_doctor -----------------------------------------------------------------------


def test_cmd_doctor_renders_run_doctor_report(monkeypatch):
    fake_report = {"checks": [DoctorCheck("x", "pass", "ok")], "overall": "pass"}
    monkeypatch.setattr(doctor, "run_doctor", lambda root=".": fake_report)
    cli = JcodeCli()
    out = cli.cmd_doctor("")
    assert "overall:" in out
    assert "ok" in out


def test_cmd_doctor_never_raises_on_failure(monkeypatch):
    def _boom(root="."):
        raise RuntimeError("doctor is out")

    monkeypatch.setattr(doctor, "run_doctor", _boom)
    cli = JcodeCli()
    out = cli.cmd_doctor("")
    assert "unavailable" in out


# --- headless dispatch: _dispatch_doctor_subcommand ---------------------------------------------


def test_dispatch_doctor_bare_word(monkeypatch, capsys):
    fake_report = {"checks": [DoctorCheck("x", "pass", "ok")], "overall": "pass"}
    monkeypatch.setattr(doctor, "run_doctor", lambda root=".": fake_report)
    code = _dispatch_doctor_subcommand(["doctor"])
    assert code == 0
    out = capsys.readouterr().out
    assert "overall:" in out


def test_dispatch_doctor_flag_form(monkeypatch, capsys):
    fake_report = {"checks": [DoctorCheck("x", "pass", "ok")], "overall": "pass"}
    monkeypatch.setattr(doctor, "run_doctor", lambda root=".": fake_report)
    code = _dispatch_doctor_subcommand(["--doctor"])
    assert code == 0


def test_dispatch_doctor_fail_overall_is_nonzero_exit(monkeypatch, capsys):
    fake_report = {"checks": [DoctorCheck("x", "fail", "broke")], "overall": "fail"}
    monkeypatch.setattr(doctor, "run_doctor", lambda root=".": fake_report)
    code = _dispatch_doctor_subcommand(["doctor"])
    assert code == 1


def test_dispatch_doctor_warn_overall_is_zero_exit(monkeypatch, capsys):
    fake_report = {"checks": [DoctorCheck("x", "warn", "meh")], "overall": "warn"}
    monkeypatch.setattr(doctor, "run_doctor", lambda root=".": fake_report)
    code = _dispatch_doctor_subcommand(["doctor"])
    assert code == 0


def test_dispatch_doctor_returns_none_for_ordinary_plain_request():
    assert _dispatch_doctor_subcommand(["fix", "the", "bug"]) is None


def test_dispatch_doctor_returns_none_for_empty_args():
    assert _dispatch_doctor_subcommand([]) is None


def test_help_documents_doctor():
    cli = JcodeCli()
    assert "/doctor" in cli.cmd_help("")
