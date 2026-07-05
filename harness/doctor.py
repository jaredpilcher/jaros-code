"""EXT-053: `/doctor` -- deterministic health-check instrument, closing
`docs/GAP-MAP.md` Product-surface parity row #25 (Install + health story).

Mirrors Claude Code's `/doctor`: a battery of DETERMINISTIC checks (no model call anywhere) that
each report `"pass"`/`"warn"`/`"fail"` plus a short detail and remedy hint, rolled up into one
honest overall verdict. Two-plane discipline (Tenet 1): every check here is pure execution-plane
bookkeeping -- an env var lookup, a filesystem stat/permission query, a BOUNDED subprocess probe
for `git`/`docker`, and a BOUNDED probe of the configured LLM endpoint (reusing
`harness.llamacpp_client.health`, already a bounded `urllib` GET). Nothing here ever blocks or
raises out to the caller: every external call carries a short, explicit timeout and is wrapped so
a hung/absent/erroring dependency degrades to an honest `"warn"` (or, for a genuine local
capability gap like a missing required binary, `"fail"`) rather than hanging `/doctor` itself.

Read-only. No check in this module performs a host WRITE -- `.jaros-data/` writability is
assessed via a permission query (`os.access(..., os.W_OK)`), never by actually writing a probe
file (per design.md's placement note: `/doctor` only reports, it never mutates the workspace).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# #EXT-053-REQ-1 Start
VALID_STATUSES = ("pass", "warn", "fail")

_SUBPROCESS_TIMEOUT_S = 5.0
_ENDPOINT_TIMEOUT_S = 2.0
_DEFAULT_PY_MINIMUM = (3, 10)
_VALID_BACKEND_PREFIXES = ("llama", "ollama")


@dataclass(frozen=True)
class DoctorCheck:
    """One deterministic `/doctor` check result."""

    name: str
    status: str            # "pass" | "warn" | "fail"
    detail: str
    remedy: str = ""


def _check(name: str, status: str, detail: str, remedy: str = "") -> DoctorCheck:
    if status not in VALID_STATUSES:
        status = "warn"
    return DoctorCheck(name=name, status=status, detail=detail, remedy=remedy)


def _check_python_version(minimum: "tuple[int, int]" = _DEFAULT_PY_MINIMUM) -> DoctorCheck:
    current = sys.version_info[:2]
    label = sys.version.split()[0]
    if current >= minimum:
        return _check("python_version", "pass",
                       f"Python {label} (>= {minimum[0]}.{minimum[1]} required)")
    return _check("python_version", "fail",
                   f"Python {label} is below the required {minimum[0]}.{minimum[1]}",
                   f"upgrade to Python >= {minimum[0]}.{minimum[1]}")


def _check_git(root: str = ".") -> DoctorCheck:
    git_bin = shutil.which("git")
    if not git_bin:
        return _check("git", "fail", "git binary not found on PATH",
                       "install git (https://git-scm.com/downloads)")
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root, capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_S,
        )
    except Exception as exc:
        return _check("git", "warn", f"git present but the probe failed: {exc}", "")
    if proc.returncode == 0 and proc.stdout.strip() == "true":
        return _check("git", "pass", f"git found ({git_bin}); this directory is a git work tree")
    return _check("git", "warn",
                   "git found, but this directory is not inside a git work tree", "")


def _check_docker() -> DoctorCheck:
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return _check("docker", "warn", "docker binary not found on PATH",
                       "install Docker -- only needed for some eval/build paths, not the core CLI")
    try:
        proc = subprocess.run(["docker", "--version"], capture_output=True, text=True,
                               timeout=_SUBPROCESS_TIMEOUT_S)
    except Exception as exc:
        return _check("docker", "warn", f"docker present but the probe failed: {exc}", "")
    if proc.returncode == 0:
        return _check("docker", "pass", (proc.stdout or "").strip() or "docker present")
    return _check("docker", "warn", "docker present but `docker --version` failed", "")


def _check_data_dir_writable(root: str = ".") -> DoctorCheck:
    """Read-only writability check: a PERMISSION QUERY (`os.access(..., os.W_OK)`), never an
    actual write -- `/doctor` reports, it does not mutate the workspace."""
    data_dir = Path(root) / ".jaros-data"
    try:
        if not data_dir.exists():
            return _check("jaros_data_writable", "warn", f"{data_dir} does not exist yet",
                           "created automatically by the harness on first use")
        if os.access(str(data_dir), os.W_OK):
            return _check("jaros_data_writable", "pass", f"{data_dir} is writable")
        return _check("jaros_data_writable", "fail", f"{data_dir} is not writable",
                       "check filesystem permissions for .jaros-data/")
    except Exception as exc:
        return _check("jaros_data_writable", "warn", f"writability probe failed: {exc}", "")


def _check_dirs_present(root: str = ".") -> DoctorCheck:
    try:
        base = Path(root) / ".jaros-data"
        missing = [name for name in ("tools", "agents") if not (base / name).is_dir()]
        if missing:
            return _check("jaros_data_dirs", "warn",
                           f"missing expected dir(s): {', '.join(missing)}",
                           "created automatically by the harness on first use")
        return _check("jaros_data_dirs", "pass", f"{base}/tools and {base}/agents present")
    except Exception as exc:
        return _check("jaros_data_dirs", "warn", f"dir-presence probe failed: {exc}", "")


def _check_config(root: str = ".") -> DoctorCheck:
    backend = os.environ.get("JCODE_LLM_BACKEND", "llamacpp").strip().lower()
    if backend.startswith(_VALID_BACKEND_PREFIXES):
        label = "llamacpp (default)" if backend.startswith("llama") else "ollama (legacy)"
        return _check("config_backend", "pass", f"JCODE_LLM_BACKEND resolves to {label}")
    return _check("config_backend", "warn",
                   f"JCODE_LLM_BACKEND={backend!r} is not a recognized value "
                   "(expected 'llamacpp' or 'ollama')",
                   "unset JCODE_LLM_BACKEND for the default (llamacpp), or set it to "
                   "'ollama' for the legacy local path")


def _check_llm_endpoint(timeout: float = _ENDPOINT_TIMEOUT_S) -> "tuple[DoctorCheck, DoctorCheck]":
    """Bounded probe of the configured LLM endpoint (never hangs -- `timeout` bounds the whole
    round trip via the already-bounded `harness.llamacpp_client.health`); any exception -- or an
    honest unreachable result -- degrades to a WARN on both derived checks, never a raise and
    never a FAIL, so `/doctor` stays useful fully offline."""
    host = os.environ.get("LLAMACPP_HOST", "http://192.168.1.183:8000")
    try:
        from harness.llamacpp_client import health as _health
        result = _health(host, timeout=timeout)
    except Exception as exc:
        endpoint = _check("llm_endpoint", "warn", f"probe of {host} raised: {exc}",
                           "start the Jetson llama.cpp server (scripts/serve.sh / serve.ps1)")
        served = _check("llm_model_served", "warn", "endpoint unreachable -- skipped",
                         "a reachable endpoint is required before model-served can be checked")
        return endpoint, served

    if not isinstance(result, dict) or not result.get("ok"):
        err = result.get("error", "unreachable") if isinstance(result, dict) else "unreachable"
        endpoint = _check("llm_endpoint", "warn", f"{host} unreachable: {err}",
                           "start the Jetson llama.cpp server (scripts/serve.sh / serve.ps1), or "
                           "set LLAMACPP_HOST to a reachable endpoint")
        served = _check("llm_model_served", "warn", "endpoint unreachable -- skipped",
                         "a reachable endpoint is required before model-served can be checked")
        return endpoint, served

    endpoint = _check("llm_endpoint", "pass", f"{host} reachable")
    models = result.get("models") or []
    if models:
        served = _check("llm_model_served", "pass",
                         f"model(s) served: {', '.join(str(m) for m in models)}")
    else:
        served = _check("llm_model_served", "warn",
                         f"{host} reachable but reports no served models",
                         "confirm the llama-server was started with a --model gguf")
    return endpoint, served
# #EXT-053-REQ-1 End


# #EXT-053-REQ-1 Start
def run_doctor(root: str = ".") -> dict:
    """Run every deterministic `/doctor` check and return a structured report:
    ``{"checks": [DoctorCheck, ...], "overall": "pass"|"warn"|"fail"}``.

    Never raises: each check function is itself defensive, and this orchestrator ALSO wraps
    every call in its own `try/except` so one broken/unexpected check can never blank out or
    crash the rest of the report (mirrors `harness.product_parity.score`'s degrade-not-raise
    discipline -- observability must never break the thing it observes)."""
    checks: "list[DoctorCheck]" = []

    def _run(label: str, fn, *args):
        try:
            result = fn(*args)
        except Exception as exc:
            checks.append(_check(label, "warn", f"check raised: {exc}"))
            return
        if isinstance(result, tuple):
            checks.extend(result)
        else:
            checks.append(result)

    _run("python_version", _check_python_version)
    _run("git", _check_git, root)
    _run("docker", _check_docker)
    _run("jaros_data_writable", _check_data_dir_writable, root)
    _run("jaros_data_dirs", _check_dirs_present, root)
    _run("config_backend", _check_config, root)
    _run("llm_endpoint", _check_llm_endpoint)

    overall = "pass"
    for c in checks:
        if getattr(c, "status", None) == "fail":
            overall = "fail"
            break
        if getattr(c, "status", None) == "warn" and overall != "fail":
            overall = "warn"
    return {"checks": checks, "overall": overall}


_STATUS_GLYPH = {"pass": "OK", "warn": "WARN", "fail": "FAIL"}


def render(report: "dict | None" = None) -> str:
    """Human-readable table for `/doctor` (REPL) and `jcode doctor`/`--doctor` (headless). Never
    raises -- falls back to an honest one-line message on any failure."""
    try:
        report = report if report is not None else run_doctor()
        checks = report.get("checks", []) if isinstance(report, dict) else []
        lines = ["jcode doctor -- deterministic health check", ""]
        for c in checks:
            status = getattr(c, "status", "warn")
            name = getattr(c, "name", "check")
            detail = getattr(c, "detail", "")
            remedy = getattr(c, "remedy", "")
            glyph = _STATUS_GLYPH.get(status, str(status).upper())
            lines.append(f"[{glyph:4}] {name}: {detail}")
            if status != "pass" and remedy:
                lines.append(f"         -> {remedy}")
        overall = report.get("overall", "warn") if isinstance(report, dict) else "warn"
        lines.append("")
        lines.append(f"overall: {_STATUS_GLYPH.get(overall, str(overall).upper())}")
        return "\n".join(lines)
    except Exception as exc:
        return f"jcode doctor: (report unavailable -- {exc})"
# #EXT-053-REQ-1 End
