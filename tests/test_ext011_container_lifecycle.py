"""EXT-011-REQ-7 isolation tests: per-selftest container naming + guaranteed cleanup.

These tests do NOT run the full 37-task eval; they verify ONLY the container-lifecycle
helper in isolation using the real Docker daemon.

Test strategy
-------------
1. Spin up a deliberately-hanging container (`sleep 600`) via the same `mi-test` image.
2. Invoke `_docker_force_remove` and assert the container is GONE within the timeout
   (neither running nor stopped — completely removed from `docker ps -a`).
3. Verify `_run_selftests` with a timeout shorter than a `sleep 600` entrypoint:
   - returns (False, "timeout")
   - leaves no orphaned container behind
"""
from __future__ import annotations

import subprocess
import time
import uuid

import pytest

from harness.commit_replay import _docker_force_remove

# Docker image known to exist in this repo (used by the eval itself)
MI_TEST_IMAGE = "mi-test"


def _container_exists(name: str) -> bool:
    """True if the container appears in `docker ps -a` (any state)."""
    r = subprocess.run(
        ["docker", "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=10,
    )
    return name in r.stdout.splitlines()


# ---------------------------------------------------------------------------
# Test 1: _docker_force_remove kills and removes a running container
# ---------------------------------------------------------------------------
def test_force_remove_kills_running_container():
    """Start a container that sleeps forever, force-remove it, assert it is gone."""
    name = f"jtest_hang_{uuid.uuid4().hex[:8]}"
    # Start the container detached so it doesn't block the test process
    subprocess.run(
        ["docker", "run", "--name", name, "-d", MI_TEST_IMAGE, "sh", "-c", "sleep 600"],
        capture_output=True, timeout=15,
    )
    # Confirm it is actually running before we attempt the fix
    assert _container_exists(name), "pre-condition: container should be running"

    _docker_force_remove(name)

    # Give Docker a moment to process the removal
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not _container_exists(name):
            break
        time.sleep(0.3)

    assert not _container_exists(name), \
        f"Container '{name}' was NOT removed — orphan still present after _docker_force_remove"


# ---------------------------------------------------------------------------
# Test 2: _docker_force_remove is a no-op on a nonexistent container (no raise)
# ---------------------------------------------------------------------------
def test_force_remove_nonexistent_container_does_not_raise():
    """Calling _docker_force_remove on a name that doesn't exist must not raise."""
    _docker_force_remove(f"jtest_never_existed_{uuid.uuid4().hex[:8]}")
    # If we reach here without exception, the test passes


# ---------------------------------------------------------------------------
# Test 3: _run_selftests timeout path returns (False, "timeout") and leaves no orphan
# ---------------------------------------------------------------------------
def test_run_selftests_timeout_leaves_no_orphan(tmp_path):
    """Inject a test file whose fixture hangs for 600s; _run_selftests must:
    - return (False, "timeout")
    - leave NO container behind in `docker ps -a`
    """
    import re
    from pathlib import Path
    from harness.commit_replay import _run_selftests, _docker_force_remove

    # Build a minimal fake repo structure so _spec() finds "tests/" and the image "mi-test".
    # We override the spec inline by monkey-patching REGISTRY rather than creating a real repo.
    import harness.commit_replay as cr
    orig_registry = cr.REGISTRY.copy()
    repo_name = f"test_repo_{uuid.uuid4().hex[:6]}"
    fake_repo = tmp_path / repo_name
    tests_dir = fake_repo / "tests"
    tests_dir.mkdir(parents=True)
    cr.REGISTRY[repo_name] = {"code": "", "test": "tests/", "img": MI_TEST_IMAGE}

    # The test code itself sleeps 600s inside a fixture — this will hang docker pytest
    hanging_test_code = (
        "import time\n"
        "def test_hang():\n"
        "    time.sleep(600)\n"
    )

    # Run with a very short timeout (3s) so the test completes quickly
    try:
        ok, fb = _run_selftests(fake_repo, hanging_test_code, timeout=3)
    finally:
        cr.REGISTRY = orig_registry

    assert ok is False, f"Expected False (timeout), got {ok!r}"
    assert "timeout" in fb.lower(), f"Expected 'timeout' in feedback, got {fb!r}"

    # Verify no orphaned containers remain that look like our jaros_selftest_ prefix
    r = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=jaros_selftest_",
         "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=10,
    )
    orphans = [n for n in r.stdout.splitlines() if n.startswith("jaros_selftest_")]
    assert not orphans, f"Orphaned containers found after timeout: {orphans}"
