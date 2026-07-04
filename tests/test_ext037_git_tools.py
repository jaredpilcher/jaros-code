"""EXT-037 / REQ-4 -- git tools (init/commit/status/log/diff/branch/history-update).

Offline, deterministic, no network: every test operates on a genuinely local git
repo created in a pytest ``tmp_path`` (no remote is ever configured, so nothing
here can reach the network even for the ``force_push`` gate test, which only
proves the gate rejects -- it never actually runs a push).

Mirrors the ``_load_tool``/``_decision`` conventions of ``test_ext037_gated_exec.py``
/ ``test_ext037_env_tools.py``. Skips cleanly if ``git`` is not on PATH (it is a
standard tool, but the skip keeps the suite honest in a hypothetical environment
without it).
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from jaros.core import create_decision

TOOLS_DIR = Path(__file__).resolve().parents[1] / ".jaros-data" / "tools"

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from _gitsecrets import secret_or_ignored_reason  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not available on PATH")

# #EXT-037-REQ-4 Start


def _load_tool(filename: str, classname: str):
    path = TOOLS_DIR / filename
    spec = importlib.util.spec_from_file_location(f"tool_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, classname)()


def _decision(dtype: str, payload):
    return create_decision(id=f"t-{dtype}", source="test", type=dtype, payload=payload)


def _init_repo(root: Path) -> None:
    """Init a repo AND configure a local (repo-scoped, not global) commit
    identity so `git commit` succeeds unattended in CI without touching the
    environment's global git config."""
    tool = _load_tool("git_init_tool.py", "GitInitTool")
    d = _decision("git.init", {"root": str(root)})
    assert tool.validate(d).ok is True
    out = tool.execute(d)
    assert out["initialized"] is True
    subprocess.run(["git", "config", "user.email", "jarify-test@example.com"], cwd=str(root), check=True)
    subprocess.run(["git", "config", "user.name", "Jarify Test"], cwd=str(root), check=True)


# --- (a) git.init --------------------------------------------------------------


def test_git_init_creates_a_repo(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    tool = _load_tool("git_init_tool.py", "GitInitTool")
    d = _decision("git.init", {"root": str(root)})
    assert tool.validate(d).ok is True
    out = tool.execute(d)
    assert out["initialized"] is True
    assert out["alreadyInitialized"] is False
    assert (root / ".git").exists()


def test_git_init_never_raises_on_bad_root():
    tool = _load_tool("git_init_tool.py", "GitInitTool")
    d = _decision("git.init", {"root": "Z:\\definitely\\not\\a\\real\\dir\\xyz"})
    out = tool.execute(d)
    assert out["initialized"] is False
    assert "error" in out or out["stderr"]


def test_git_init_validate_rejects_missing_root():
    tool = _load_tool("git_init_tool.py", "GitInitTool")
    d = _decision("git.init", {"root": "Z:\\nope\\nope"})
    assert tool.validate(d).ok is False


# --- (b) git.commit -------------------------------------------------------------


def test_git_commit_stages_and_commits_a_file(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _init_repo(root)
    (root / "hello.py").write_text("print('hi')\n", encoding="utf-8")

    tool = _load_tool("git_commit_tool.py", "GitCommitTool")
    d = _decision("git.commit", {"root": str(root), "message": "add hello.py"})
    result = tool.validate(d)
    assert result.ok is True, result.reason
    out = tool.execute(d)
    assert out["committed"] is True
    assert out["commitHash"]
    assert "hello.py" in out["staged"]


def test_git_commit_refuses_env_secret_path(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _init_repo(root)
    (root / ".env").write_text("SECRET=abc123\n", encoding="utf-8")
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")

    tool = _load_tool("git_commit_tool.py", "GitCommitTool")

    # (i) staging "everything" (no explicit paths) must be refused because .env
    # is among the candidate files git status would actually stage.
    d_all = _decision("git.commit", {"root": str(root), "message": "commit everything"})
    result_all = tool.validate(d_all)
    assert result_all.ok is False
    assert "secret" in (result_all.reason or "").lower() or "ignored" in (result_all.reason or "").lower()

    # (ii) explicitly naming the secret file is refused the same way.
    d_named = _decision("git.commit", {
        "root": str(root), "message": "commit secret", "paths": [".env"],
    })
    result_named = tool.validate(d_named)
    assert result_named.ok is False

    # Confirm nothing was ever committed: the log has no commits at all.
    log_tool = _load_tool("git_log_tool.py", "GitLogTool")
    log_out = log_tool.execute(_decision("git.log", {"root": str(root)}))
    assert log_out["hasCommits"] is False
    assert not any(".env" in c.get("subject", "") for c in log_out["commits"])

    # A commit of ONLY the safe file still works (the guard is path-specific,
    # not a blanket refusal of the whole repo).
    d_safe = _decision("git.commit", {
        "root": str(root), "message": "commit app.py only", "paths": ["app.py"],
    })
    assert tool.validate(d_safe).ok is True
    safe_out = tool.execute(d_safe)
    assert safe_out["committed"] is True
    assert "app.py" in safe_out["staged"]
    assert ".env" not in safe_out["staged"]


def test_git_commit_validate_rejects_path_escaping_root(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _init_repo(root)
    tool = _load_tool("git_commit_tool.py", "GitCommitTool")
    d = _decision("git.commit", {
        "root": str(root), "message": "escape", "paths": ["../outside.txt"],
    })
    result = tool.validate(d)
    assert result.ok is False
    assert "root" in (result.reason or "").lower()


def test_git_commit_never_raises_on_bad_root():
    tool = _load_tool("git_commit_tool.py", "GitCommitTool")
    d = _decision("git.commit", {"root": "Z:\\nope\\nope\\nope", "message": "x"})
    out = tool.execute(d)
    assert isinstance(out, dict)
    assert out["committed"] is False


# --- (c) git.status / git.log / git.diff ----------------------------------------


def test_git_status_reports_untracked_and_clean(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _init_repo(root)
    status_tool = _load_tool("git_status_tool.py", "GitStatusTool")

    clean = status_tool.execute(_decision("git.status", {"root": str(root)}))
    assert clean["clean"] is True
    assert clean["entries"] == []

    (root / "a.txt").write_text("a\n", encoding="utf-8")
    dirty = status_tool.execute(_decision("git.status", {"root": str(root)}))
    assert dirty["clean"] is False
    assert any(e["path"] == "a.txt" for e in dirty["entries"])


def test_git_log_lists_the_commit_after_a_commit(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _init_repo(root)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    commit_tool = _load_tool("git_commit_tool.py", "GitCommitTool")
    commit_out = commit_tool.execute(_decision("git.commit", {"root": str(root), "message": "add a.txt"}))
    assert commit_out["committed"] is True

    log_tool = _load_tool("git_log_tool.py", "GitLogTool")
    log_out = log_tool.execute(_decision("git.log", {"root": str(root)}))
    assert log_out["hasCommits"] is True
    assert any(c["subject"] == "add a.txt" for c in log_out["commits"])
    assert log_out["commits"][0]["hash"] == commit_out["commitHash"]


def test_git_log_on_empty_repo_is_honest_not_an_error(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _init_repo(root)
    log_tool = _load_tool("git_log_tool.py", "GitLogTool")
    out = log_tool.execute(_decision("git.log", {"root": str(root)}))
    assert out["hasCommits"] is False
    assert out["commits"] == []


def test_git_diff_shows_unstaged_changes(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _init_repo(root)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    commit_tool = _load_tool("git_commit_tool.py", "GitCommitTool")
    commit_tool.execute(_decision("git.commit", {"root": str(root), "message": "add a.txt"}))
    (root / "a.txt").write_text("a\nb\n", encoding="utf-8")

    diff_tool = _load_tool("git_diff_tool.py", "GitDiffTool")
    out = diff_tool.execute(_decision("git.diff", {"root": str(root)}))
    assert out["hasChanges"] is True
    assert "a.txt" in out["diff"]


# --- (d) git.branch --------------------------------------------------------------


def test_git_branch_create_and_list(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _init_repo(root)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    commit_tool = _load_tool("git_commit_tool.py", "GitCommitTool")
    commit_tool.execute(_decision("git.commit", {"root": str(root), "message": "seed"}))

    branch_tool = _load_tool("git_branch_tool.py", "GitBranchTool")
    create_d = _decision("git.branch", {"root": str(root), "action": "create", "name": "feature-x"})
    assert branch_tool.validate(create_d).ok is True
    create_out = branch_tool.execute(create_d)
    assert create_out["created"] is True

    list_out = branch_tool.execute(_decision("git.branch", {"root": str(root), "action": "list"}))
    assert "feature-x" in list_out["branches"]


def test_git_branch_switch(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _init_repo(root)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    commit_tool = _load_tool("git_commit_tool.py", "GitCommitTool")
    commit_tool.execute(_decision("git.commit", {"root": str(root), "message": "seed"}))

    branch_tool = _load_tool("git_branch_tool.py", "GitBranchTool")
    switch_d = _decision("git.branch", {
        "root": str(root), "action": "switch", "name": "feature-y", "create_if_missing": True,
    })
    assert branch_tool.validate(switch_d).ok is True
    out = branch_tool.execute(switch_d)
    assert out["switched"] is True

    list_out = branch_tool.execute(_decision("git.branch", {"root": str(root), "action": "list"}))
    assert list_out["current"] == "feature-y"


def test_git_branch_validate_rejects_bad_name():
    tool = _load_tool("git_branch_tool.py", "GitBranchTool")
    d = _decision("git.branch", {"root": ".", "action": "create", "name": "-rf"})
    assert tool.validate(d).ok is False


# --- (e) git.history_update -- explicit-gated -----------------------------------


def test_history_update_rejected_by_default(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _init_repo(root)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    commit_tool = _load_tool("git_commit_tool.py", "GitCommitTool")
    commit_tool.execute(_decision("git.commit", {"root": str(root), "message": "orig message"}))

    tool = _load_tool("git_history_update_tool.py", "GitHistoryUpdateTool")
    for payload in (
        {"root": str(root), "action": "amend", "message": "rewritten"},
        {"root": str(root), "action": "amend", "message": "rewritten", "allow_unsafe": False},
        {"root": str(root), "action": "amend", "message": "rewritten", "allow_unsafe": "true"},
    ):
        result = tool.validate(_decision("git.history_update", payload))
        assert result.ok is False


def test_history_update_amend_allowed_with_explicit_gate(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _init_repo(root)
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    commit_tool = _load_tool("git_commit_tool.py", "GitCommitTool")
    commit_tool.execute(_decision("git.commit", {"root": str(root), "message": "orig message"}))

    tool = _load_tool("git_history_update_tool.py", "GitHistoryUpdateTool")
    d = _decision("git.history_update", {
        "root": str(root), "action": "amend", "message": "rewritten message", "allow_unsafe": True,
    })
    assert tool.validate(d).ok is True
    out = tool.execute(d)
    assert out["applied"] is True

    log_tool = _load_tool("git_log_tool.py", "GitLogTool")
    log_out = log_tool.execute(_decision("git.log", {"root": str(root)}))
    assert log_out["commits"][0]["subject"] == "rewritten message"
    assert len(log_out["commits"]) == 1  # amend replaces, does not add, a commit


def test_history_update_reset_hard_requires_gate_and_ref(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _init_repo(root)
    tool = _load_tool("git_history_update_tool.py", "GitHistoryUpdateTool")
    # No allow_unsafe -> rejected regardless of ref.
    d_no_gate = _decision("git.history_update", {"root": str(root), "action": "reset_hard", "ref": "HEAD"})
    assert tool.validate(d_no_gate).ok is False
    # Gated but missing ref -> still rejected.
    d_no_ref = _decision("git.history_update", {"root": str(root), "action": "reset_hard", "allow_unsafe": True})
    assert tool.validate(d_no_ref).ok is False


def test_history_update_force_push_requires_gate():
    tool = _load_tool("git_history_update_tool.py", "GitHistoryUpdateTool")
    # Never actually runs (no remote configured); only proves the gate blocks by
    # default and requires remote/branch even once gated.
    d = _decision("git.history_update", {"root": ".", "action": "force_push"})
    assert tool.validate(d).ok is False
    d_gated_incomplete = _decision("git.history_update", {
        "root": ".", "action": "force_push", "allow_unsafe": True,
    })
    assert tool.validate(d_gated_incomplete).ok is False


def test_history_update_never_raises_on_bad_root():
    tool = _load_tool("git_history_update_tool.py", "GitHistoryUpdateTool")
    d = _decision("git.history_update", {
        "root": "Z:\\nope\\nope\\nope", "action": "amend", "allow_unsafe": True,
    })
    out = tool.execute(d)
    assert isinstance(out, dict)
    assert out["applied"] is False


# --- (f) secret guard helper (direct) --------------------------------------------


def test_secret_or_ignored_reason_helper():
    assert secret_or_ignored_reason(".env") is not None
    assert secret_or_ignored_reason("config/.env.production") is not None
    assert secret_or_ignored_reason("id_rsa") is not None
    assert secret_or_ignored_reason("server.pem") is not None
    assert secret_or_ignored_reason("secrets.yaml") is not None
    assert secret_or_ignored_reason("app.log") is not None
    assert secret_or_ignored_reason("__pycache__/mod.pyc") is not None
    assert secret_or_ignored_reason("src/app.py") is None
    assert secret_or_ignored_reason("README.md") is None
    assert secret_or_ignored_reason(None) is None
# #EXT-037-REQ-4 End
