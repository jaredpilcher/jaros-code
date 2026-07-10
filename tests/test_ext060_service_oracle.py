"""EXT-060 TASK-8: offline tests for the "service" oracle_kind (REQ-9) and the first REST/SQLite
CRUD CREATE (REQ-9) + MODIFY (REQ-10) tasks on the canonical real-systems scoreboard.

FULLY OFFLINE -- no Jetson/LLM call anywhere. Every fixture here is a HAND-WRITTEN stdlib
``http.server`` + ``sqlite3`` service (never a reference implementation the model could have seen)
launched as a REAL subprocess on an ephemeral localhost port, driven with REAL HTTP requests via
``harness.server_oracle.serve_and_check_stdlib`` (reused, not reimplemented), then independently
re-opened as a REAL sqlite3 connection AFTER the server is torn down -- exactly the honesty
discipline ``grade_real_system_task``'s ``"service"`` dispatch (:mod:`harness.real_systems_suite`)
performs against any candidate build.
"""

# #EXT-060-REQ-9 Start
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

from harness.graph_dsl import leaf_for_spec
from harness.real_systems_suite import (
    REAL_SYSTEMS_MODIFY_TASKS,
    REAL_SYSTEMS_TASKS,
    REST_SQLITE_ADD_UPDATE_MODIFY,
    REST_SQLITE_CRUD_TASK,
    _REST_SQLITE_BASELINE_PY,
    grade_real_system_task,
)

PY = sys.executable or "python"


def _write(root: Path, name: str, source: str) -> None:
    (root / name).write_text(source, encoding="utf-8")


# --- fixtures ----------------------------------------------------------------------------------

CORRECT_MAIN = _REST_SQLITE_BASELINE_PY

# The new PUT handler REST_SQLITE_ADD_UPDATE_MODIFY's mod_sentence asks for, spliced into the
# baseline right before `log_message` -- a correct post-modification module.
_PUT_METHOD = '''
    def do_PUT(self):
        item_id = _item_id(self.path)
        if item_id is None:
            self._send_json(404, {"error": "not found"})
            return
        data = self._read_json()
        name = data.get("name")
        cur = CONN.execute("UPDATE items SET name = ? WHERE id = ?", (name, item_id))
        CONN.commit()
        if cur.rowcount == 0:
            self._send_json(404, {"error": "not found"})
        else:
            self._send_json(200, {"id": item_id, "name": name})

'''

CORRECT_MAIN_WITH_PUT = _REST_SQLITE_BASELINE_PY.replace(
    "    def log_message", _PUT_METHOD + "    def log_message"
)
assert "do_PUT" in CORRECT_MAIN_WITH_PUT  # guard against a silent splice-point typo above

# WRONG (a): keeps state ONLY in an in-process list -- every HTTP response looks correct, but
# nothing is ever written to data.db. The db assertion must catch this even though every
# http_check itself would pass.
WRONG_NO_PERSISTENCE = '''import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

ITEMS = []


def _item_id(path):
    parts = urlparse(path).path.strip("/").split("/")
    if len(parts) == 2 and parts[0] == "items":
        try:
            return int(parts[1])
        except ValueError:
            return None
    return None


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/items":
            self._send_json(200, ITEMS)
            return
        item_id = _item_id(self.path)
        for it in ITEMS:
            if it["id"] == item_id:
                self._send_json(200, it)
                return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        data = self._read_json()
        item = {"id": len(ITEMS) + 1, "name": data.get("name")}
        ITEMS.append(item)
        self._send_json(201, item)

    def do_DELETE(self):
        item_id = _item_id(self.path)
        for it in list(ITEMS):
            if it["id"] == item_id:
                ITEMS.remove(it)
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        self._send_json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ["PORT"])
    server = HTTPServer(("127.0.0.1", port), Handler)
    server.serve_forever()
'''

# WRONG (b): POST responds 200 instead of the required 201.
WRONG_STATUS_CODE = _REST_SQLITE_BASELINE_PY.replace(
    'self._send_json(201, {"id": cur.lastrowid, "name": name})',
    'self._send_json(200, {"id": cur.lastrowid, "name": name})',
)
assert WRONG_STATUS_CODE != _REST_SQLITE_BASELINE_PY

# WRONG (c): no DELETE handler at all -- BaseHTTPRequestHandler 501s any unhandled verb.
WRONG_MISSING_DELETE = _REST_SQLITE_BASELINE_PY.replace(
    '''    def do_DELETE(self):
        item_id = _item_id(self.path)
        if item_id is None:
            self._send_json(404, {"error": "not found"})
            return
        cur = CONN.execute("DELETE FROM items WHERE id = ?", (item_id,))
        CONN.commit()
        if cur.rowcount == 0:
            self._send_json(404, {"error": "not found"})
        else:
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()

''',
    "",
)
assert "do_DELETE" not in WRONG_MISSING_DELETE

# A fixture that crashes before it ever binds the port.
CRASHING_MAIN = "import sys\nsys.exit('boom before bind')\n"


# --- (a) CORRECT baseline accepted, including the independent db assertion ---------------------

class TestServiceOracleGradesTheCrudTaskCorrectly:
    def test_correct_fixture_is_accepted_with_db_assertion(self):
        with tempfile.TemporaryDirectory(prefix="ext060_svc_") as tmp:
            root = Path(tmp)
            _write(root, "main.py", CORRECT_MAIN)
            accepted, note = grade_real_system_task(REST_SQLITE_CRUD_TASK, root, python_exe=PY)
            assert accepted is True, note
            assert "db assertion ok" in note

            # Re-verify the persistence claim independently, from the TEST's own fresh connection
            # too -- not just trusting the oracle's own note string.
            conn = sqlite3.connect(str(root / "data.db"))
            try:
                rows = conn.execute("SELECT name FROM items").fetchall()
            finally:
                conn.close()
            assert ("beta",) in rows  # "alpha" (id 1) was deleted by the check sequence itself

    def test_never_persists_fixture_is_rejected_despite_correct_http_responses(self):
        with tempfile.TemporaryDirectory(prefix="ext060_svc_") as tmp:
            root = Path(tmp)
            _write(root, "main.py", WRONG_NO_PERSISTENCE)
            accepted, note = grade_real_system_task(REST_SQLITE_CRUD_TASK, root, python_exe=PY)
            assert accepted is False
            assert "db assertion" in note or "database file does not exist" in note

    def test_wrong_post_status_code_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="ext060_svc_") as tmp:
            root = Path(tmp)
            _write(root, "main.py", WRONG_STATUS_CODE)
            accepted, note = grade_real_system_task(REST_SQLITE_CRUD_TASK, root, python_exe=PY)
            assert accepted is False

    def test_missing_delete_endpoint_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="ext060_svc_") as tmp:
            root = Path(tmp)
            _write(root, "main.py", WRONG_MISSING_DELETE)
            accepted, note = grade_real_system_task(REST_SQLITE_CRUD_TASK, root, python_exe=PY)
            assert accepted is False

    def test_crashing_fixture_never_raises_and_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="ext060_svc_") as tmp:
            root = Path(tmp)
            _write(root, "main.py", CRASHING_MAIN)
            accepted, note = grade_real_system_task(REST_SQLITE_CRUD_TASK, root, python_exe=PY)
            assert accepted is False
            assert note  # a diagnostic note, never a silent/blank failure

    def test_never_binds_fixture_never_raises_and_is_rejected(self):
        never_binds = "import time\ntime.sleep(60)\n"
        with tempfile.TemporaryDirectory(prefix="ext060_svc_") as tmp:
            root = Path(tmp)
            _write(root, "main.py", never_binds)
            spec = dict(REST_SQLITE_CRUD_TASK.oracle_spec)
            spec["startup_timeout"] = 1.5
            spec["request_timeout"] = 1.0
            task = REST_SQLITE_CRUD_TASK.__class__(
                name=REST_SQLITE_CRUD_TASK.name, cls=REST_SQLITE_CRUD_TASK.cls,
                sentence=REST_SQLITE_CRUD_TASK.sentence, oracle_kind="service", oracle_spec=spec,
            )
            accepted, note = grade_real_system_task(task, root, python_exe=PY)
            assert accepted is False
            assert note


class TestCrudTaskDeclaration:
    def test_task_is_declared_correctly(self):
        assert REST_SQLITE_CRUD_TASK.oracle_kind == "service"
        assert REST_SQLITE_CRUD_TASK.cls == "rest-api"
        assert "PORT" in REST_SQLITE_CRUD_TASK.sentence
        assert "data.db" in REST_SQLITE_CRUD_TASK.sentence
        assert REST_SQLITE_CRUD_TASK.oracle_spec["entry"] == "main.py"
        assert REST_SQLITE_CRUD_TASK.oracle_spec["db"]["min_rows"] == 1

    def test_task_is_a_member_of_real_systems_tasks(self):
        names = {t.name for t in REAL_SYSTEMS_TASKS}
        assert REST_SQLITE_CRUD_TASK.name in names

    def test_task_is_leaves_off(self):
        assert leaf_for_spec(REST_SQLITE_CRUD_TASK.sentence) is None


# --- (b) MODIFY task: correct post-modify fixture accepted, unmodified baseline rejected -------

class TestServiceOracleGradesTheModifyTaskCorrectly:
    def test_correct_post_modify_fixture_is_accepted(self):
        with tempfile.TemporaryDirectory(prefix="ext060_svcmod_") as tmp:
            root = Path(tmp)
            _write(root, "main.py", CORRECT_MAIN_WITH_PUT)
            accepted, note = grade_real_system_task(
                REST_SQLITE_ADD_UPDATE_MODIFY, root, python_exe=PY
            )
            assert accepted is True, note

    def test_unmodified_baseline_lacking_put_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="ext060_svcmod_") as tmp:
            root = Path(tmp)
            _write(root, "main.py", _REST_SQLITE_BASELINE_PY)
            accepted, note = grade_real_system_task(
                REST_SQLITE_ADD_UPDATE_MODIFY, root, python_exe=PY
            )
            assert accepted is False


class TestModifyTaskDeclaration:
    def test_task_is_declared_correctly(self):
        assert REST_SQLITE_ADD_UPDATE_MODIFY.oracle_kind == "service"
        assert "main.py" in REST_SQLITE_ADD_UPDATE_MODIFY.start_system
        assert "PUT" in REST_SQLITE_ADD_UPDATE_MODIFY.mod_sentence
        assert "do_PUT" not in REST_SQLITE_ADD_UPDATE_MODIFY.start_system["main.py"]

    def test_task_is_a_member_of_real_systems_modify_tasks(self):
        names = {t.name for t in REAL_SYSTEMS_MODIFY_TASKS}
        assert REST_SQLITE_ADD_UPDATE_MODIFY.name in names

    def test_task_is_leaves_off(self):
        assert leaf_for_spec(REST_SQLITE_ADD_UPDATE_MODIFY.mod_sentence) is None


# --- (c) `json_body` extension: additive + byte-identical for checks that omit it --------------
# A NEW test module (not an edit to tests/test_ext036_server_oracle_stdlib.py, which this task
# does not touch) proving harness.server_oracle's `json_body` extension (added by this task) is
# backward-compatible: a check with no `json_body` key sends no request body at all, exactly as it
# did before this key existed.

ECHO_MAIN = '''import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send_json(200, {"got_body": False})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        self._send_json(200, {"got_body": bool(raw), "raw_len": len(raw)})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ["PORT"])
    server = HTTPServer(("127.0.0.1", port), Handler)
    server.serve_forever()
'''


class TestJsonBodyExtensionIsAdditive:
    def test_check_without_json_body_sends_no_body_exactly_as_before(self):
        from harness.server_oracle import serve_and_check_stdlib

        with tempfile.TemporaryDirectory(prefix="ext060_jsonbody_") as tmp:
            root = Path(tmp)
            _write(root, "main.py", ECHO_MAIN)
            result = serve_and_check_stdlib(
                root, "main.py",
                [{"method": "POST", "path": "/", "status": 200,
                  "json_contains": {"got_body": False, "raw_len": 0}}],
                startup_timeout=15, request_timeout=5,
            )
            assert result["ok"] is True, result["note"]

    def test_check_with_json_body_sends_a_real_json_request_body(self):
        from harness.server_oracle import serve_and_check_stdlib

        with tempfile.TemporaryDirectory(prefix="ext060_jsonbody_") as tmp:
            root = Path(tmp)
            _write(root, "main.py", ECHO_MAIN)
            result = serve_and_check_stdlib(
                root, "main.py",
                [{"method": "POST", "path": "/", "json_body": {"name": "alpha"},
                  "status": 200, "json_contains": {"got_body": True}}],
                startup_timeout=15, request_timeout=5,
            )
            assert result["ok"] is True, result["note"]
# #EXT-060-REQ-9 End
