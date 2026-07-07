"""EXT-039 REQ-2: a real-service (Redis) provisioner + independent persistence oracle.

**The gap this closes (Tenet 3, the next rung above ``harness/datastore_oracle.py`` REQ-1):** REQ-1
proved the acceptance-oracle PATTERN for the one datastore stdlib already ships (``sqlite3``, a
file, no running service). This module takes the SAME pattern to a REAL running service — Redis —
by (a) bringing a real Redis up on localhost via Docker, (b) driving the built system's CLI against
it, and (c) INDEPENDENTLY verifying the data really landed in Redis via this module's OWN client —
never trusting the CLI's stdout — and re-checking across a second, entirely fresh CLI invocation. It
plugs into the SAME ``verify_persistence``-shaped contract REQ-1 established (clean-state → drive →
independently verify → cross-invocation → never-raise honest ``ok=False``+note).

**Pure stdlib, no new dependency (mirrors ``datastore_oracle``'s discipline):** the independent
Redis client is a tiny RESP-over-raw-``socket`` speaker (``_resp_command``) — NOT ``redis-py``. The
only external requirement is the ``docker`` CLI, and every code path degrades honestly when it is
absent (``docker_available()`` gates everything; a provision call with no Docker returns an honest
failed :class:`ServiceHandle`, never raises).

**Offline-honest (Tenet 3):** this needs a running service, which the repo's offline/no-network test
discipline cannot exercise when Docker is absent — so ``tests/test_ext039_service_provisioner.py``
skips ENTIRELY when ``docker_available()`` is False. It never fails offline and never falsely passes.

**Honest platform/egress note (mirrors ``harness/secure_exec.py``):** the CLI-under-test is driven
through ``harness.secure_exec.run_sandboxed`` (scrubbed environment + resource caps + timeout +
process-tree kill), the same house sandbox ``system_suite._run_cli`` uses — called here one layer
down so the service's ``REDIS_HOST``/``REDIS_PORT`` can be injected via ``extra_env`` into the
otherwise-scrubbed environment. ``run_sandboxed`` does NOT enforce network egress at runtime today
(documented: only the static ``scan_code`` gate does), which is WHY a Redis-backed CLI can reach the
provisioned loopback service here. On a future Linux/netns deployment with real runtime egress
enforcement, the provisioned ``host:port`` must be added to that run's egress allow-list — recorded
here honestly, not silently assumed.

**Named-but-NOT-built-here:** Postgres/Qdrant/Cassandra provisioners (each a different wire protocol)
and a live DATASTORE creation-suite task that runs inside the suite loop against a provisioned
service remain follow-ups under REQ-2 — this task lands the Redis rung + its offline-skipped tests.
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


@dataclass
class ServiceHandle:
    """A provisioned (or failed-to-provision) service. ``ok`` is True only when the service is up
    and answered a readiness probe; ``container_id`` is the Docker id to tear down (may be set even
    when ``ok`` is False, so a partially-started container is never leaked). ``host``/``port`` are
    where the CLI-under-test should connect (exposed to it via ``REDIS_HOST``/``REDIS_PORT``)."""

    kind: str
    host: str = "127.0.0.1"
    port: int = 0
    container_id: "str | None" = None
    ok: bool = False
    note: str = ""


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
def _read_mapped_port(container_id: str) -> "int | None":
    """Parse ``docker port <id> 6379/tcp`` (e.g. ``0.0.0.0:49153``) → the host port int, or None."""
    rc, out, _err = _docker("port", container_id, f"{_REDIS_CONTAINER_PORT}/tcp", timeout=12.0)
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


def _fail_and_teardown(container_id: str, note: str) -> ServiceHandle:
    teardown(ServiceHandle(kind="redis", container_id=container_id, ok=False))
    return ServiceHandle(kind="redis", ok=False, note=note)


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
# #EXT-039-REQ-2 End
