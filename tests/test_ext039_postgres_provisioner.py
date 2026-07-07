"""EXT-039 REQ-2 / TASK-3 tests: the real-service (Postgres) provisioner + independent oracle.

OFFLINE-HONEST (Tenet 3): the ENTIRE module is skipped when Docker is absent — it never fails
offline and never falsely passes. When Docker IS present, every test exercises a REAL Postgres
brought up on localhost. Fixtures are small hand-written CLIs (pure stdlib socket — a minimal
Postgres wire-protocol v3 client, trust auth, no psycopg2, no build_system/gemma run), so the tests
prove the ORACLE, not the model.
"""

# #EXT-039-REQ-2 Start
# TASK-3
import subprocess
import tempfile
from pathlib import Path

import pytest

from harness import service_provisioner as sp

pytestmark = pytest.mark.skipif(
    not sp.docker_available(), reason="docker unavailable — real-service tests skipped (offline-honest)"
)

# ------------------------------------------------------------------------------------------------
# Hand-written CLI fixtures. The "good" CLI embeds the SAME minimal Postgres wire-protocol v3 client
# (startup + simple query, trust auth — no password needed) as the oracle itself, reading
# PGHOST/PGPORT/PGDATABASE/PGUSER from env, pure stdlib socket only.
# ------------------------------------------------------------------------------------------------
_GOOD_CLI = r'''
import os, sys, socket

def _read_msg(sock):
    tag = sock.recv(1)
    if not tag: return None, None
    hdr = b""
    while len(hdr) < 4:
        chunk = sock.recv(4 - len(hdr))
        if not chunk: return None, None
        hdr += chunk
    length = int.from_bytes(hdr, "big") - 4
    body = b""
    while len(body) < length:
        chunk = sock.recv(length - len(body))
        if not chunk: return None, None
        body += chunk
    return tag, body

def connect(host, port, user, db):
    s = socket.create_connection((host, port), timeout=5)
    s.settimeout(5)
    params = b"user\x00" + user.encode() + b"\x00database\x00" + db.encode() + b"\x00\x00"
    body = (196608).to_bytes(4, "big") + params
    s.sendall((len(body) + 4).to_bytes(4, "big") + body)
    while True:
        tag, _ = _read_msg(s)
        if tag in (None, b"E"): return None
        if tag == b"Z": return s

def query(s, sql):
    payload = sql.encode() + b"\x00"
    s.sendall(b"Q" + (len(payload) + 4).to_bytes(4, "big") + payload)
    rows = []
    while True:
        tag, body = _read_msg(s)
        if tag is None: return None
        if tag == b"D":
            n = int.from_bytes(body[:2], "big"); off = 2; vals = []
            for _ in range(n):
                ln = int.from_bytes(body[off:off+4], "big", signed=True); off += 4
                vals.append(None if ln == -1 else body[off:off+ln].decode())
                if ln != -1: off += ln
            rows.append(tuple(vals))
        elif tag == b"Z":
            return rows

def main():
    host = os.environ.get("PGHOST", "127.0.0.1")
    port = int(os.environ.get("PGPORT", "5432"))
    db = os.environ.get("PGDATABASE", "app")
    user = os.environ.get("PGUSER", "app")
    conn = connect(host, port, user, db)
    a = sys.argv[1:]
    if not a:
        print("usage: add|list|count"); return
    if a[0] == "add":
        query(conn, "CREATE TABLE IF NOT EXISTS notes(id serial primary key, text text)")
        query(conn, "INSERT INTO notes(text) VALUES ('" + a[1].replace("'", "''") + "')")
        print("added")
    elif a[0] == "list":
        for row in (query(conn, "SELECT text FROM notes ORDER BY id") or []):
            print(row[0])
    elif a[0] == "count":
        rows = query(conn, "SELECT count(*) FROM notes")
        print(rows[0][0] if rows else 0)
    conn.close()

if __name__ == "__main__":
    main()
'''

# Prints "Saved!" on add but NEVER touches Postgres — the classic hollow-persistence fake.
_FAKE_SAVED_CLI = r'''
import sys
a = sys.argv[1:]
if a and a[0] == "add": print("Saved!")
elif a and a[0] == "count": print(0)
elif a and a[0] == "list": pass
'''

# Keeps state only in an in-process structure (resets every process) — never reaches real Postgres.
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


def _write_cli(src: str) -> Path:
    d = Path(tempfile.mkdtemp(prefix="pgprov_"))
    (d / "main.py").write_text(src, encoding="utf-8")
    return d


@pytest.fixture()
def pg_service():
    h = sp.provision_postgres()
    if not h.ok:
        pytest.skip(f"could not provision postgres: {h.note}")
    try:
        yield h
    finally:
        sp.teardown(h)


def _running_postgres_containers() -> int:
    try:
        out = subprocess.run(["docker", "ps", "--filter", "ancestor=postgres:16-alpine",
                              "--format", "{{.ID}}"], capture_output=True, text=True, timeout=15).stdout
        return len([x for x in out.splitlines() if x.strip()])
    except Exception:
        return -1


# ------------------------------------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------------------------------------
def test_provision_ready_then_teardown_leaves_no_container():
    before = _running_postgres_containers()
    h = sp.provision_postgres()
    assert h.ok and h.port > 0 and h.db and h.user, f"provision failed: {h.note}"
    conn = sp._pg_connect(h.host, h.port, user=h.user, db=h.db)
    assert conn is not None
    conn.close()
    sp.teardown(h)
    assert _running_postgres_containers() == before


def test_verify_ok_for_real_postgres_backed_cli(pg_service):
    """LOAD-BEARING GOOD: a CLI that really persists to Postgres passes, verified independently."""
    root = _write_cli(_GOOD_CLI)
    res = sp.verify_postgres_persistence(
        root, handle=pg_service,
        drive_cmds=[(["add", "hello"], None), (["add", "world"], None)],
        assertions=[
            lambda q: q("SELECT count(*) FROM notes") == [("2",)],
            lambda q: q("SELECT text FROM notes ORDER BY id") == [("hello",), ("world",)],
        ],
        cross_invocation_cmd=(["count"], None),
    )
    assert res.ok, f"expected ok for a real postgres-backed CLI, got: {res.note} / {res.failures}"
    assert res.rows_checked == 2


def test_verify_catches_fake_saved_cli(pg_service):
    """LOAD-BEARING CATCH: a CLI that prints 'Saved!' but never writes to Postgres must FAIL."""
    root = _write_cli(_FAKE_SAVED_CLI)
    res = sp.verify_postgres_persistence(
        root, handle=pg_service,
        drive_cmds=[(["add", "hello"], None)],
        assertions=[lambda q: q("SELECT count(*) FROM notes") == [("1",)]],
    )
    assert not res.ok, "a hollow 'Saved!'-printing CLI must NOT pass the persistence oracle"


def test_verify_catches_inprocess_only_cli(pg_service):
    """A CLI keeping state only in-process (never reaching real Postgres) must FAIL."""
    root = _write_cli(_INPROC_CLI)
    res = sp.verify_postgres_persistence(
        root, handle=pg_service,
        drive_cmds=[(["add", "hello"], None)],
        assertions=[lambda q: (q("SELECT count(*) FROM notes") or [("0",)]) == [("1",)]],
    )
    assert not res.ok, "in-process-only storage must NOT pass (real Postgres has no notes table)"


def test_verify_fails_on_broken_ready_timeout():
    # An absurdly short ready_timeout_s must deterministically fail to provision (never raise).
    h = sp.provision_postgres(ready_timeout_s=0.01)
    assert not h.ok
    sp.teardown(h)  # safe even though provisioning failed


def test_verify_never_raises_on_missing_entrypoint(pg_service):
    empty = Path(tempfile.mkdtemp(prefix="pgprov_empty_"))
    res = sp.verify_postgres_persistence(
        empty, handle=pg_service, drive_cmds=[(["add", "x"], None)],
        assertions=[lambda q: True])
    assert not res.ok and "entrypoint not found" in res.note


def test_verify_never_raises_on_malformed_inputs(pg_service):
    root = _write_cli(_GOOD_CLI)
    r1 = sp.verify_postgres_persistence(root, handle=pg_service,
                                        drive_cmds=[("not-a-pair")], assertions=[lambda q: True])
    assert not r1.ok
    r2 = sp.verify_postgres_persistence(root, handle=pg_service,
                                        drive_cmds=[(["add", "x"], None)], assertions=[])
    assert not r2.ok and "assertions" in r2.note


def test_verify_fails_without_live_handle():
    dead = sp.ServiceHandle(kind="postgres", ok=False, note="not provisioned")
    res = sp.verify_postgres_persistence(_write_cli(_GOOD_CLI), handle=dead,
                                         drive_cmds=[(["add", "x"], None)],
                                         assertions=[lambda q: True])
    assert not res.ok and "no live service handle" in res.note


def test_teardown_safe_on_none_and_failed_handle():
    sp.teardown(None)
    sp.teardown(sp.ServiceHandle(kind="postgres", ok=False))
# #EXT-039-REQ-2 End
