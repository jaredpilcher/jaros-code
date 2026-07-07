"""EXT-039 REQ-2 / TASK-2 tests: the real-service (Redis) provisioner + independent oracle.

OFFLINE-HONEST (Tenet 3): the ENTIRE module is skipped when Docker is absent — it never fails
offline and never falsely passes. When Docker IS present, every test exercises a REAL Redis brought
up on localhost. Fixtures are small hand-written CLIs (pure stdlib socket RESP — no redis-py, no
build_system/gemma run), so the tests prove the ORACLE, not the model.
"""

# #EXT-039-REQ-2 Start
# TASK-2
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from harness import service_provisioner as sp

pytestmark = pytest.mark.skipif(
    not sp.docker_available(), reason="docker unavailable — real-service tests skipped (offline-honest)"
)

# ------------------------------------------------------------------------------------------------
# Hand-written CLI fixtures (stdlib socket RESP only). Each reads REDIS_HOST/REDIS_PORT from env.
# ------------------------------------------------------------------------------------------------
_GOOD_CLI = r'''
import os, sys, socket

def _read(fp):
    line = fp.readline(); tag, rest = line[:1], line[1:-2]
    if tag == b"+": return rest.decode()
    if tag == b"-": return None
    if tag == b":": return int(rest)
    if tag == b"$":
        n = int(rest)
        if n == -1: return None
        d = fp.read(n); fp.read(2); return d.decode()
    if tag == b"*":
        n = int(rest); return [_read(fp) for _ in range(n)]

def resp(*args):
    out = b"*%d\r\n" % len(args)
    for a in args:
        b = str(a).encode(); out += b"$%d\r\n%s\r\n" % (len(b), b)
    s = socket.create_connection((os.environ.get("REDIS_HOST", "127.0.0.1"),
                                  int(os.environ.get("REDIS_PORT", "6379"))), timeout=5)
    s.sendall(out); r = _read(s.makefile("rb")); s.close(); return r

def main():
    a = sys.argv[1:]
    if not a: print("usage: add|list|count"); return
    if a[0] == "add": resp("RPUSH", "notes", a[1]); print("added")
    elif a[0] == "list":
        for x in (resp("LRANGE", "notes", "0", "-1") or []): print(x)
    elif a[0] == "count": print(resp("LLEN", "notes"))

if __name__ == "__main__":
    main()
'''

# Prints "Saved!" on add but NEVER touches Redis — the classic hollow-persistence fake.
_FAKE_SAVED_CLI = r'''
import sys
a = sys.argv[1:]
if a and a[0] == "add": print("Saved!")
elif a and a[0] == "count": print(0)
elif a and a[0] == "list": pass
'''

# Keeps state only in an in-process structure (resets every process) — never reaches real Redis.
_INPROC_CLI = r'''
import sys
_MEM = []
def main():
    a = sys.argv[1:]
    if a and a[0] == "add": _MEM.append(a[1]); print("added (in-memory)")
    elif a and a[0] == "count": print(len(_MEM))
    elif a and a[0] == "list":
        for x in _MEM: print(x)
if __name__ == "__main__":
    main()
'''

# Exits non-zero on add — a broken CLI.
_BROKEN_CLI = r'''
import sys
sys.stderr.write("boom\n"); sys.exit(2)
'''


def _write_cli(src: str) -> Path:
    d = Path(tempfile.mkdtemp(prefix="svcprov_"))
    (d / "main.py").write_text(src, encoding="utf-8")
    return d


@pytest.fixture()
def redis_service():
    h = sp.provision_redis()
    if not h.ok:
        pytest.skip(f"could not provision redis: {h.note}")
    try:
        yield h
    finally:
        sp.teardown(h)


def _running_redis_containers() -> int:
    try:
        out = subprocess.run(["docker", "ps", "--filter", "ancestor=redis:7-alpine",
                              "--format", "{{.ID}}"], capture_output=True, text=True, timeout=15).stdout
        return len([x for x in out.splitlines() if x.strip()])
    except Exception:
        return -1


# ------------------------------------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------------------------------------
def test_provision_ready_then_teardown_leaves_no_container():
    before = _running_redis_containers()
    h = sp.provision_redis()
    assert h.ok and h.port > 0, f"provision failed: {h.note}"
    # Ready: a fresh independent PING answers PONG.
    assert sp._resp_command(h.host, h.port, "PING") == "PONG"
    sp.teardown(h)
    # Container is gone (--rm auto-removes on stop).
    assert _running_redis_containers() == before


def test_docker_available_is_true_here():
    # This file only runs when docker_available() — sanity that the gate agrees.
    assert sp.docker_available() is True


def test_verify_ok_for_real_redis_backed_cli(redis_service):
    """LOAD-BEARING GOOD: a CLI that really persists to Redis passes, verified independently."""
    root = _write_cli(_GOOD_CLI)
    res = sp.verify_redis_persistence(
        root, handle=redis_service,
        drive_cmds=[(["add", "hello"], None), (["add", "world"], None)],
        assertions=[
            (("LLEN", "notes"), 2),
            lambda call: call("LRANGE", "notes", "0", "-1") == ["hello", "world"],
        ],
        cross_invocation_cmd=(["count"], None),
    )
    assert res.ok, f"expected ok for a real redis-backed CLI, got: {res.note} / {res.failures}"
    assert res.rows_checked == 2


def test_verify_catches_fake_saved_cli(redis_service):
    """LOAD-BEARING CATCH: a CLI that prints 'Saved!' but never writes to Redis must FAIL."""
    root = _write_cli(_FAKE_SAVED_CLI)
    res = sp.verify_redis_persistence(
        root, handle=redis_service,
        drive_cmds=[(["add", "hello"], None)],
        assertions=[(("LLEN", "notes"), 1)],
    )
    assert not res.ok, "a hollow 'Saved!'-printing CLI must NOT pass the persistence oracle"
    assert "hollow-persistence" in res.note or res.failures


def test_verify_catches_inprocess_only_cli(redis_service):
    """A CLI keeping state only in-process (never reaching real Redis) must FAIL."""
    root = _write_cli(_INPROC_CLI)
    res = sp.verify_redis_persistence(
        root, handle=redis_service,
        drive_cmds=[(["add", "hello"], None)],
        assertions=[(("LLEN", "notes"), 1)],
    )
    assert not res.ok, "in-process-only storage must NOT pass (real Redis stays empty)"


def test_verify_fails_on_broken_cli(redis_service):
    root = _write_cli(_BROKEN_CLI)
    res = sp.verify_redis_persistence(
        root, handle=redis_service,
        drive_cmds=[(["add", "hello"], None)],
        assertions=[(("LLEN", "notes"), 1)],
    )
    assert not res.ok and "non-zero exit" in res.note


def test_verify_never_raises_on_missing_entrypoint(redis_service):
    empty = Path(tempfile.mkdtemp(prefix="svcprov_empty_"))
    res = sp.verify_redis_persistence(
        empty, handle=redis_service, drive_cmds=[(["add", "x"], None)],
        assertions=[(("LLEN", "notes"), 1)])
    assert not res.ok and "entrypoint not found" in res.note


def test_verify_never_raises_on_malformed_inputs(redis_service):
    root = _write_cli(_GOOD_CLI)
    # malformed drive_cmds entry
    r1 = sp.verify_redis_persistence(root, handle=redis_service,
                                     drive_cmds=[("not-a-pair")], assertions=[(("LLEN", "notes"), 0)])
    assert not r1.ok
    # empty assertions
    r2 = sp.verify_redis_persistence(root, handle=redis_service,
                                     drive_cmds=[(["add", "x"], None)], assertions=[])
    assert not r2.ok and "assertions" in r2.note


def test_verify_fails_without_live_handle():
    dead = sp.ServiceHandle(kind="redis", ok=False, note="not provisioned")
    res = sp.verify_redis_persistence(_write_cli(_GOOD_CLI), handle=dead,
                                      drive_cmds=[(["add", "x"], None)],
                                      assertions=[(("LLEN", "notes"), 1)])
    assert not res.ok and "no live service handle" in res.note


def test_teardown_safe_on_none_and_failed_handle():
    # Must never raise on a None or a handle with no container.
    sp.teardown(None)
    sp.teardown(sp.ServiceHandle(kind="redis", ok=False))
# #EXT-039-REQ-2 End
