"""EXT-037 / REQ-5 -- the interactive CLI WIELDS the git toolbelt.

Verifies the five new REPL commands (`/gitstatus`, `/gitlog`, `/gitdiff`, `/gitbranch`,
`/commit`) dispatch the existing git.* Decisions through a root-anchored Runtime — the
same two-plane path harness/system_finalize.py already uses — and NEVER raise to the
REPL, even outside a git repo or when the secret guard refuses a commit.

Offline, deterministic, no network: every test operates on a genuinely local git repo
created in a pytest ``tmp_path`` (mirrors ``tests/test_ext037_git_tools.py``'s
conventions). Skips cleanly if ``git`` is not on PATH.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.cli import JcodeCli  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not available on PATH")

# #EXT-037-REQ-5 Start


def _init_repo(root: Path) -> None:
    """Init a repo with a repo-scoped (not global) commit identity, then commit one
    tracked file — a realistic starting point for status/log/diff/branch/commit."""
    subprocess.run(["git", "init"], cwd=str(root), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "jarify-test@example.com"], cwd=str(root), check=True)
    subprocess.run(["git", "config", "user.name", "Jarify Test"], cwd=str(root), check=True)
    (root / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(root), check=True, capture_output=True)


def _log_count(root: Path) -> int:
    out = subprocess.run(["git", "log", "--oneline"], cwd=str(root), capture_output=True, text=True)
    return len([ln for ln in out.stdout.splitlines() if ln.strip()])


# --- read-only commands on a real, dirty repo -------------------------------------


def test_gitstatus_reports_dirty_file(tmp_path: Path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.dispatch("/gitstatus")
    assert "dirty.txt" in out
    assert "change" in out


def test_gitstatus_reports_clean(tmp_path: Path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    assert "clean" in cli.dispatch("/gitstatus")


def test_gitlog_shows_commit_and_respects_count(tmp_path: Path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "second commit"], cwd=str(tmp_path), check=True, capture_output=True)
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.dispatch("/gitlog")
    assert "initial commit" in out and "second commit" in out
    out1 = cli.dispatch("/gitlog 1")
    assert "second commit" in out1 and "initial commit" not in out1


def test_gitlog_bad_count_is_usage_string(tmp_path: Path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    assert "usage" in cli.dispatch("/gitlog notanumber")


def test_gitdiff_shows_unstaged_change(tmp_path: Path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("hello\nmodified\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.dispatch("/gitdiff")
    assert "modified" in out
    out_scoped = cli.dispatch("/gitdiff README.md")
    assert "modified" in out_scoped


def test_gitdiff_no_changes(tmp_path: Path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    assert "no changes" in cli.dispatch("/gitdiff")


def test_gitbranch_lists_current(tmp_path: Path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    out = cli.dispatch("/gitbranch")
    assert "*" in out
    assert len(out.strip()) > 0


# --- /commit ------------------------------------------------------------------


def test_commit_requires_message(tmp_path: Path, monkeypatch):
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    cli = JcodeCli()
    assert "usage" in cli.dispatch("/commit")
    assert "usage" in cli.dispatch("/commit   ")


def test_commit_stages_and_commits(tmp_path: Path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / "feature.txt").write_text("new feature\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    before = _log_count(tmp_path)
    cli = JcodeCli()
    out = cli.dispatch("/commit add feature.txt")
    assert "committed" in out
    assert "feature.txt" in out or "1 file" in out
    assert _log_count(tmp_path) == before + 1


def test_commit_refuses_secret_env_file(tmp_path: Path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / ".env").write_text("SECRET=abc123\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    before = _log_count(tmp_path)
    cli = JcodeCli()
    out = cli.dispatch("/commit add secret")
    assert "refused" in out or "rejected" in out
    assert _log_count(tmp_path) == before  # no commit happened


# --- never raise outside a git repo --------------------------------------------


def test_handlers_never_raise_on_non_repo_dir(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no git init here
    cli = JcodeCli()
    for line in ("/gitstatus", "/gitlog", "/gitdiff", "/gitbranch", "/commit a message"):
        out = cli.dispatch(line)  # must not raise
        assert isinstance(out, str) and out.strip()
# #EXT-037-REQ-5 End
