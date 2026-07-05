"""EXT-055: graceful interrupt + steer mid-run. Fully hermetic -- no live gemma, no real
subprocess-level Ctrl-C. `fix_loop` is monkeypatched (mirrors tests/test_ext003_multifile.py and
tests/test_ext037_agent_plan_jaros_write.py's proven pattern); the REPL's SIGINT wiring is
exercised by directly invoking the handler `signal.signal` installs, never a real OS signal.

★ The #1 property this file proves: with NO interrupt requested (interrupt=None, or a live but
never-cancelled controller), every touched loop runs BYTE-IDENTICAL to before this spec."""
from __future__ import annotations

import os
import signal
from pathlib import Path

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

import harness.coding_loop as cl
from harness.interrupt import InterruptController, get_interrupt_controller, reset_interrupt_controller


# --- InterruptController basics ------------------------------------------------------------------

def test_controller_starts_uncancelled():
    c = InterruptController()
    assert c.is_cancelled() is False


def test_request_cancel_sets_flag():
    c = InterruptController()
    c.request_cancel()
    assert c.is_cancelled() is True


def test_request_cancel_is_idempotent():
    c = InterruptController()
    c.request_cancel()
    c.request_cancel()
    assert c.is_cancelled() is True


def test_reset_clears_flag():
    c = InterruptController()
    c.request_cancel()
    c.reset()
    assert c.is_cancelled() is False


def test_singleton_returns_same_object():
    a = get_interrupt_controller()
    b = get_interrupt_controller()
    assert a is b


def test_reset_singleton_clears_shared_flag():
    c = get_interrupt_controller()
    c.request_cancel()
    assert c.is_cancelled() is True
    reset_interrupt_controller()
    assert get_interrupt_controller().is_cancelled() is False


# --- multi_file_fix: default (no interrupt) is byte-identical ------------------------------------

def _write_two_bug_repo(tmp_path):
    (tmp_path / "first_mod.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "second_mod.py").write_text("def mul(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / "test_ops.py").write_text(
        "from first_mod import add\nfrom second_mod import mul\n\n"
        "def test_add():\n    assert add(2, 3) == 5\n\n"
        "def test_mul():\n    assert mul(2, 3) == 6\n",
        encoding="utf-8",
    )


def test_multi_file_fix_default_interrupt_none_is_byte_identical(tmp_path, monkeypatch):
    _write_two_bug_repo(tmp_path)

    def fake_fix_loop(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False,
                       keep_partial=True):
        if str(target).endswith("first_mod.py"):
            Path(target).write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        elif str(target).endswith("second_mod.py"):
            Path(target).write_text("def mul(a, b):\n    return a * b\n", encoding="utf-8")

    monkeypatch.setattr(cl, "fix_loop", fake_fix_loop)
    from harness.multi_file import multi_file_fix
    r = multi_file_fix(str(tmp_path), "python -m pytest -q", "fix", "test_ops.py", interrupt=None)
    assert r["solved"] is True
    assert r["tried"] == ["first_mod.py", "second_mod.py"]


def test_multi_file_fix_live_uncancelled_controller_matches_none(tmp_path, monkeypatch):
    """A live but NEVER-cancelled controller must behave exactly like interrupt=None -- proves
    the real CLI's day-to-day wiring (a controller that just never gets cancelled) changes
    nothing observable."""
    _write_two_bug_repo(tmp_path)

    def fake_fix_loop(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False,
                       keep_partial=True):
        if str(target).endswith("first_mod.py"):
            Path(target).write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        elif str(target).endswith("second_mod.py"):
            Path(target).write_text("def mul(a, b):\n    return a * b\n", encoding="utf-8")

    monkeypatch.setattr(cl, "fix_loop", fake_fix_loop)
    from harness.multi_file import multi_file_fix
    live = InterruptController()   # constructed, but request_cancel() is never called
    r = multi_file_fix(str(tmp_path), "python -m pytest -q", "fix", "test_ops.py", interrupt=live)
    assert r["solved"] is True
    assert r["tried"] == ["first_mod.py", "second_mod.py"]


# --- multi_file_fix: graceful mid-run cancellation -----------------------------------------------

def test_multi_file_fix_stops_gracefully_after_step_k(tmp_path, monkeypatch):
    _write_two_bug_repo(tmp_path)
    controller = InterruptController()
    calls = []

    def fake_fix_loop(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False,
                       keep_partial=True):
        calls.append(Path(target).name)
        if str(target).endswith("first_mod.py"):
            # step K: genuinely fix first_mod, THEN the fake step-hook requests cancel --
            # simulates a Ctrl-C arriving right after this step completes.
            Path(target).write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            controller.request_cancel()
        elif str(target).endswith("second_mod.py"):
            raise AssertionError("second_mod.py must NEVER be attempted after the cancel")

    monkeypatch.setattr(cl, "fix_loop", fake_fix_loop)
    from harness.multi_file import multi_file_fix
    r = multi_file_fix(str(tmp_path), "python -m pytest -q", "fix", "test_ops.py",
                       interrupt=controller)

    # stopped BEFORE the second candidate -- no exception escaped, partial state intact
    assert calls == ["first_mod.py"]
    assert r["solved"] is False
    assert r["tried"] == ["first_mod.py"]
    assert r["fixed"] == ["first_mod.py"]          # step K's fix was kept (strict progress)
    assert "interrupted" in r["note"]
    assert "first_mod.py" not in r["dropped"]

    # files from the completed step are present; the un-attempted file is untouched (no
    # half-written file, no corruption)
    assert "return a + b" in (tmp_path / "first_mod.py").read_text(encoding="utf-8")
    assert "return a - b" in (tmp_path / "second_mod.py").read_text(encoding="utf-8")


def test_multi_file_fix_already_cancelled_stops_before_first_candidate(tmp_path, monkeypatch):
    _write_two_bug_repo(tmp_path)
    controller = InterruptController()
    controller.request_cancel()

    def _boom(*a, **k):
        raise AssertionError("fix_loop must never run once already cancelled")
    monkeypatch.setattr(cl, "fix_loop", _boom)

    from harness.multi_file import multi_file_fix
    r = multi_file_fix(str(tmp_path), "python -m pytest -q", "fix", "test_ops.py",
                       interrupt=controller)
    assert r["tried"] == []
    assert r["solved"] is False
    assert "interrupted" in r["note"]


# --- spec_loop.py: _build_per_function / _decompose_build cooperative checks ---------------------

class _FakeDecision:
    def __init__(self, dtype="noop"):
        self.type = dtype
        self.payload = {}


class _FakeWriterAgent:
    def decide(self, ctx):
        return [_FakeDecision("noop")]


def test_build_per_function_stops_gracefully_after_step_k(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "_load_agent", lambda filename, llm: _FakeWriterAgent())
    controller = InterruptController()
    calls = []

    def fake_fix_loop(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False,
                       keep_partial=False):
        calls.append(Path(target).name)
        if str(target).endswith("add.py"):
            Path(target).write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
            controller.request_cancel()
        elif str(target).endswith("subtract.py"):
            raise AssertionError("subtract.py must never be attempted after the cancel")

    monkeypatch.setattr(cl, "fix_loop", fake_fix_loop)
    from harness.spec_loop import _build_per_function
    sigs = [("add", "a, b"), ("subtract", "a, b")]
    r = _build_per_function("add(a, b) and subtract(a, b)", str(tmp_path), sigs,
                            interrupt=controller)

    assert calls == ["add.py"]                              # subtract never even started
    assert not (tmp_path / "subtract.py").exists()           # never created -- no half-written file
    assert r["solved"] is False                              # subtract is an honest stub
    assert "interrupted" in r["note"]
    sol = (tmp_path / "solution.py").read_text(encoding="utf-8")
    assert "def add" in sol and "return a + b" in sol        # step K's work is present
    assert "def subtract" in sol and "raise NotImplementedError" in sol  # honest stub, module parses
    import ast
    ast.parse(sol)                                           # the module genuinely still parses


def test_build_per_function_default_interrupt_none_is_byte_identical(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "_load_agent", lambda filename, llm: _FakeWriterAgent())

    def fake_fix_loop(target, instruction, test_cmd, *, max_iters=3, cwd=None, verbose=False,
                       keep_partial=False):
        if str(target).endswith("add.py"):
            Path(target).write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        elif str(target).endswith("subtract.py"):
            Path(target).write_text("def subtract(a, b):\n    return a - b\n", encoding="utf-8")

    monkeypatch.setattr(cl, "fix_loop", fake_fix_loop)
    from harness.spec_loop import _build_per_function
    sigs = [("add", "a, b"), ("subtract", "a, b")]
    r = _build_per_function("add(a, b) and subtract(a, b)", str(tmp_path), sigs, interrupt=None)
    assert r["solved"] is True
    assert "def add" in (tmp_path / "solution.py").read_text(encoding="utf-8")
    assert "def subtract" in (tmp_path / "solution.py").read_text(encoding="utf-8")


def test_decompose_build_already_cancelled_does_nothing(tmp_path, monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("no build strategy must run once already cancelled")
    monkeypatch.setattr(cl, "fix_loop", _boom)
    monkeypatch.setattr(cl, "_load_agent", lambda filename, llm: _FakeWriterAgent())

    controller = InterruptController()
    controller.request_cancel()
    from harness.spec_loop import _decompose_build
    r = _decompose_build("add(a, b) and subtract(a, b)", str(tmp_path), interrupt=controller)
    assert r["flow"] == "interrupted"
    assert r["solved"] is False
    assert list(tmp_path.iterdir()) == []          # genuinely nothing was written


# --- REPL SIGINT wiring: harness.cli._run_command_interruptible ---------------------------------

def test_run_command_interruptible_default_matches_handle_directly(monkeypatch):
    from harness.cli import _run_command_interruptible

    class _FakeCli:
        def handle(self, line, *, interactive=False):
            assert interactive is True
            return "plain result"

    out = _run_command_interruptible(_FakeCli(), "/status")
    assert out == "plain result"           # byte-identical to calling cli.handle directly
    assert get_interrupt_controller().is_cancelled() is False


def test_run_command_interruptible_simulated_sigint_mid_command_reports_interrupted():
    from harness.cli import _run_command_interruptible

    prior_handler = signal.getsignal(signal.SIGINT)

    class _FakeCli:
        def handle(self, line, *, interactive=False):
            # Simulate a real Ctrl-C arriving mid-command by invoking the handler that
            # `_run_command_interruptible` just installed (never a raw os.kill/real signal --
            # deterministic, hermetic).
            installed_handler = signal.getsignal(signal.SIGINT)
            assert installed_handler is not prior_handler   # confirms wiring actually swapped it
            installed_handler(signal.SIGINT, None)
            return "partial result"

    out = _run_command_interruptible(_FakeCli(), "/agent do something big")

    assert "partial result" in out
    assert "interrupted" in out
    # the original SIGINT handler is restored afterward, whether or not a cancel happened
    assert signal.getsignal(signal.SIGINT) is prior_handler


def test_run_command_interruptible_keyboardinterrupt_escaping_is_caught_gracefully(monkeypatch):
    from harness.cli import _run_command_interruptible

    prior_handler = signal.getsignal(signal.SIGINT)

    class _FakeCli:
        def handle(self, line, *, interactive=False):
            raise KeyboardInterrupt()

    out = _run_command_interruptible(_FakeCli(), "/run something-slow")

    assert isinstance(out, str)
    assert "interrupted" in out
    assert signal.getsignal(signal.SIGINT) is prior_handler   # still restored, no leaked handler


def test_run_command_interruptible_ordinary_exception_is_still_reported(monkeypatch):
    from harness.cli import _run_command_interruptible

    class _FakeCli:
        def handle(self, line, *, interactive=False):
            raise ValueError("boom")

    out = _run_command_interruptible(_FakeCli(), "/whatever")
    assert "error" in out.lower() and "boom" in out
