"""EXT-060 TASK-26/TASK-27/TASK-28/TASK-29: offline tests for FOUR NEW real-systems CREATE tasks
from the atlas's top impact x buildability lists (REQ-31/32/33/34):

- ``GFS_RETENTION_TASK`` (``oracle_kind="import"``, ``cls="backup"``): a Grandfather-Father-Son
  backup retention pruning library, graded by the ALREADY-LANDED ``harness.import_driver.
  drive_import`` dispatch (REQ-3's ``_grade_import``, no new oracle code).
- ``CI_MATRIX_TASK`` (``oracle_kind="import"``, ``cls="devtools"``): a CI job-matrix expansion
  library, graded by the SAME ALREADY-LANDED ``import`` dispatch (no new oracle code).
- ``URL_SHORTENER_TASK`` (``oracle_kind="service"``, ``cls="web"``): a stdlib REST/SQLite URL-
  shortener, graded by the ALREADY-LANDED ``harness.server_oracle.serve_and_check_stdlib`` +
  independent post-teardown SQLite row assertion dispatch (REQ-9's ``_grade_service``, no new
  oracle code).
- ``TOKEN_VALIDITY_TASK`` (``oracle_kind="clock"``, ``cls="auth"``): an access-token validity-
  window issuer, the SECOND task graded by the injectable-clock oracle (REQ-28's ``_grade_clock``
  -> ``harness.clock_oracle.grade_clock``, no new oracle code).

FULLY OFFLINE -- no real model/Jetson call anywhere. Every module/program here is a small,
hand-written stdlib Python fixture written to a temp directory and driven against the existing
deterministic oracle machinery (exactly what ``grade_real_system_task`` itself wires) -- never a
live orchestrator/gemma run.

Run in isolation: ``python -m pytest tests/test_ext060_atlas_wave2_tasks.py -q``.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path

from harness.clock_oracle import validate_spec
from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    CI_MATRIX_TASK,
    GFS_RETENTION_TASK,
    REAL_SYSTEMS_TASKS,
    TOKEN_VALIDITY_TASK,
    URL_SHORTENER_TASK,
    grade_real_system_task,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(textwrap.dedent(source), encoding="utf-8")


# ================================================================================================
# #EXT-060-REQ-31 Start
# GFS_RETENTION_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_GFS_RETENTION = """
    from datetime import date


    def compute_keep_dates(snapshots, keep_daily, keep_weekly, keep_monthly):
        parsed = sorted(date.fromisoformat(s) for s in snapshots)
        keep = set()

        if keep_daily > 0:
            for d in parsed[-keep_daily:]:
                keep.add(d)

        week_buckets = {}
        for d in parsed:
            key = d.isocalendar()[:2]
            week_buckets.setdefault(key, []).append(d)
        for wk in sorted(week_buckets.keys(), reverse=True)[:keep_weekly]:
            keep.add(max(week_buckets[wk]))

        month_buckets = {}
        for d in parsed:
            key = (d.year, d.month)
            month_buckets.setdefault(key, []).append(d)
        for mo in sorted(month_buckets.keys(), reverse=True)[:keep_monthly]:
            keep.add(max(month_buckets[mo]))

        return sorted(x.isoformat() for x in keep)
"""


def test_correct_gfs_retention_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_gfstest_") as tmp:
        root = Path(tmp)
        _write(root, "gfs_retention.py", CORRECT_GFS_RETENTION)
        accepted, note = grade_real_system_task(GFS_RETENTION_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: ignores the daily/weekly/monthly policy entirely and keeps EVERY snapshot.
# ------------------------------------------------------------------------------------------------

BROKEN_GFS_RETENTION_KEEPS_EVERYTHING = """
    def compute_keep_dates(snapshots, keep_daily, keep_weekly, keep_monthly):
        # BUG: ignores the retention policy entirely -- keeps every snapshot, prunes nothing.
        return sorted(set(snapshots))
"""


def test_broken_gfs_retention_keeps_everything_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_gfstest_") as tmp:
        root = Path(tmp)
        _write(root, "gfs_retention.py", BROKEN_GFS_RETENTION_KEEPS_EVERYTHING)
        accepted, note = grade_real_system_task(GFS_RETENTION_TASK, root, python_exe=PY)
        assert accepted is False


def test_gfs_retention_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(GFS_RETENTION_TASK.sentence) is None
    assert GFS_RETENTION_TASK in REAL_SYSTEMS_TASKS
    assert GFS_RETENTION_TASK.oracle_kind == "import"
    assert GFS_RETENTION_TASK.cls == "backup"
    assert GFS_RETENTION_TASK.name == "backup-retention-gfs-pruning-lib"
    assert GFS_RETENTION_TASK.oracle_spec["module"] == "gfs_retention"
    checks = GFS_RETENTION_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "gfs_main",
            "expected": ["2024-05-31", "2024-06-20", "2024-06-30", "2024-07-05", "2024-07-10"]
            } in checks
    assert {"kind": "returns_equals", "call_id": "gfs_fewer_than_policy",
            "expected": ["2024-01-01", "2024-01-02", "2024-01-03"]} in checks
# #EXT-060-REQ-31 End


# ================================================================================================
# #EXT-060-REQ-32 Start
# CI_MATRIX_TASK ("import" oracle_kind)
# ================================================================================================

CORRECT_CI_MATRIX = """
    import itertools


    def expand_matrix(matrix, exclude=None, include=None):
        exclude = exclude or []
        include = include or []
        axes = sorted(matrix.keys())
        combos = [dict(zip(axes, values))
                  for values in itertools.product(*[matrix[a] for a in axes])]

        def excluded(combo):
            return any(all(combo.get(k) == v for k, v in ex.items()) for ex in exclude)

        result = [c for c in combos if not excluded(c)]
        result.extend(include)
        return result
"""


def test_correct_ci_matrix_passes_the_import_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_cimatrixtest_") as tmp:
        root = Path(tmp)
        _write(root, "ci_matrix.py", CORRECT_CI_MATRIX)
        accepted, note = grade_real_system_task(CI_MATRIX_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: computes the full cross product and appends `include`, but never applies `exclude`.
# ------------------------------------------------------------------------------------------------

BROKEN_CI_MATRIX_IGNORES_EXCLUDE = """
    import itertools


    def expand_matrix(matrix, exclude=None, include=None):
        exclude = exclude or []
        include = include or []
        axes = sorted(matrix.keys())
        combos = [dict(zip(axes, values))
                  for values in itertools.product(*[matrix[a] for a in axes])]
        # BUG: never removes anything matching `exclude`.
        result = list(combos)
        result.extend(include)
        return result
"""


def test_broken_ci_matrix_ignores_exclude_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_cimatrixtest_") as tmp:
        root = Path(tmp)
        _write(root, "ci_matrix.py", BROKEN_CI_MATRIX_IGNORES_EXCLUDE)
        accepted, note = grade_real_system_task(CI_MATRIX_TASK, root, python_exe=PY)
        assert accepted is False


def test_ci_matrix_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(CI_MATRIX_TASK.sentence) is None
    assert CI_MATRIX_TASK in REAL_SYSTEMS_TASKS
    assert CI_MATRIX_TASK.oracle_kind == "import"
    assert CI_MATRIX_TASK.cls == "devtools"
    assert CI_MATRIX_TASK.name == "ci-job-matrix-expansion-lib"
    assert CI_MATRIX_TASK.oracle_spec["module"] == "ci_matrix"
    checks = CI_MATRIX_TASK.oracle_spec["checks"]
    assert {"kind": "returns_equals", "call_id": "full_matrix", "expected": [
        {"os": "linux", "python": "3.9"}, {"os": "linux", "python": "3.10"},
        {"os": "linux", "python": "3.11"}, {"os": "windows", "python": "3.10"},
        {"os": "windows", "python": "3.11"},
        {"os": "macos", "python": "3.11", "extra": "beta"},
    ]} in checks
    assert {"kind": "returns_equals", "call_id": "subset_exclude", "expected": [
        {"os": "linux", "python": "3.9"}, {"os": "linux", "python": "3.10"},
    ]} in checks
# #EXT-060-REQ-32 End


# ================================================================================================
# #EXT-060-REQ-33 Start
# URL_SHORTENER_TASK ("service" oracle_kind)
# ================================================================================================

CORRECT_URL_SHORTENER = """
    import json
    import os
    import sqlite3
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    DB_PATH = "data.db"


    def _get_conn():
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS links "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL)"
        )
        return conn


    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path == "/links":
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length) or b"{}")
                conn = _get_conn()
                cur = conn.execute("INSERT INTO links (url) VALUES (?)", (data["url"],))
                conn.commit()
                new_id = cur.lastrowid
                conn.close()
                self._send_json(201, {"code": str(new_id), "url": data["url"]})
                return
            self.send_response(404)
            self.end_headers()

        def do_GET(self):
            if self.path.startswith("/links/"):
                code = self.path[len("/links/"):]
                conn = _get_conn()
                row = conn.execute("SELECT id, url FROM links WHERE id = ?", (code,)).fetchone()
                conn.close()
                if row is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self._send_json(200, {"code": str(row[0]), "url": row[1]})
                return
            if self.path.startswith("/r/"):
                code = self.path[len("/r/"):]
                conn = _get_conn()
                row = conn.execute("SELECT id, url FROM links WHERE id = ?", (code,)).fetchone()
                conn.close()
                if row is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(301)
                self.send_header("Location", row[1])
                self.end_headers()
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, fmt, *args):
            pass


    if __name__ == "__main__":
        port = int(os.environ["PORT"])
        _get_conn().close()
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        server.serve_forever()
"""


def test_correct_url_shortener_passes_the_service_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_shortenertest_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", CORRECT_URL_SHORTENER)
        accepted, note = grade_real_system_task(URL_SHORTENER_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: `GET /links/<code>` always 404s (the lookup branch is dead), even for a code that was
# just created by a POST moments earlier -- storage/lookup is broken even though POST itself
# looks like it succeeds.
# ------------------------------------------------------------------------------------------------

BROKEN_URL_SHORTENER_LINKS_LOOKUP_DEAD = CORRECT_URL_SHORTENER.replace(
    'if self.path.startswith("/links/"):',
    'if False and self.path.startswith("/links/"):',
    1,
)


def test_broken_url_shortener_links_lookup_dead_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_shortenertest_") as tmp:
        root = Path(tmp)
        _write(root, "main.py", BROKEN_URL_SHORTENER_LINKS_LOOKUP_DEAD)
        accepted, note = grade_real_system_task(URL_SHORTENER_TASK, root, python_exe=PY)
        assert accepted is False


def test_url_shortener_task_is_leaves_off_and_a_roster_member():
    assert leaf_for_spec(URL_SHORTENER_TASK.sentence) is None
    assert URL_SHORTENER_TASK in REAL_SYSTEMS_TASKS
    assert URL_SHORTENER_TASK.oracle_kind == "service"
    assert URL_SHORTENER_TASK.cls == "web"
    assert URL_SHORTENER_TASK.name == "url-shortener-http-service"
    assert URL_SHORTENER_TASK.oracle_spec["db"] == {"path": "data.db", "min_rows": 2}
    paths = {c["path"] for c in URL_SHORTENER_TASK.oracle_spec["http_checks"]}
    assert paths == {"/links", "/links/1", "/links/999", "/r/999"}
    # the redirect endpoint is never exercised for a KNOWN code (see the module-level note in
    # harness/real_systems_suite.py for why -- urlopen transparently follows a real 3xx).
    assert "/r/1" not in paths
# #EXT-060-REQ-33 End


# ================================================================================================
# #EXT-060-REQ-34 Start
# TOKEN_VALIDITY_TASK ("clock" oracle_kind)
# ================================================================================================

CORRECT_TOKEN_ISSUER = """
    class TokenIssuer:
        def __init__(self, now_fn):
            self._now_fn = now_fn
            self._issued_at = {}

        def issue(self, name):
            self._issued_at[name] = self._now_fn()
            return name

        def check(self, token):
            issued_at = self._issued_at.get(token)
            if issued_at is None:
                return False
            return (self._now_fn() - issued_at) < 900
"""


def test_correct_token_issuer_passes_the_clock_task_oracle():
    with tempfile.TemporaryDirectory(prefix="ext060_tokentest_") as tmp:
        root = Path(tmp)
        _write(root, "tokens.py", CORRECT_TOKEN_ISSUER)
        accepted, note = grade_real_system_task(TOKEN_VALIDITY_TASK, root, python_exe=PY)
        assert accepted is True, note


# ------------------------------------------------------------------------------------------------
# BROKEN: never checks the validity window at all -- once issued, a token stays valid forever.
# ------------------------------------------------------------------------------------------------

BROKEN_TOKEN_ISSUER_NEVER_INVALIDATES = """
    class TokenIssuer:
        def __init__(self, now_fn):
            self._now_fn = now_fn
            self._issued = set()

        def issue(self, name):
            self._issued.add(name)
            return name

        def check(self, token):
            # BUG: never consults the 900-second window -- a token is valid forever once issued.
            return token in self._issued
"""


def test_broken_token_issuer_never_invalidates_is_rejected():
    with tempfile.TemporaryDirectory(prefix="ext060_tokentest_") as tmp:
        root = Path(tmp)
        _write(root, "tokens.py", BROKEN_TOKEN_ISSUER_NEVER_INVALIDATES)
        accepted, note = grade_real_system_task(TOKEN_VALIDITY_TASK, root, python_exe=PY)
        assert accepted is False


def test_token_validity_clock_spec_validates_and_task_is_leaves_off_and_a_roster_member():
    ok, note = validate_spec(TOKEN_VALIDITY_TASK.oracle_spec["spec"])
    assert (ok, note) == (True, "ok")
    assert leaf_for_spec(TOKEN_VALIDITY_TASK.sentence) is None
    assert TOKEN_VALIDITY_TASK in REAL_SYSTEMS_TASKS
    assert TOKEN_VALIDITY_TASK.oracle_kind == "clock"
    assert TOKEN_VALIDITY_TASK.cls == "auth"
    assert TOKEN_VALIDITY_TASK.name == "access-token-validity-window-lib"
    # the sentence pins the now_fn contract explicitly.
    assert "now_fn" in TOKEN_VALIDITY_TASK.sentence
    assert "zero-argument callable" in TOKEN_VALIDITY_TASK.sentence
    # says "valid for 900 seconds"/"elapsed", never "expires" -- avoids every leaf-fingerprinting
    # token (the ttl-store leaf in particular fingerprints on "expire"/"expiry"/"ttl"; note this
    # checks the actual multi-word PHRASES `harness.adt_oracle._KEYWORDS` fingerprints on, e.g.
    # "ring buffer", not the bare substring "ring" -- which would false-positive on ordinary
    # words like "string").
    lowered = TOKEN_VALIDITY_TASK.sentence.lower()
    for banned in ("expire", "expiry", "expiration", "cache", "ttl", "queue", "stack",
                   "ring buffer", "ring-buffer", "circular buffer", "circular-buffer",
                   "memoize"):
        assert banned not in lowered, banned
# #EXT-060-REQ-34 End


# ------------------------------------------------------------------------------------------------
# roster growth: the scoreboard's CREATE half grew by exactly these four new tasks (REQ-31..34).
# ------------------------------------------------------------------------------------------------

def test_real_systems_tasks_roster_grew_by_the_four_new_tasks():
    # bumped 22 -> 26 -> 30: this module's own REQ-31/32/33/34 add four more CREATE tasks, then
    # EXT-060 REQ-40..43 (tests/test_ext060_atlas_wave7_tasks.py) added four more.
    assert len(REAL_SYSTEMS_TASKS) == 30
    names = {t.name for t in REAL_SYSTEMS_TASKS}
    assert "backup-retention-gfs-pruning-lib" in names
    assert "ci-job-matrix-expansion-lib" in names
    assert "url-shortener-http-service" in names
    assert "access-token-validity-window-lib" in names


def test_no_new_task_has_a_leaf_fingerprint():
    for task in (GFS_RETENTION_TASK, CI_MATRIX_TASK, URL_SHORTENER_TASK, TOKEN_VALIDITY_TASK):
        assert leaf_for_spec(task.sentence) is None, task.name
