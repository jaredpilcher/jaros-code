"""Offline tests for EXT-036 REQ-48: deterministic http.server SCAFFOLD repair.

No model/Jetson call anywhere in this file. The recognizable-handler wiring case (test class
TestApplyScaffoldEndToEnd) is proven END-TO-END against a REAL running stdlib server via
`harness.server_oracle.serve_and_check_stdlib` -- the same oracle `harness.real_systems_suite`
uses to grade the "service" oracle_kind -- so a green here is a genuine offline proof the
repaired code actually binds PORT and serves real HTTP.

The fixture modules below reconstruct gemma's MEASURED shape from
`.jaros-data/artifacts/saas_diag.log` (a `database.py` SQLite layer + an `api.py`
`APIHandler.handle_request(method, path, data) -> (status, body)` router + a `main.py` that
imports http.server/socketserver but never calls `HTTPServer(...).serve_forever()`), validated
offline in `.jaros-data/saas_scaffold_probe.py`.
"""
from pathlib import Path

from harness.http_service_scaffold import (
    apply_http_service_scaffold,
    find_dispatch_handler,
    generate_skeleton,
    has_real_serve_loop,
    spec_demands_stdlib_http_service,
)
from harness.server_oracle import serve_and_check_stdlib

REST_SPEC = (
    "Write a Python web service in a file named main.py using only the standard library "
    "(http.server + sqlite3 + json). On startup it listens on the TCP port given by the PORT "
    "environment variable and stores data in a SQLite database file named data.db in the current "
    "directory (create the table if missing). It serves a JSON REST API for `items`, each item "
    "having an integer id (autoincrement) and a string `name`: `POST /items` with a JSON body "
    "`{\"name\": ...}` inserts a new item and responds 201 with the created item as JSON including "
    "its id; `GET /items` responds 200 with a JSON array of all items; `GET /items/<id>` responds "
    "200 with that item as JSON, or 404 if absent; `DELETE /items/<id>` deletes it and responds "
    "204, or 404 if absent. Data must persist in data.db across process restarts."
)

DATABASE_PY = '''
class DatabaseManager:
    def __init__(self, db_name="data.db"):
        self.db_name = db_name

    def _get_connection(self):
        import sqlite3
        conn = sqlite3.connect(self.db_name)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)"
        )
        return conn

    def add_item(self, name):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO items (name) VALUES (?)", (name,))
        conn.commit()
        item = {"id": cur.lastrowid, "name": name}
        conn.close()
        return item

    def get_all_items(self):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM items")
        items = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
        conn.close()
        return items

    def get_item_by_id(self, item_id):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM items WHERE id = ?", (item_id,))
        row = cur.fetchone()
        conn.close()
        return {"id": row[0], "name": row[1]} if row else None

    def delete_item(self, item_id):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM items WHERE id = ?", (item_id,))
        conn.commit()
        deleted = cur.rowcount > 0
        conn.close()
        return deleted
'''

API_PY = '''
from database import DatabaseManager


class APIHandler(DatabaseManager):
    def __init__(self, db_name="data.db"):
        super().__init__(db_name)

    def handle_request(self, method: str, path: str, data: dict = None):
        """Simulates handling an HTTP request. Returns (status_code, response_body)."""
        if path == "/items":
            if method == "POST":
                if not data or "name" not in data:
                    return 400, {"error": "Missing name"}
                item = self.add_item(data["name"])
                return 201, item
            elif method == "GET":
                return 200, self.get_all_items()
        elif path.startswith("/items/"):
            try:
                item_id = int(path.split("/")[-1])
            except ValueError:
                return 404, {"error": "bad id"}
            if method == "GET":
                item = self.get_item_by_id(item_id)
                if item:
                    return 200, item
                return 404, {"error": "not found"}
            elif method == "DELETE":
                if self.delete_item(item_id):
                    return 204, None
                return 404, {"error": "not found"}
        return 404, {"error": "not found"}
'''

# gemma's ACTUAL measured main.py: imports http.server/socketserver but NEVER calls
# serve_forever/HTTPServer( -- the exact defect saas_diag.log shows.
MAIN_PY_NO_LOOP = '''
import os
import http.server
import socketserver
import sqlite3
import json
from api import APIHandler


class DatabaseManager:
    def __init__(self, db_name="data.db"):
        self.db_name = db_name
'''

GEMMA_SAAS_MODULES = {
    "database.py": DATABASE_PY,
    "api.py": API_PY,
    "main.py": MAIN_PY_NO_LOOP,
}

_HTTP_CHECKS = [
    {"method": "POST", "path": "/items", "json_body": {"name": "alpha"}, "status": 201,
     "json_contains": {"name": "alpha", "id": 1}},
    {"method": "POST", "path": "/items", "json_body": {"name": "beta"}, "status": 201,
     "json_contains": {"name": "beta", "id": 2}},
    {"method": "GET", "path": "/items", "status": 200, "body_contains": "alpha"},
    {"method": "GET", "path": "/items/1", "status": 200, "json_contains": {"name": "alpha"}},
    {"method": "DELETE", "path": "/items/1", "status": 204},
    {"method": "GET", "path": "/items/1", "status": 404},
]


class TestSpecDetection:
    def test_rest_spec_is_detected(self):
        assert spec_demands_stdlib_http_service(REST_SPEC) is True

    def test_unrelated_spec_is_not_detected(self):
        assert spec_demands_stdlib_http_service("Build a CLI that reverses a string.") is False

    def test_none_and_empty_never_raise(self):
        assert spec_demands_stdlib_http_service(None) is False
        assert spec_demands_stdlib_http_service("") is False

    def test_requires_endpoint_mention_too(self):
        # mentions http.server but no endpoint -- not confidently a demand
        assert spec_demands_stdlib_http_service("Use http.server for something internal.") is False


class TestHasRealServeLoop:
    def test_true_when_serve_forever_present(self):
        assert has_real_serve_loop({"main.py": "srv.serve_forever()\n"}) is True

    def test_true_when_httpserver_call_present(self):
        assert has_real_serve_loop({"main.py": "HTTPServer(('', 8000), H)\n"}) is True

    def test_false_when_absent(self):
        assert has_real_serve_loop(GEMMA_SAAS_MODULES) is False

    def test_garbage_never_raises(self):
        assert has_real_serve_loop(None) is False
        assert has_real_serve_loop("not a dict") is False  # type: ignore[arg-type]


class TestFindDispatchHandler:
    def test_finds_gemmas_handle_request(self):
        found = find_dispatch_handler(GEMMA_SAAS_MODULES)
        assert found is not None
        assert found["module"] == "api"
        assert found["class"] == "APIHandler"
        assert found["callable"] == "handle_request"
        assert found["kind"] == "method"

    def test_no_match_returns_none(self):
        assert find_dispatch_handler({"a.py": "def add(x, y):\n    return x + y\n"}) is None

    def test_garbage_never_raises(self):
        assert find_dispatch_handler(None) is None
        assert find_dispatch_handler({"broken.py": "def f(:\n"}) is None


class TestApplyScaffoldEndToEnd:
    """(a) recognizable handler + no serve loop -> the repaired main.py, when actually RUN
    with PORT set, binds the port and passes a real serve_and_check_stdlib round-trip."""

    def test_a_recognized_handler_wired_and_serves_for_real(self, tmp_path: Path):
        new_mods, notes = apply_http_service_scaffold(GEMMA_SAAS_MODULES, REST_SPEC)
        assert "main.py" in new_mods
        assert has_real_serve_loop(new_mods) is True
        assert any("wired api.APIHandler.handle_request" in n for n in notes)
        # database.py/api.py themselves are untouched (byte-identical)
        assert new_mods["database.py"] == GEMMA_SAAS_MODULES["database.py"]
        assert new_mods["api.py"] == GEMMA_SAAS_MODULES["api.py"]

        for name, code in new_mods.items():
            (tmp_path / name).write_text(code, encoding="utf-8")

        result = serve_and_check_stdlib(tmp_path, "main.py", _HTTP_CHECKS)
        assert result["ok"] is True, result["note"]
        for r in result["results"]:
            assert r["passed"], r

    def test_never_mutates_input_dict(self):
        original = dict(GEMMA_SAAS_MODULES)
        apply_http_service_scaffold(GEMMA_SAAS_MODULES, REST_SPEC)
        assert GEMMA_SAAS_MODULES == original


class TestNoOpCases:
    def test_b_noop_when_real_serve_loop_already_present(self):
        working = dict(GEMMA_SAAS_MODULES)
        working["main.py"] = (
            "import os\nfrom http.server import HTTPServer, BaseHTTPRequestHandler\n"
            "class H(BaseHTTPRequestHandler):\n    pass\n"
            "if __name__ == '__main__':\n"
            "    port = int(os.environ.get('PORT', '8000'))\n"
            "    HTTPServer(('', port), H).serve_forever()\n"
        )
        new_mods, notes = apply_http_service_scaffold(working, REST_SPEC)
        assert new_mods == working
        assert any("already exists" in n for n in notes)

    def test_c_noop_when_spec_is_not_a_web_service(self):
        new_mods, notes = apply_http_service_scaffold(
            GEMMA_SAAS_MODULES, "Build a CLI that reverses a string from stdin."
        )
        assert new_mods == GEMMA_SAAS_MODULES
        assert notes == []

    def test_noop_when_flask_service_detected(self):
        flask_mods = {
            "main.py": "from flask import Flask\napp = Flask(__name__)\n",
        }
        new_mods, notes = apply_http_service_scaffold(flask_mods, REST_SPEC)
        assert new_mods == flask_mods
        assert any("Flask" in n for n in notes)

    def test_no_llm_and_no_handler_is_a_safe_noop(self):
        modules = {"main.py": "import http.server\n"}
        new_mods, notes = apply_http_service_scaffold(modules, REST_SPEC)
        assert new_mods == modules
        assert any("no-op" in n for n in notes)


class TestNeverRaises:
    def test_d_none_inputs_never_raise(self):
        new_mods, notes = apply_http_service_scaffold(None, None)  # type: ignore[arg-type]
        assert new_mods == {}

    def test_d_garbage_modules_never_raise(self):
        new_mods, notes = apply_http_service_scaffold("not a dict", REST_SPEC)  # type: ignore[arg-type]
        assert isinstance(new_mods, dict)

    def test_d_unparseable_module_never_raises(self):
        modules = {"main.py": "def f(:\n"}
        new_mods, notes = apply_http_service_scaffold(modules, REST_SPEC)
        assert isinstance(new_mods, dict)

    def test_d_spec_of_unexpected_type_never_raises(self):
        new_mods, notes = apply_http_service_scaffold(GEMMA_SAAS_MODULES, 12345)  # type: ignore[arg-type]
        assert isinstance(new_mods, dict)


class TestGenerateSkeletonUnit:
    def test_import_mode_wires_class_method(self):
        handler = {"module": "api", "kind": "method", "class": "APIHandler", "callable": "handle_request"}
        code = generate_skeleton(handler, same_module=False)
        assert "from api import APIHandler" in code
        assert "_handler_instance = APIHandler()" in code
        assert "_handler_instance.handle_request(method, path, data)" in code
        assert "serve_forever()" in code
        import ast as _ast
        _ast.parse(code)  # must be syntactically valid

    def test_same_module_mode_appends_to_existing_code(self):
        handler = {"module": "main", "kind": "function", "class": None, "callable": "dispatch"}
        existing = "def dispatch(method, path, data):\n    return 200, {}\n    return 404, {}\n"
        code = generate_skeleton(handler, same_module=True, existing_code=existing)
        assert code.startswith(existing.rstrip("\n"))
        assert "dispatch(method, path, data)" in code
        assert "from api import" not in code
        import ast as _ast
        _ast.parse(code)
