"""EXT-036 REQ-70: tests for harness/db_init_call.py (deterministic DB/state-init-call repair
for a stdlib http.server build that kept its OWN real serve loop). Fully OFFLINE for the AST-level
tests; the reproduction/fix tests additionally launch a REAL subprocess on an ephemeral localhost
port and drive real HTTP requests (via ``harness.server_oracle.serve_and_check_stdlib``) -- no
model/Jetson call anywhere in this file.
"""
# #EXT-036-REQ-70 Start
from __future__ import annotations

import ast

from harness.db_init_call import (
    apply_db_init_call,
    find_instance_init_methods,
    find_serve_sites,
)
from harness.server_oracle import serve_and_check_stdlib

STDLIB_SPEC = (
    "Build a URL shortener as a stdlib http.server web service. It must implement `POST "
    "/links` and `GET /links/<id>` over the PORT environment variable. REST endpoints."
)

# The MEASURED reproduction (url-shortener-http-service): database.py defines a correct
# zero-arg CREATE-TABLE instance method on a zero-arg-constructible class, but nothing on the
# path to the server bind ever calls it.
DATABASE_PY = '''
import sqlite3


class DatabaseManager:
    def __init__(self, db_path="data.db"):
        self.db_path = db_path

    def initialize_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS links (id INTEGER PRIMARY KEY, url TEXT)")
        conn.commit()
        conn.close()

    def create_link(self, url):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("INSERT INTO links (url) VALUES (?)", (url,))
        conn.commit()
        link_id = cur.lastrowid
        conn.close()
        return link_id

    def get_link(self, link_id):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT url FROM links WHERE id = ?", (link_id,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
'''

API_PY = '''
from database import DatabaseManager


class LinkHandler(DatabaseManager):
    def route(self, method, path, data):
        if method == "POST" and path == "/links":
            link_id = self.create_link((data or {}).get("url"))
            return 201, {"id": link_id}
        if method == "GET" and path.startswith("/links/"):
            link_id = int(path.rsplit("/", 1)[-1])
            url = self.get_link(link_id)
            if url is None:
                return 404, {"error": "not found"}
            return 200, {"url": url}
        return 404, {"error": "not found"}
'''

SERVER_PY = '''
import json
import socketserver
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

from database import DatabaseManager
from api import LinkHandler

_handler = LinkHandler()


class Handler(BaseHTTPRequestHandler):
    def _reply(self, status, body):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw) if raw else None
        except Exception:
            data = None
        status, body = _handler.route("POST", urlparse(self.path).path, data)
        self._reply(status, body)

    def do_GET(self):
        status, body = _handler.route("GET", urlparse(self.path).path, None)
        self._reply(status, body)

    def log_message(self, fmt, *args):
        pass


def start_server(port):
    with socketserver.TCPServer(("", int(port)), Handler) as httpd:
        httpd.serve_forever()
'''

MAIN_PY = '''
import os

from server import start_server

if __name__ == "__main__":
    port = os.environ.get("PORT", "8000")
    start_server(port)
'''

FIXTURE_MODULES = {
    "main.py": MAIN_PY,
    "server.py": SERVER_PY,
    "api.py": API_PY,
    "database.py": DATABASE_PY,
}


def _write(root, modules):
    for name, code in modules.items():
        (root / name).write_text(code, encoding="utf-8")


def _start_server_body(code: str) -> list:
    tree = ast.parse(code)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "start_server":
            return node.body
    raise AssertionError("start_server not found")


class TestFinders:
    def test_finds_instance_init_method(self):
        candidates = find_instance_init_methods(FIXTURE_MODULES)
        assert candidates == [
            {"module": "database", "class": "DatabaseManager", "callable": "initialize_db"}
        ]

    def test_finds_serve_site(self):
        sites = find_serve_sites(FIXTURE_MODULES)
        assert sites == [{"module": "server", "kind": "function", "name": "start_server"}]

    def test_no_candidates_on_garbage(self):
        assert find_instance_init_methods("not a dict") == []
        assert find_instance_init_methods({"x.py": None}) == []
        assert find_instance_init_methods(None) == []
        assert find_serve_sites("not a dict") == []
        assert find_serve_sites({"x.py": "def f(:"}) == []
        assert find_serve_sites(None) == []


class TestApplyDbInitCallAst:
    def test_injects_call_before_bind(self):
        repaired, notes = apply_db_init_call(FIXTURE_MODULES, STDLIB_SPEC)
        assert any("initialize_db" in n for n in notes)

        body = _start_server_body(repaired["server.py"])
        assert len(body) >= 2
        first = body[0]
        assert isinstance(first, ast.Expr)
        call = first.value
        assert isinstance(call, ast.Call)
        assert isinstance(call.func, ast.Attribute)
        assert call.func.attr == "initialize_db"
        assert isinstance(call.func.value, ast.Call)
        assert isinstance(call.func.value.func, ast.Name)
        assert call.func.value.func.id == "DatabaseManager"

        # every other module is untouched
        assert repaired["main.py"] == FIXTURE_MODULES["main.py"]
        assert repaired["api.py"] == FIXTURE_MODULES["api.py"]
        assert repaired["database.py"] == FIXTURE_MODULES["database.py"]

    def test_repaired_code_still_parses(self):
        repaired, _ = apply_db_init_call(FIXTURE_MODULES, STDLIB_SPEC)
        for code in repaired.values():
            ast.parse(code)


class TestApplyDbInitCallLive:
    """Actually RUNS the built service in a FRESH tempdir over a free ephemeral port -- the
    strongest possible proof: the unrepaired build genuinely crashes on a real request (not a
    sandbox artifact), and the repaired build genuinely serves a POST-create/GET round-trip."""

    HTTP_CHECKS = [
        {"method": "POST", "path": "/links", "status": 201,
         "json_body": {"url": "http://example.com"}, "json_contains": {"id": 1}},
        {"method": "GET", "path": "/links/1", "status": 200,
         "json_contains": {"url": "http://example.com"}},
    ]

    def test_unrepaired_build_genuinely_crashes_on_fresh_db(self, tmp_path):
        _write(tmp_path, FIXTURE_MODULES)
        result = serve_and_check_stdlib(
            tmp_path, "main.py", self.HTTP_CHECKS, startup_timeout=15, request_timeout=5,
        )
        assert result["ok"] is False

    def test_repaired_build_genuinely_serves_the_roundtrip(self, tmp_path):
        repaired, notes = apply_db_init_call(FIXTURE_MODULES, STDLIB_SPEC)
        assert repaired["server.py"] != FIXTURE_MODULES["server.py"], notes
        _write(tmp_path, repaired)
        result = serve_and_check_stdlib(
            tmp_path, "main.py", self.HTTP_CHECKS, startup_timeout=15, request_timeout=5,
        )
        assert result["ok"] is True, result["note"]
        assert all(r["passed"] for r in result["results"]), result["results"]


class TestIdempotency:
    def test_already_called_is_a_byte_identical_noop(self):
        already_ok_server = SERVER_PY.replace(
            "def start_server(port):\n",
            "def start_server(port):\n    DatabaseManager().initialize_db()\n",
        )
        modules = dict(FIXTURE_MODULES)
        modules["server.py"] = already_ok_server
        repaired, notes = apply_db_init_call(modules, STDLIB_SPEC)
        assert repaired == modules
        assert any("already called" in n or "idempotent" in n for n in notes)

    def test_applying_twice_equals_applying_once(self):
        once, _ = apply_db_init_call(FIXTURE_MODULES, STDLIB_SPEC)
        twice, _ = apply_db_init_call(once, STDLIB_SPEC)
        assert once == twice


class TestNonDegradingNoOps:
    def test_no_init_export_is_a_noop(self):
        modules = {
            "database.py": "class DatabaseManager:\n    def __init__(self):\n        pass\n",
            "server.py": SERVER_PY,
            "api.py": API_PY,
            "main.py": MAIN_PY,
        }
        repaired, notes = apply_db_init_call(modules, STDLIB_SPEC)
        assert repaired == modules

    def test_non_zero_arg_ctor_is_a_noop(self):
        modules = dict(FIXTURE_MODULES)
        modules["database.py"] = DATABASE_PY.replace(
            'def __init__(self, db_path="data.db"):', "def __init__(self, db_path):",
        )
        repaired, notes = apply_db_init_call(modules, STDLIB_SPEC)
        assert repaired == modules

    def test_multiple_candidates_is_a_noop(self):
        modules = dict(FIXTURE_MODULES)
        modules["cache.py"] = (
            "class CacheManager:\n"
            "    def __init__(self):\n"
            "        pass\n\n"
            "    def init_storage(self):\n"
            "        pass\n"
        )
        repaired, notes = apply_db_init_call(modules, STDLIB_SPEC)
        assert repaired == modules
        assert any("ambiguous" in n for n in notes)

    def test_flask_service_is_a_noop(self):
        modules = {
            "main.py": (
                "from flask import Flask\n"
                "app = Flask(__name__)\n\n"
                "@app.route('/links', methods=['POST'])\n"
                "def create():\n"
                "    return {}\n"
            ),
        }
        repaired, notes = apply_db_init_call(modules, STDLIB_SPEC)
        assert repaired == modules

    def test_non_web_spec_is_a_noop(self):
        repaired, notes = apply_db_init_call(FIXTURE_MODULES, "Write a CSV column-stats CLI.")
        assert repaired == FIXTURE_MODULES

    def test_no_real_serve_loop_is_a_noop(self):
        modules = dict(FIXTURE_MODULES)
        modules["server.py"] = "def start_server(port):\n    pass\n"
        repaired, notes = apply_db_init_call(modules, STDLIB_SPEC)
        assert repaired == modules

    def test_class_not_resolvable_in_serve_module_is_a_noop(self):
        modules = dict(FIXTURE_MODULES)
        modules["server.py"] = SERVER_PY.replace("from database import DatabaseManager\n", "")
        repaired, notes = apply_db_init_call(modules, STDLIB_SPEC)
        assert repaired == modules
        assert any("not resolvable" in n for n in notes)

    def test_multiple_serve_sites_is_a_noop(self):
        modules = dict(FIXTURE_MODULES)
        modules["server2.py"] = SERVER_PY.replace("start_server", "start_server_two")
        repaired, notes = apply_db_init_call(modules, STDLIB_SPEC)
        assert repaired == modules
        assert any("serve site" in n for n in notes)


class TestNeverRaises:
    def test_garbage_inputs(self):
        assert apply_db_init_call(None, STDLIB_SPEC) == ({}, [])
        assert apply_db_init_call({}, STDLIB_SPEC) == ({}, [])
        assert apply_db_init_call("not a dict", STDLIB_SPEC)[0] == {}
        repaired, _ = apply_db_init_call({"main.py": None}, STDLIB_SPEC)
        assert repaired == {"main.py": None}
        repaired, _ = apply_db_init_call({"main.py": "def ("}, STDLIB_SPEC)
        assert repaired == {"main.py": "def ("}
        # missing/garbage spec text
        repaired, notes = apply_db_init_call(FIXTURE_MODULES, None)
        assert repaired == FIXTURE_MODULES and notes == []
        repaired, notes = apply_db_init_call(FIXTURE_MODULES, 12345)
        assert repaired == FIXTURE_MODULES and notes == []
# #EXT-036-REQ-70 End
