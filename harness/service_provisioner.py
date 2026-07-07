"""EXT-039 REQ-2: real-service (Redis + Postgres) provisioners + independent persistence oracles.

**The gap this closes (Tenet 3, the next rung above ``harness/datastore_oracle.py`` REQ-1):** REQ-1
proved the acceptance-oracle PATTERN for the one datastore stdlib already ships (``sqlite3``, a
file, no running service). This module takes the SAME pattern to a REAL running service — Redis —
by (a) bringing a real Redis up on localhost via Docker, (b) driving the built system's CLI against
it, and (c) INDEPENDENTLY verifying the data really landed in Redis via this module's OWN client —
never trusting the CLI's stdout — and re-checking across a second, entirely fresh CLI invocation. It
plugs into the SAME ``verify_persistence``-shaped contract REQ-1 established (clean-state → drive →
independently verify → cross-invocation → never-raise honest ``ok=False``+note).

**Pure stdlib, no new dependency (mirrors ``datastore_oracle``'s discipline):** the independent Redis
client is a tiny RESP-over-raw-``socket`` speaker (``_resp_command``) — NOT ``redis-py``. The
independent Postgres client is a minimal hand-rolled wire-protocol v3 speaker (``_pg_connect``/
``_pg_query`` — startup + simple-query message flow only) — NOT ``psycopg2``/``pg8000``. The Postgres
container is provisioned with ``POSTGRES_HOST_AUTH_METHOD=trust`` specifically so the client never
needs to implement SCRAM-SHA-256 authentication; this is safe because the container is ephemeral,
bound to loopback only, and torn down at the end of every run — never a persistent or
network-exposed service. The only external requirement for EITHER service is the ``docker`` CLI, and
every code path degrades honestly when it is absent (``docker_available()`` gates everything; a
provision call with no Docker returns an honest failed :class:`ServiceHandle`, never raises).

**Offline-honest (Tenet 3):** this needs a running service, which the repo's offline/no-network test
discipline cannot exercise when Docker is absent — so both
``tests/test_ext039_service_provisioner.py`` (Redis) and ``tests/test_ext039_postgres_provisioner.py``
(Postgres) skip ENTIRELY when ``docker_available()`` is False. Never fails offline, never falsely
passes.

**Honest platform/egress note (mirrors ``harness/secure_exec.py``):** the CLI-under-test is driven
through ``harness.secure_exec.run_sandboxed`` (scrubbed environment + resource caps + timeout +
process-tree kill), the same house sandbox ``system_suite._run_cli`` uses — called here one layer
down so the service's connection env vars can be injected via ``extra_env`` into the otherwise-
scrubbed environment (``REDIS_HOST``/``REDIS_PORT`` for Redis; the standard libpq
``PGHOST``/``PGPORT``/``PGDATABASE``/``PGUSER`` for Postgres). ``run_sandboxed`` does NOT enforce
network egress at runtime today (documented: only the static ``scan_code`` gate does), which is WHY a
service-backed CLI can reach the provisioned loopback service here. On a future Linux/netns
deployment with real runtime egress enforcement, the provisioned ``host:port`` must be added to that
run's egress allow-list — recorded here honestly, not silently assumed.

**Named-but-NOT-built-here:** Qdrant/Cassandra provisioners (each a different wire protocol) and a
live DATASTORE creation-suite task that runs inside the suite loop against a provisioned service
remain follow-ups under REQ-2 — Redis (TASK-2) and Postgres (TASK-3) are the two rungs landed here.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# #EXT-039-REQ-2 Start
# TASK-2: reuse the house sandbox (scrubbed env + caps + timeout + tree-kill) at the run_sandboxed
# layer (not _run_cli) so REDIS_HOST/REDIS_PORT can be injected via extra_env for the CLI-under-test.
from harness.secure_exec import run_sandboxed, EgressPolicy

DEFAULT_ENTRY_NAME = "main.py"
_DOCKER_TIMEOUT_S = 25.0
_CLI_TIMEOUT_S = 30.0
_REDIS_CONTAINER_PORT = 6379
_POSTGRES_CONTAINER_PORT = 5432


@dataclass
class ServiceHandle:
    """A provisioned (or failed-to-provision) service. ``ok`` is True only when the service is up
    and answered a readiness probe; ``container_id`` is the Docker id to tear down (may be set even
    when ``ok`` is False, so a partially-started container is never leaked). ``host``/``port`` are
    where the CLI-under-test should connect (exposed to it via ``REDIS_HOST``/``REDIS_PORT`` for
    ``kind="redis"``, or ``PGHOST``/``PGPORT``/``PGDATABASE``/``PGUSER`` for ``kind="postgres"``).
    ``db``/``user`` are populated for ``kind="postgres"`` only (Redis has no notion of either)."""

    kind: str
    host: str = "127.0.0.1"
    port: int = 0
    container_id: "str | None" = None
    ok: bool = False
    note: str = ""
    db: "str | None" = None
    user: "str | None" = None


@dataclass
class ServiceResult:
    """Result of :func:`verify_redis_persistence` — same shape as
    ``datastore_oracle.DatastoreResult``. ``ok`` is True only when the handle was up, both CLI
    invocations exited cleanly, and every assertion held against real Redis state on BOTH the
    post-drive and the post-cross-invocation checks. Never fabricated."""

    ok: bool
    rows_checked: int = 0
    failures: "list" = field(default_factory=list)
    note: str = ""


def _docker(*args: str, timeout: float = _DOCKER_TIMEOUT_S) -> "tuple[int, str, str]":
    """Run a ``docker`` CLI command; return ``(returncode, stdout, stderr)`` stripped. NEVER raises
    — a missing binary, a timeout, or any error is an honest non-zero return, not an exception."""
    try:
        p = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except Exception as exc:  # noqa: BLE001
        return 1, "", str(exc)


def docker_available() -> bool:
    """Best-effort, NEVER-RAISE gate: the ``docker`` CLI exists AND its daemon answers. Every
    provision call and every test in this spec consults this first."""
    if shutil.which("docker") is None:
        return False
    rc, _out, _err = _docker("info", timeout=12.0)
    return rc == 0


# ------------------------------------------------------------------------------------------------
# Tiny RESP-over-raw-socket client (stdlib only — NOT redis-py). Used both for readiness probing
# and for the module's OWN independent verification of Redis state.
# ------------------------------------------------------------------------------------------------
def _resp_encode(args: "tuple") -> bytes:
    out = b"*%d\r\n" % len(args)
    for a in args:
        b = a if isinstance(a, bytes) else str(a).encode()
        out += b"$%d\r\n%s\r\n" % (len(b), b)
    return out


def _resp_read(fp) -> Any:
    line = fp.readline()
    if not line:
        raise ConnectionError("no RESP reply (connection closed)")
    tag, rest = line[:1], line[1:-2]  # strip trailing CRLF
    if tag == b"+":
        return rest.decode()
    if tag == b"-":
        return RESPError(rest.decode())
    if tag == b":":
        return int(rest)
    if tag == b"$":
        n = int(rest)
        if n == -1:
            return None
        data = fp.read(n)
        fp.read(2)  # trailing CRLF
        return data.decode()
    if tag == b"*":
        n = int(rest)
        if n == -1:
            return None
        return [_resp_read(fp) for _ in range(n)]
    raise ValueError(f"unrecognized RESP type tag {tag!r}")


class RESPError(str):
    """A Redis ``-ERR ...`` reply, surfaced as a distinct (falsy-comparable) string subtype so a
    caller can tell an error reply apart from a normal bulk string if it cares. Never raised."""


def _resp_command(host: str, port: int, *args: Any, timeout_s: float = 5.0) -> Any:
    """Send ONE RESP command and return the parsed reply (``str``/``int``/``list``/``None``, or a
    :class:`RESPError` for a ``-ERR`` reply). NEVER raises: any socket/parse error is returned as an
    :class:`RESPError` sentinel the caller treats as a failed reply."""
    s = None
    try:
        s = socket.create_connection((host, port), timeout=timeout_s)
        s.settimeout(timeout_s)
        s.sendall(_resp_encode(tuple(args)))
        fp = s.makefile("rb")
        return _resp_read(fp)
    except Exception as exc:  # noqa: BLE001
        return RESPError(f"resp command {args!r} failed: {exc}")
    finally:
        try:
            if s is not None:
                s.close()
        except Exception:
            pass


# ------------------------------------------------------------------------------------------------
# Provisioning
# ------------------------------------------------------------------------------------------------
def _read_mapped_port(container_id: str, container_port: int = _REDIS_CONTAINER_PORT) -> "int | None":
    """Parse ``docker port <id> <container_port>/tcp`` (e.g. ``0.0.0.0:49153``) → the host port int,
    or None."""
    rc, out, _err = _docker("port", container_id, f"{container_port}/tcp", timeout=12.0)
    if rc != 0 or not out:
        return None
    # Output may have several lines (IPv4/IPv6); take the first host:port and its trailing number.
    first = out.splitlines()[0].strip()
    try:
        return int(first.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return None


def provision_redis(*, image: str = "redis:7-alpine", host_port: int = 0,
                     mem_cap: str = "128m", ready_timeout_s: float = 20.0) -> ServiceHandle:
    """Bring a real Redis up on localhost via Docker and probe it ready. ``host_port=0`` lets Docker
    pick a free loopback port (so parallel/repeat runs never collide). Applies ``--memory=<mem_cap>``
    and ``--rm`` (auto-remove on stop). Returns an ``ok=True`` :class:`ServiceHandle` once Redis
    answers ``PING``→``PONG``; on ANY failure it tears down the partial container and returns
    ``ok=False`` with a diagnostic note. NEVER raises, NEVER leaks a container."""
    if not docker_available():
        return ServiceHandle(kind="redis", ok=False, note="docker unavailable")

    publish = (f"127.0.0.1:{host_port}:{_REDIS_CONTAINER_PORT}" if host_port
               else f"127.0.0.1::{_REDIS_CONTAINER_PORT}")
    rc, out, err = _docker("run", "-d", "--rm", f"--memory={mem_cap}",
                           "-p", publish, image, timeout=90.0)
    if rc != 0 or not out:
        return ServiceHandle(kind="redis", ok=False, note=f"docker run failed: {(err or out)[:300]}")
    container_id = out.splitlines()[0].strip()

    try:
        port = host_port or _read_mapped_port(container_id)
        if not port:
            return _fail_and_teardown(container_id, "could not determine the mapped host port")

        deadline = time.time() + max(1.0, ready_timeout_s)
        while time.time() < deadline:
            if _resp_command("127.0.0.1", port, "PING", timeout_s=1.5) == "PONG":
                return ServiceHandle(kind="redis", host="127.0.0.1", port=port,
                                     container_id=container_id, ok=True, note="ok")
            time.sleep(0.3)
        return _fail_and_teardown(container_id,
                                  f"redis did not answer PING within {ready_timeout_s}s")
    except Exception as exc:  # noqa: BLE001  — never raise, never leak
        return _fail_and_teardown(container_id, f"provision_redis failed unexpectedly: {exc}")


def _fail_and_teardown(container_id: str, note: str, kind: str = "redis") -> ServiceHandle:
    teardown(ServiceHandle(kind=kind, container_id=container_id, ok=False))
    return ServiceHandle(kind=kind, ok=False, note=note)


def teardown(handle: "ServiceHandle | None") -> None:
    """Stop the provisioned container (``--rm`` auto-removes it). Best-effort, short timeout, safe
    to call on ``None`` or a failed handle. NEVER raises. Every provision site MUST call this in a
    ``finally`` (mirrors ``server_oracle._kill_tree``'s teardown discipline)."""
    cid = getattr(handle, "container_id", None) if handle is not None else None
    if not cid:
        return
    _docker("stop", "-t", "1", cid, timeout=20.0)


# ------------------------------------------------------------------------------------------------
# Independent persistence oracle (verify_persistence-shaped, for Redis)
# ------------------------------------------------------------------------------------------------
def _run_cli_env(py_exe: str, entry_path: Path, argv: "list", stdin: "str | None",
                 cwd: Path, env: dict) -> "tuple[bool, str]":
    """Drive the built CLI via the house sandbox (``run_sandboxed``: scrubbed env + caps + timeout +
    tree-kill), injecting ``env`` (the service's REDIS_HOST/REDIS_PORT) via ``extra_env`` so the
    CLI-under-test can reach the provisioned service. Returns ``(ok, stdout+stderr)``. Never raises."""
    cmd = [py_exe, str(entry_path)] + list(argv or [])
    result = run_sandboxed(cmd, cwd=str(cwd), egress_policy=EgressPolicy.DENY_ALL,
                           timeout=_CLI_TIMEOUT_S, extra_env=dict(env or {}), stdin=stdin)
    out = (result.get("stdout") or "") + (result.get("stderr") or "")
    if not out:
        out = result.get("note") or ""
    return bool(result.get("ok")), out


def _unpack_cmd(cmd: Any) -> "tuple[list, str | None]":
    """A drive/cross-invocation command is a 2-item ``(argv, stdin)`` sequence."""
    argv, stdin = cmd
    argv = list(argv) if isinstance(argv, (list, tuple)) else ([] if argv is None else [str(argv)])
    stdin = stdin if (stdin is None or isinstance(stdin, str)) else str(stdin)
    return argv, stdin


def _check_assertions(host: str, port: int, asserts: "list") -> "tuple[int, list]":
    """Evaluate each assertion against REAL Redis state via this module's own RESP client (never the
    CLI's stdout). Each assertion is either a ``callable(resp_call) -> bool`` (where ``resp_call`` is
    ``lambda *a: _resp_command(host, port, *a)``) or a ``(argv_tuple, expected)`` pair. Returns
    ``(n_passed, failures)``. Never raises."""
    passed = 0
    failures: "list" = []

    def resp_call(*a: Any) -> Any:
        return _resp_command(host, port, *a)

    for idx, spec in enumerate(asserts):
        try:
            if callable(spec):
                ok = bool(spec(resp_call))
            else:
                argv, expected = spec
                got = _resp_command(host, port, *argv)
                ok = (got == expected)
            if ok:
                passed += 1
            else:
                failures.append(f"assertion[{idx}] did not hold against real Redis state")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"assertion[{idx}] raised while evaluating: {exc}")
    return passed, failures


def verify_redis_persistence(root: Any, *, handle: ServiceHandle, drive_cmds: "list",
                             assertions: "list", python_exe: "str | None" = None,
                             cross_invocation_cmd: "tuple | None" = None,
                             entry_name: str = DEFAULT_ENTRY_NAME) -> ServiceResult:
    """The load-bearing Redis oracle — mirrors ``datastore_oracle.verify_persistence`` stage-for-
    stage, against the provisioned Redis in ``handle`` instead of a ``.db`` file:

    1. **Clean state** — independently ``FLUSHDB`` via this module's RESP client.
    2. **Drive** — run each ``(argv, stdin)`` in ``drive_cmds`` as its own sandboxed CLI process,
       with ``REDIS_HOST``/``REDIS_PORT`` injected so the CLI can reach the service.
    3. **Independently verify** — evaluate ``assertions`` against REAL Redis state (this module's
       own client), never the CLI's stdout.
    4. **Cross-invocation** — one more fresh CLI process (defaults to re-running the last drive cmd),
       then re-evaluate the same assertions — proving the data really reached the external service.

    ``ok=True`` only when the handle was up, both CLI invocations exited cleanly, and every assertion
    held on BOTH checks. NEVER RAISES — any failure is an honest ``ok=False`` + diagnostic note."""
    try:
        if handle is None or not getattr(handle, "ok", False):
            return ServiceResult(ok=False, note="no live service handle (provisioning failed/absent)")
        host, port = handle.host, handle.port

        try:
            root_path = Path(root)
        except (TypeError, ValueError) as exc:
            return ServiceResult(ok=False, note=f"invalid root: {root!r}: {exc}")
        if not root_path.exists() or not root_path.is_dir():
            return ServiceResult(ok=False, note=f"root does not exist: {root_path}")

        entry_path = root_path / entry_name
        if not entry_path.is_file():
            return ServiceResult(ok=False, note=f"entrypoint not found: {entry_path}")

        py_exe = python_exe or sys.executable or "python"
        env = {"REDIS_HOST": str(host), "REDIS_PORT": str(port)}

        cmds = list(drive_cmds) if isinstance(drive_cmds, (list, tuple)) else None
        if not cmds:
            return ServiceResult(ok=False, note="no drive_cmds supplied (must be a non-empty list)")
        asserts = list(assertions) if isinstance(assertions, (list, tuple)) else None
        if not asserts:
            return ServiceResult(ok=False, note="no assertions supplied (must be a non-empty list)")

        # Step 1 — clean state (independent FLUSHDB).
        flush = _resp_command(host, port, "FLUSHDB")
        if isinstance(flush, RESPError):
            return ServiceResult(ok=False, note=f"could not FLUSHDB the service to clean state: {flush}")

        # Step 2 — drive each command as its own fresh sandboxed subprocess.
        for i, raw_cmd in enumerate(cmds):
            try:
                argv, stdin = _unpack_cmd(raw_cmd)
            except Exception as exc:  # noqa: BLE001
                return ServiceResult(ok=False, note=f"malformed drive_cmds[{i}]: {exc}")
            ok, out = _run_cli_env(py_exe, entry_path, argv, stdin, root_path, env)
            if not ok:
                return ServiceResult(
                    ok=False, note=f"drive_cmds[{i}] CLI invocation failed (non-zero exit): {out[:500]!r}")

        # Step 3 — independent check #1 (right after the drive commands).
        passed1, failures1 = _check_assertions(host, port, asserts)
        if failures1:
            return ServiceResult(
                ok=False, rows_checked=passed1, failures=failures1,
                note="assertions failed against real Redis right after the drive commands — the "
                     "CLI's stdout may claim success but nothing actually reached Redis "
                     "(hollow-persistence catch)")

        # Step 4 — cross-invocation: one more, entirely fresh CLI process.
        cross_cmd = cross_invocation_cmd if cross_invocation_cmd is not None else cmds[-1]
        try:
            cross_argv, cross_stdin = _unpack_cmd(cross_cmd)
        except Exception as exc:  # noqa: BLE001
            return ServiceResult(ok=False, rows_checked=passed1,
                                 note=f"malformed cross_invocation_cmd: {exc}")
        ok, out = _run_cli_env(py_exe, entry_path, cross_argv, cross_stdin, root_path, env)
        if not ok:
            return ServiceResult(ok=False, rows_checked=passed1,
                                 note=f"cross-invocation CLI call failed (non-zero exit): {out[:500]!r}")

        passed2, failures2 = _check_assertions(host, port, asserts)
        if failures2:
            return ServiceResult(
                ok=False, rows_checked=passed2, failures=failures2,
                note="assertions failed after a SECOND fresh CLI invocation — the state did not "
                     "survive as real external Redis data (in-process-only storage)")

        return ServiceResult(ok=True, rows_checked=passed2, failures=[],
                             note="ok: real persisted Redis state verified independently, both "
                                  "immediately and across a second fresh CLI invocation")
    except Exception as exc:  # noqa: BLE001  — never raise
        return ServiceResult(ok=False, note=f"verify_redis_persistence failed unexpectedly: {exc}")


# ------------------------------------------------------------------------------------------------
# Postgres rung (TASK-3): a minimal, hand-rolled Postgres wire-protocol v3 client over a raw
# stdlib socket — mirroring the Redis RESP client's own-protocol discipline exactly. The container
# is configured with POSTGRES_HOST_AUTH_METHOD=trust (safe: an ephemeral, loopback-only, local-dev
# container torn down at the end of every run) so the client needs only the STARTUP + SIMPLE QUERY
# message flow, never SCRAM-SHA-256 authentication.
# ------------------------------------------------------------------------------------------------
def provision_postgres(*, image: str = "postgres:16-alpine", host_port: int = 0,
                        mem_cap: str = "256m", db: str = "app", user: str = "app",
                        ready_timeout_s: float = 30.0) -> ServiceHandle:
    """Bring a real Postgres up on localhost via Docker (``POSTGRES_HOST_AUTH_METHOD=trust`` — no
    password needed for this ephemeral, loopback-only, torn-down-every-run container) and probe it
    ready via the image's own bundled ``pg_isready``. ``host_port=0`` lets Docker pick a free
    loopback port. On ANY failure tears down the partial container and returns ``ok=False`` with a
    diagnostic note. NEVER raises, NEVER leaks a container."""
    if not docker_available():
        return ServiceHandle(kind="postgres", ok=False, note="docker unavailable")

    publish = (f"127.0.0.1:{host_port}:{_POSTGRES_CONTAINER_PORT}" if host_port
               else f"127.0.0.1::{_POSTGRES_CONTAINER_PORT}")
    rc, out, err = _docker("run", "-d", "--rm", f"--memory={mem_cap}",
                           "-e", f"POSTGRES_DB={db}", "-e", f"POSTGRES_USER={user}",
                           "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
                           "-p", publish, image, timeout=90.0)
    if rc != 0 or not out:
        return ServiceHandle(kind="postgres", ok=False,
                             note=f"docker run failed: {(err or out)[:300]}")
    container_id = out.splitlines()[0].strip()

    try:
        port = host_port or _read_mapped_port(container_id, _POSTGRES_CONTAINER_PORT)
        if not port:
            return _fail_and_teardown(container_id, "could not determine the mapped host port",
                                      kind="postgres")

        deadline = time.time() + max(1.0, ready_timeout_s)
        while time.time() < deadline:
            rc, _out, _err = _docker("exec", container_id, "pg_isready", "-U", user, "-d", db,
                                     timeout=5.0)
            if rc == 0:
                # pg_isready reports the server accepting connections, but the module's OWN
                # wire-protocol client has occasionally raced it right at startup — never declare
                # ready unless a real connect via THIS module's client also succeeds.
                probe = _pg_connect("127.0.0.1", port, user=user, db=db, timeout_s=3.0)
                if probe is not None:
                    probe.close()
                    return ServiceHandle(kind="postgres", host="127.0.0.1", port=port,
                                         container_id=container_id, ok=True, note="ok",
                                         db=db, user=user)
            time.sleep(0.3)
        return _fail_and_teardown(container_id,
                                  f"postgres did not become ready within {ready_timeout_s}s",
                                  kind="postgres")
    except Exception as exc:  # noqa: BLE001  — never raise, never leak
        return _fail_and_teardown(container_id, f"provision_postgres failed unexpectedly: {exc}",
                                  kind="postgres")


def _pg_read_msg(sock: "socket.socket") -> "tuple[bytes, bytes] | tuple[None, None]":
    """Read one Postgres backend message: a 1-byte type tag + a 4-byte big-endian length (inclusive
    of itself) + the body. Returns ``(type_tag, body)``, or ``(None, None)`` on EOF/short read."""
    tag = sock.recv(1)
    if not tag:
        return None, None
    hdr = b""
    while len(hdr) < 4:
        chunk = sock.recv(4 - len(hdr))
        if not chunk:
            return None, None
        hdr += chunk
    length = int.from_bytes(hdr, "big") - 4
    body = b""
    while len(body) < length:
        chunk = sock.recv(length - len(body))
        if not chunk:
            return None, None
        body += chunk
    return tag, body


def _pg_connect(host: str, port: int, *, user: str, db: str,
                timeout_s: float = 5.0) -> "socket.socket | None":
    """Open a Postgres v3 connection: send the StartupMessage, consume messages until
    ``ReadyForQuery`` ('Z') or an error ('E'). Returns the connected socket on success, or ``None``
    on ANY failure (auth error, connection refused, malformed reply) — NEVER raises."""
    sock = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout_s)
        sock.settimeout(timeout_s)
        params = b"user\x00" + user.encode() + b"\x00database\x00" + db.encode() + b"\x00\x00"
        body = (196608).to_bytes(4, "big") + params  # protocol version 3.0
        sock.sendall((len(body) + 4).to_bytes(4, "big") + body)
        while True:
            tag, _body = _pg_read_msg(sock)
            if tag is None or tag == b"E":
                sock.close()
                return None
            if tag == b"Z":
                return sock
    except Exception:  # noqa: BLE001
        try:
            if sock is not None:
                sock.close()
        except Exception:
            pass
        return None


def _pg_query(sock: "socket.socket", sql: str) -> "list[tuple] | None":
    """Send a Simple Query message on an already-connected socket and parse the reply
    (``RowDescription``/``DataRow``/``CommandComplete`` until ``ReadyForQuery``). Returns the parsed
    rows as a list of string tuples (``[]`` for a query with no rows, e.g. DDL), or ``None`` on an
    error reply or any parse failure. NEVER raises."""
    try:
        payload = sql.encode() + b"\x00"
        sock.sendall(b"Q" + (len(payload) + 4).to_bytes(4, "big") + payload)
        rows: "list[tuple]" = []
        errored = False
        while True:
            tag, body = _pg_read_msg(sock)
            if tag is None:
                return None
            if tag == b"D":  # DataRow
                n = int.from_bytes(body[:2], "big")
                off = 2
                vals: "list[str | None]" = []
                for _ in range(n):
                    ln = int.from_bytes(body[off:off + 4], "big", signed=True)
                    off += 4
                    if ln == -1:
                        vals.append(None)
                    else:
                        vals.append(body[off:off + ln].decode())
                        off += ln
                rows.append(tuple(vals))
            elif tag == b"E":  # ErrorResponse
                errored = True
            elif tag == b"Z":  # ReadyForQuery
                return None if errored else rows
    except Exception:  # noqa: BLE001
        return None


def _unpack_cmd_pg(cmd: Any) -> "tuple[list, str | None]":
    return _unpack_cmd(cmd)  # identical shape to the Redis helper; named separately for clarity


def _check_pg_assertions(host: str, port: int, *, user: str, db: str,
                         asserts: "list") -> "tuple[int, list]":
    """Evaluate each assertion against REAL Postgres state via a FRESH ``_pg_connect``/``_pg_query``
    call per assertion (never the CLI's stdout). Each assertion is either a ``callable(query_fn) ->
    bool`` (``query_fn(sql)`` runs one query on a fresh connection) or a ``(sql, expected_rows)``
    pair. Returns ``(n_passed, failures)``. Never raises."""
    passed = 0
    failures: "list" = []

    def query_fn(sql: str) -> "list[tuple] | None":
        conn = _pg_connect(host, port, user=user, db=db)
        if conn is None:
            return None
        try:
            return _pg_query(conn, sql)
        finally:
            conn.close()

    for idx, spec in enumerate(asserts):
        try:
            if callable(spec):
                ok = bool(spec(query_fn))
            else:
                sql, expected = spec
                ok = (query_fn(sql) == expected)
            if ok:
                passed += 1
            else:
                failures.append(f"assertion[{idx}] did not hold against real Postgres state")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"assertion[{idx}] raised while evaluating: {exc}")
    return passed, failures


def verify_postgres_persistence(root: Any, *, handle: ServiceHandle, drive_cmds: "list",
                                assertions: "list", python_exe: "str | None" = None,
                                cross_invocation_cmd: "tuple | None" = None,
                                entry_name: str = DEFAULT_ENTRY_NAME) -> ServiceResult:
    """The load-bearing Postgres oracle — structurally identical to :func:`verify_redis_persistence`
    (clean-state → drive → independently verify → cross-invocation) against the provisioned Postgres
    in ``handle`` instead of Redis:

    1. **Clean state** — ``DROP SCHEMA public CASCADE; CREATE SCHEMA public;`` via this module's own
       ``_pg_connect``/``_pg_query``.
    2. **Drive** — run each ``(argv, stdin)`` in ``drive_cmds`` as its own sandboxed CLI process,
       with the standard libpq env vars (``PGHOST``/``PGPORT``/``PGDATABASE``/``PGUSER`` — no
       ``PGPASSWORD`` needed, trust auth) injected so the CLI can reach the service.
    3. **Independently verify** — evaluate ``assertions`` against REAL Postgres state (this module's
       own client), never the CLI's stdout.
    4. **Cross-invocation** — one more fresh CLI process, then re-evaluate the same assertions.

    ``ok=True`` only when the handle was up, both CLI invocations exited cleanly, and every assertion
    held on BOTH checks. NEVER RAISES."""
    try:
        if handle is None or not getattr(handle, "ok", False):
            return ServiceResult(ok=False, note="no live service handle (provisioning failed/absent)")
        host, port, user, db = handle.host, handle.port, handle.user, handle.db
        if not user or not db:
            return ServiceResult(ok=False, note="handle is missing db/user (not a postgres handle?)")

        try:
            root_path = Path(root)
        except (TypeError, ValueError) as exc:
            return ServiceResult(ok=False, note=f"invalid root: {root!r}: {exc}")
        if not root_path.exists() or not root_path.is_dir():
            return ServiceResult(ok=False, note=f"root does not exist: {root_path}")

        entry_path = root_path / entry_name
        if not entry_path.is_file():
            return ServiceResult(ok=False, note=f"entrypoint not found: {entry_path}")

        py_exe = python_exe or sys.executable or "python"
        env = {"PGHOST": str(host), "PGPORT": str(port), "PGDATABASE": str(db), "PGUSER": str(user)}

        cmds = list(drive_cmds) if isinstance(drive_cmds, (list, tuple)) else None
        if not cmds:
            return ServiceResult(ok=False, note="no drive_cmds supplied (must be a non-empty list)")
        asserts = list(assertions) if isinstance(assertions, (list, tuple)) else None
        if not asserts:
            return ServiceResult(ok=False, note="no assertions supplied (must be a non-empty list)")

        # Step 1 — clean state.
        conn = _pg_connect(host, port, user=user, db=db)
        if conn is None:
            return ServiceResult(ok=False, note="could not connect to postgres to clean state")
        try:
            reset = _pg_query(conn, "DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        finally:
            conn.close()
        if reset is None:
            return ServiceResult(ok=False, note="could not reset the schema to clean state")

        # Step 2 — drive each command as its own fresh sandboxed subprocess.
        for i, raw_cmd in enumerate(cmds):
            try:
                argv, stdin = _unpack_cmd_pg(raw_cmd)
            except Exception as exc:  # noqa: BLE001
                return ServiceResult(ok=False, note=f"malformed drive_cmds[{i}]: {exc}")
            ok, out = _run_cli_env(py_exe, entry_path, argv, stdin, root_path, env)
            if not ok:
                return ServiceResult(
                    ok=False, note=f"drive_cmds[{i}] CLI invocation failed (non-zero exit): {out[:500]!r}")

        # Step 3 — independent check #1.
        passed1, failures1 = _check_pg_assertions(host, port, user=user, db=db, asserts=asserts)
        if failures1:
            return ServiceResult(
                ok=False, rows_checked=passed1, failures=failures1,
                note="assertions failed against real Postgres right after the drive commands — the "
                     "CLI's stdout may claim success but nothing actually reached Postgres "
                     "(hollow-persistence catch)")

        # Step 4 — cross-invocation: one more, entirely fresh CLI process.
        cross_cmd = cross_invocation_cmd if cross_invocation_cmd is not None else cmds[-1]
        try:
            cross_argv, cross_stdin = _unpack_cmd_pg(cross_cmd)
        except Exception as exc:  # noqa: BLE001
            return ServiceResult(ok=False, rows_checked=passed1,
                                 note=f"malformed cross_invocation_cmd: {exc}")
        ok, out = _run_cli_env(py_exe, entry_path, cross_argv, cross_stdin, root_path, env)
        if not ok:
            return ServiceResult(ok=False, rows_checked=passed1,
                                 note=f"cross-invocation CLI call failed (non-zero exit): {out[:500]!r}")

        passed2, failures2 = _check_pg_assertions(host, port, user=user, db=db, asserts=asserts)
        if failures2:
            return ServiceResult(
                ok=False, rows_checked=passed2, failures=failures2,
                note="assertions failed after a SECOND fresh CLI invocation — the state did not "
                     "survive as real external Postgres data (in-process-only storage)")

        return ServiceResult(ok=True, rows_checked=passed2, failures=[],
                             note="ok: real persisted Postgres state verified independently, both "
                                  "immediately and across a second fresh CLI invocation")
    except Exception as exc:  # noqa: BLE001  — never raise
        return ServiceResult(ok=False, note=f"verify_postgres_persistence failed unexpectedly: {exc}")
# #EXT-039-REQ-2 End
