"""EXT-037 / REQ-5 (TASK-6) -- ``harness.system_finalize.finalize_system``: the FINISHER

that makes the toolbelt actually WIELDED by the sentence-to-system product after a
shipped ``/buildsystem`` build. Offline, deterministic, no network: every test drives
a genuinely local git repo in a pytest ``tmp_path`` (no remote configured anywhere),
and venv creation uses the stdlib ``venv``/``ensurepip`` (bundled wheels, no PyPI).
Skips cleanly if ``git`` is not on ``PATH``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.system_finalize import finalize_system  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not available on PATH")

# #EXT-037-REQ-5 Start


def _configure_local_git_identity(root: Path) -> None:
    """Repo-scoped (not global) commit identity so `git commit` succeeds unattended,
    mirroring `tests/test_ext037_git_tools.py`'s own convention."""
    subprocess.run(["git", "config", "user.email", "jarify-test@example.com"], cwd=str(root), check=True)
    subprocess.run(["git", "config", "user.name", "Jarify Test"], cwd=str(root), check=True)


def _git_log_subjects(root: Path) -> list:
    proc = subprocess.run(["git", "log", "--pretty=format:%s"], cwd=str(root),
                           capture_output=True, text=True)
    if proc.returncode != 0:
        return []
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


# --- (a) git-init + commit end-to-end --------------------------------------------------


def test_finalize_git_inits_and_commits_a_shipped_build(tmp_path):
    root = tmp_path / "sys_built"
    root.mkdir()
    (root / "main.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    # A pre-existing repo with local identity configured (mirrors the git-tools test
    # convention) -- finalize's own git.init is idempotent against an existing repo.
    subprocess.run(["git", "init"], cwd=str(root), check=True, capture_output=True)
    _configure_local_git_identity(root)

    out = finalize_system(str(root), {"main.py": "def run():\n    return 1\n"},
                           git=True, venv="off", data_dir=tmp_path / "state")

    assert out["ok"] is True
    commit_step = next(s for s in out["steps"] if s["step"] == "git.commit")
    assert commit_step["ok"] is True
    assert commit_step["output"]["commitHash"]
    subjects = _git_log_subjects(root)
    assert any("built by /buildsystem" in s for s in subjects)


def test_finalize_git_init_is_idempotent_on_a_fresh_root(tmp_path):
    root = tmp_path / "fresh"
    root.mkdir()
    (root / "util.py").write_text("VALUE = 1\n", encoding="utf-8")
    out = finalize_system(str(root), {"util.py": "VALUE = 1\n"},
                           git=True, venv="off", data_dir=tmp_path / "state")
    # git.init has no repo-local identity yet on a genuinely fresh repo (no prior
    # `git config`), so the commit step may fail in a CI box with no global identity
    # either -- what matters is finalize never raises and honestly reports either way.
    assert (root / ".git").exists()
    init_step = next(s for s in out["steps"] if s["step"] == "git.init")
    assert init_step["ok"] is True


# --- (b) venv-if-deps --------------------------------------------------------------------


def test_finalize_creates_venv_when_requirements_txt_present(tmp_path):
    root = tmp_path / "sys_with_deps"
    root.mkdir()
    (root / "requirements.txt").write_text("requests\n", encoding="utf-8")
    (root / "main.py").write_text("import requests\n", encoding="utf-8")

    out = finalize_system(str(root), {"main.py": "import requests\n"},
                           git=False, venv="auto", data_dir=tmp_path / "state")

    assert out["dependenciesDetected"] is True
    venv_step = next(s for s in out["steps"] if s["step"] == "env.venv_create")
    assert venv_step["ok"] is True
    # A real venv was created (offline stdlib venv/ensurepip) -- its own python exists.
    assert venv_step["output"]["pythonExists"] is True
    assert (root / ".venv").is_dir()
    # requirements.txt already existed -- finalize must not clobber it with a pin step.
    assert not any(s["step"] == "env.venv_pin" for s in out["steps"])


def test_finalize_skips_venv_for_a_stdlib_only_system(tmp_path):
    root = tmp_path / "sys_stdlib_only"
    root.mkdir()
    (root / "main.py").write_text("import os\nimport json\n\ndef run():\n    return os.getcwd()\n",
                                   encoding="utf-8")

    out = finalize_system(str(root), {"main.py": "import os\nimport json\n\ndef run():\n    return os.getcwd()\n"},
                           git=False, venv="auto", data_dir=tmp_path / "state")

    assert out["dependenciesDetected"] is False
    venv_step = next(s for s in out["steps"] if s["step"] == "venv")
    assert venv_step["ok"] is True
    assert venv_step.get("skipped")
    assert not (root / ".venv").exists()


def test_finalize_detects_dependency_from_import_scan_without_requirements_txt(tmp_path):
    root = tmp_path / "sys_import_only"
    root.mkdir()
    code = "import numpy\n\ndef run():\n    return numpy.array([1])\n"
    (root / "main.py").write_text(code, encoding="utf-8")

    out = finalize_system(str(root), {"main.py": code}, git=False, venv="auto",
                           data_dir=tmp_path / "state")

    assert out["dependenciesDetected"] is True
    venv_step = next(s for s in out["steps"] if s["step"] == "env.venv_create")
    assert venv_step["ok"] is True
    pin_step = next(s for s in out["steps"] if s["step"] == "env.venv_pin")
    assert pin_step["ok"] is True
    req_path = root / "requirements.txt"
    assert req_path.is_file()
    assert "numpy" in req_path.read_text(encoding="utf-8")


# --- (b2) live-demo bug fix: a build's own __pycache__ artifact must never block the
#          commit -- finalize writes a .gitignore before git.init/git.commit ------------------


def test_finalize_writes_gitignore_and_excludes_pycache_artifact_from_commit(tmp_path):
    root = tmp_path / "sys_with_pycache_artifact"
    root.mkdir()
    main_src = "def run():\n    return 1\n"
    (root / "main.py").write_text(main_src, encoding="utf-8")
    # Simulate the acceptance-test run's artifact (the live-demo failure): running the
    # built main.py creates a __pycache__ dir with a compiled .pyc inside root.
    pycache_dir = root / "__pycache__"
    pycache_dir.mkdir()
    (pycache_dir / "main.cpython-312.pyc").write_bytes(b"\x00\x01fake-bytecode")

    subprocess.run(["git", "init"], cwd=str(root), check=True, capture_output=True)
    _configure_local_git_identity(root)

    out = finalize_system(str(root), {"main.py": main_src}, git=True, venv="off",
                           data_dir=tmp_path / "state")

    assert out["ok"] is True
    commit_step = next(s for s in out["steps"] if s["step"] == "git.commit")
    assert commit_step["ok"] is True
    assert commit_step["output"]["committed"] is True
    assert _git_log_subjects(root)  # non-empty: something was actually committed

    gitignore_path = root / ".gitignore"
    assert gitignore_path.is_file()
    assert "__pycache__/" in gitignore_path.read_text(encoding="utf-8")

    ls_files = subprocess.run(["git", "ls-files"], cwd=str(root), capture_output=True,
                               text=True, check=True).stdout
    assert "main.cpython-312.pyc" not in ls_files
    assert ".gitignore" in ls_files.replace("\\", "/")


def test_finalize_does_not_overwrite_an_existing_gitignore(tmp_path):
    root = tmp_path / "sys_with_own_gitignore"
    root.mkdir()
    main_src = "def run():\n    return 1\n"
    (root / "main.py").write_text(main_src, encoding="utf-8")
    own_gitignore = "# my own project ignores\ncustom_ignore_me/\n"
    (root / ".gitignore").write_text(own_gitignore, encoding="utf-8")

    subprocess.run(["git", "init"], cwd=str(root), check=True, capture_output=True)
    _configure_local_git_identity(root)

    out = finalize_system(str(root), {"main.py": main_src}, git=True, venv="off",
                           data_dir=tmp_path / "state")

    gitignore_step = next(s for s in out["steps"] if s["step"] == "gitignore")
    assert gitignore_step["ok"] is True
    assert gitignore_step.get("skipped") == "exists"
    assert (root / ".gitignore").read_text(encoding="utf-8") == own_gitignore  # untouched

    commit_step = next(s for s in out["steps"] if s["step"] == "git.commit")
    assert commit_step["ok"] is True
    assert _git_log_subjects(root)


# --- (c) secrets never committed, even through finalize -----------------------------------


def test_finalize_never_commits_a_secret(tmp_path):
    root = tmp_path / "sys_with_secret"
    root.mkdir()
    (root / "main.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    (root / ".env").write_text("API_KEY=super-secret\n", encoding="utf-8")

    subprocess.run(["git", "init"], cwd=str(root), check=True, capture_output=True)
    _configure_local_git_identity(root)

    out = finalize_system(str(root), {"main.py": "def run():\n    return 1\n"},
                           git=True, venv="off", data_dir=tmp_path / "state")

    commit_step = next(s for s in out["steps"] if s["step"] == "git.commit")
    assert commit_step["ok"] is False  # refused by the secret guard, never forced through
    assert _git_log_subjects(root) == []  # zero commits -- nothing was committed at all
    # And finalize as a whole still reports honestly (not "ok") without raising.
    assert out["ok"] is False


# --- (d) finalize NEVER raises, even on a hard git failure ---------------------------------


def test_finalize_never_raises_on_a_runtime_failure(tmp_path, monkeypatch):
    root = tmp_path / "sys_broken"
    root.mkdir()
    (root / "main.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    class _AlwaysFailsRuntime:
        def __init__(self, *a, **k):
            pass

        def apply(self, decision):
            raise RuntimeError(f"simulated gate rejection for {decision.type}")

    import harness.system_finalize as sf
    monkeypatch.setattr(sf, "Runtime", _AlwaysFailsRuntime)

    out = finalize_system(str(root), {"main.py": "def run():\n    return 1\n"},
                           git=True, venv="always", data_dir=tmp_path / "state")

    assert out["ok"] is False  # honestly reflects the failure
    assert all(s.get("ok") is False for s in out["steps"] if s["step"] in
               ("git.init", "git.commit", "env.venv_create"))
    # Critically: no exception propagated out of finalize_system itself.


def test_finalize_never_raises_on_a_nonexistent_root(tmp_path):
    missing = tmp_path / "does_not_exist"
    out = finalize_system(str(missing), {}, git=True, venv="auto", data_dir=tmp_path / "state")
    assert out["ok"] is False
    assert "does not exist" in out["note"]


# --- (e) the gate/flag disables finalize cleanly -------------------------------------------


def test_finalize_git_false_and_venv_off_skip_everything(tmp_path):
    root = tmp_path / "sys_disabled"
    root.mkdir()
    (root / "main.py").write_text("import requests\n", encoding="utf-8")

    out = finalize_system(str(root), {"main.py": "import requests\n"},
                           git=False, venv="off", data_dir=tmp_path / "state")

    assert out["ok"] is True
    step_names = {s["step"] for s in out["steps"]}
    assert step_names == {"git", "venv"}
    assert not (root / ".git").exists()
    assert not (root / ".venv").exists()


# #EXT-037-REQ-5 End
# #EXT-037-REQ-17 Start
# --- (f) REQ-17: dep_security is advisory-only, additive on the finalize result -----------


def test_finalize_attaches_dep_security_when_deps_detected_and_stays_advisory(tmp_path):
    root = tmp_path / "sys_with_deps_advisory"
    root.mkdir()
    (root / "requirements.txt").write_text("pyyaml==5.3\n", encoding="utf-8")
    (root / "main.py").write_text("import yaml\n", encoding="utf-8")

    out = finalize_system(str(root), {"main.py": "import yaml\n"},
                           git=False, venv="auto", data_dir=tmp_path / "state")

    assert out["dependenciesDetected"] is True
    assert out["dep_security"] is not None
    findings = out["dep_security"]["findings"]
    assert any(f["package"] == "pyyaml" and f["kind"] == "known-advisory" for f in findings)
    # ADVISORY ONLY: a known-vulnerable pinned dep never affects `ok`, and the venv step
    # (REQ-3) still runs exactly as before -- dep_security is purely additive.
    assert out["ok"] is True
    venv_step = next(s for s in out["steps"] if s["step"] == "env.venv_create")
    assert venv_step["ok"] is True
    assert (root / ".venv").is_dir()


def test_finalize_dep_security_is_none_when_no_dependency_detected(tmp_path):
    root = tmp_path / "sys_stdlib_only_advisory"
    root.mkdir()
    (root / "main.py").write_text("import os\n", encoding="utf-8")

    out = finalize_system(str(root), {"main.py": "import os\n"},
                           git=False, venv="auto", data_dir=tmp_path / "state")

    assert out["dependenciesDetected"] is False
    assert out["dep_security"] is None
    assert out["ok"] is True

# #EXT-037-REQ-17 End
# #EXT-037-REQ-5 Start


def test_cli_finalize_config_env_gate(monkeypatch):
    from harness.cli import _buildsystem_finalize_config

    monkeypatch.delenv("JCODE_FINALIZE_SYSTEM", raising=False)
    monkeypatch.delenv("JCODE_FINALIZE_GIT", raising=False)
    monkeypatch.delenv("JCODE_FINALIZE_VENV", raising=False)
    default_cfg = _buildsystem_finalize_config()
    assert default_cfg == {"enabled": True, "git": True, "venv": "auto"}

    monkeypatch.setenv("JCODE_FINALIZE_SYSTEM", "0")
    assert _buildsystem_finalize_config()["enabled"] is False

    monkeypatch.setenv("JCODE_FINALIZE_SYSTEM", "1")
    monkeypatch.setenv("JCODE_FINALIZE_GIT", "off")
    assert _buildsystem_finalize_config()["git"] is False

    monkeypatch.setenv("JCODE_FINALIZE_GIT", "1")
    monkeypatch.setenv("JCODE_FINALIZE_VENV", "always")
    assert _buildsystem_finalize_config()["venv"] == "always"

    monkeypatch.setenv("JCODE_FINALIZE_VENV", "bogus")
    assert _buildsystem_finalize_config()["venv"] == "auto"  # bad value -> safe default
# #EXT-037-REQ-5 End
