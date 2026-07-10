"""Offline tests for EXT-036 REQ-65 (TASK-80): DB/state-init detection in the HTTP-service
scaffold.

MEASURED MOTIVATION (`scratchpad/batch3_diag_urlshort_d1.out`): `url-shortener-http-service`
fails with "Remote end closed connection without response" -- gemma's own `route()`/logic
module defines a correct zero-arg `initialize_db()` (creates the SQLite table) and calls it
from ITS OWN `start_server()`, but the deterministic route-skeleton
(`harness/http_service_scaffold.py`'s `generate_route_skeleton`) NEVER calls it -- only
`HTTPServer(...).serve_forever()` runs, so the first real request hits
`sqlite3.OperationalError: no such table` and the handler dies mid-request.

No model/Jetson call anywhere in this file. The END-TO-END cases run a REAL stdlib HTTP server
via `harness.server_oracle.serve_and_check_stdlib` -- a genuine offline proof the fix actually
initializes state before serving, and that the UNREPAIRED control genuinely fails the same way.
"""
from __future__ import annotations

import ast
from pathlib import Path

from harness.http_service_scaffold import (
    apply_http_service_scaffold,
    find_init_functions,
    find_route_function,
    generate_route_skeleton,
    generate_skeleton,
)
from harness.server_oracle import serve_and_check_stdlib

# --- fixtures -----------------------------------------------------------------------------

SHORTENER_SPEC = (
    "Write a Python web service in a file named main.py using only the standard library "
    "(http.server + sqlite3 + json). On startup it listens on the TCP port given by the PORT "
    "environment variable and stores data in a SQLite database (create the table if missing). "
    "`POST /shorten` with a JSON body `{\"url\": ...}` creates a short code and responds 201 "
    "with `{\"code\": ...}`; `GET /<code>` responds 200 with `{\"url\": ...}` if the code "
    "exists, or 404 otherwise."
)

NON_HTTP_SPEC = "Build a CLI that reverses a string from stdin."

# gemma's MEASURED shape: a `route()` module that owns its own `initialize_db()` (creates the
# table) but never gets a chance to call it once the deterministic scaffold takes over.
URL_SHORTENER_MODULE_CODE = '''
import sqlite3

DB_NAME = "shortener.db"


def initialize_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS urls (code TEXT PRIMARY KEY, url TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()


def route(method, path, body):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    if path == "/shorten" and method == "POST":
        url = (body or {}).get("url")
        if not url:
            conn.close()
            return 400, {"error": "missing url"}
        code = "abc123"
        cur.execute("INSERT OR REPLACE INTO urls (code, url) VALUES (?, ?)", (code, url))
        conn.commit()
        conn.close()
        return 201, {"code": code}
    if method == "GET" and path.startswith("/"):
        short_code = path.strip("/")
        cur.execute("SELECT url FROM urls WHERE code = ?", (short_code,))
        row = cur.fetchone()
        conn.close()
        if row:
            return 200, {"url": row[0]}
        return 404, {"error": "not found"}
    conn.close()
    return 404, {"error": "not found"}
'''

_HTTP_CHECKS = [
    {"method": "POST", "path": "/shorten", "json_body": {"url": "http://example.com"},
     "status": 201, "json_contains": {"code": "abc123"}},
    {"method": "GET", "path": "/abc123", "status": 200,
     "json_contains": {"url": "http://example.com"}},
]


# --- (1) the MEASURED shape: END-TO-END genuine pass vs. genuine control failure ----------

class TestMeasuredShapeEndToEnd:
    def test_apply_scaffold_calls_init_and_serves_the_real_round_trip(self, tmp_path: Path):
        modules = {"service.py": URL_SHORTENER_MODULE_CODE}
        new_mods, notes = apply_http_service_scaffold(modules, SHORTENER_SPEC)
        assert "main.py" in new_mods
        assert "initialize_db()" in new_mods["main.py"]
        assert "from service import initialize_db" in new_mods["main.py"]
        # the call must come BEFORE serve_forever()
        assert new_mods["main.py"].index("initialize_db()\n") < new_mods["main.py"].index(
            "serve_forever()"
        )
        ast.parse(new_mods["main.py"])
        # service.py itself is untouched (byte-identical)
        assert new_mods["service.py"] == modules["service.py"]

        for name, code in new_mods.items():
            (tmp_path / name).write_text(code, encoding="utf-8")

        result = serve_and_check_stdlib(tmp_path, "main.py", _HTTP_CHECKS)
        assert result["ok"] is True, result["note"]
        for r in result["results"]:
            assert r["passed"], r

    def test_unrepaired_control_without_the_init_call_genuinely_fails(self, tmp_path: Path):
        """The pre-REQ-65 shape (no init_candidates wired) genuinely fails -- proving the
        end-to-end pass above is a REAL fix, not a fabricated one."""
        handler = find_route_function({"service.py": URL_SHORTENER_MODULE_CODE})
        assert handler is not None
        control_main = generate_route_skeleton(handler, same_module=False)
        assert "initialize_db" not in control_main

        (tmp_path / "service.py").write_text(URL_SHORTENER_MODULE_CODE, encoding="utf-8")
        (tmp_path / "main.py").write_text(control_main, encoding="utf-8")

        result = serve_and_check_stdlib(tmp_path, "main.py", _HTTP_CHECKS)
        assert result["ok"] is False
        assert result["results"][0]["passed"] is False


# --- (2) no init function -> byte-identical to today's skeleton ---------------------------

NO_INIT_ROUTE_MODULE_CODE = (
    "def route(method, path, body):\n"
    "    return 200, {'ok': True}\n"
)

NO_INIT_DISPATCH_MODULE_CODE = (
    "def handle(method, path, data):\n"
    "    if method == 'GET':\n"
    "        return 200, {'ok': True}\n"
    "    return 404, {'ok': False}\n"
)


class TestNoInitFunctionNonDegrading:
    def test_route_skeleton_byte_identical_when_no_init_function_present(self):
        modules = {"service.py": NO_INIT_ROUTE_MODULE_CODE}
        assert find_init_functions(modules) == []
        new_mods, _ = apply_http_service_scaffold(modules, SHORTENER_SPEC)
        handler = {"module": "service", "kind": "function", "class": None, "callable": "route"}
        expected = generate_route_skeleton(handler, same_module=False)
        assert new_mods["main.py"] == expected

    def test_dispatch_skeleton_byte_identical_when_no_init_function_present(self):
        modules = {"dispatch.py": NO_INIT_DISPATCH_MODULE_CODE}
        assert find_init_functions(modules) == []
        new_mods, _ = apply_http_service_scaffold(modules, SHORTENER_SPEC)
        handler = {"module": "dispatch", "kind": "function", "class": None, "callable": "handle"}
        expected = generate_skeleton(handler, same_module=False)
        assert new_mods["main.py"] == expected

    def test_generate_functions_default_kwargs_produce_the_same_output(self):
        handler = {"module": "service", "kind": "function", "class": None, "callable": "route"}
        assert generate_route_skeleton(handler, same_module=False) == generate_route_skeleton(
            handler, same_module=False, init_candidates=None, entry_stem=None
        )
        d_handler = {"module": "dispatch", "kind": "function", "class": None, "callable": "handle"}
        assert generate_skeleton(d_handler, same_module=False) == generate_skeleton(
            d_handler, same_module=False, init_candidates=None, entry_stem=None
        )


# --- (3) init with required args -> skipped ------------------------------------------------

REQUIRED_ARG_INIT_MODULE_CODE = (
    "def initialize_db(conn):\n"
    "    conn.execute('CREATE TABLE IF NOT EXISTS t (id INTEGER)')\n\n\n"
    "def route(method, path, body):\n"
    "    return 200, {'ok': True}\n"
)


class TestRequiredArgInitSkipped:
    def test_find_init_functions_skips_a_required_arg_function(self):
        modules = {"service.py": REQUIRED_ARG_INIT_MODULE_CODE}
        assert find_init_functions(modules) == []

    def test_apply_scaffold_never_calls_a_required_arg_init(self):
        modules = {"service.py": REQUIRED_ARG_INIT_MODULE_CODE}
        new_mods, _ = apply_http_service_scaffold(modules, SHORTENER_SPEC)
        assert "initialize_db()" not in new_mods["main.py"]
        assert "initialize_db" not in new_mods["main.py"]
        ast.parse(new_mods["main.py"])

    def test_default_args_only_are_still_recognized_as_zero_arg(self):
        modules = {"service.py": (
            "def initialize_db(path='data.db'):\n    pass\n\n\n"
            "def route(method, path, body):\n    return 200, {}\n"
        )}
        candidates = find_init_functions(modules)
        assert candidates == [{"module": "service", "callable": "initialize_db"}]

    def test_required_keyword_only_arg_is_skipped(self):
        modules = {"service.py": (
            "def initialize_db(*, conn):\n    pass\n\n\n"
            "def route(method, path, body):\n    return 200, {}\n"
        )}
        assert find_init_functions(modules) == []


# --- (4) multiple init candidates -> called in module order -------------------------------

MULTI_INIT_MODULES = {
    "database.py": (
        "def setup_db():\n    pass\n"
    ),
    "cache.py": (
        "def init_storage():\n    pass\n"
    ),
    "service.py": (
        "def route(method, path, body):\n    return 200, {'ok': True}\n"
    ),
}


class TestMultipleInitCandidatesCalledInOrder:
    def test_find_init_functions_returns_candidates_in_module_order(self):
        candidates = find_init_functions(MULTI_INIT_MODULES)
        assert candidates == [
            {"module": "database", "callable": "setup_db"},
            {"module": "cache", "callable": "init_storage"},
        ]

    def test_apply_scaffold_calls_both_in_module_order_before_serve_forever(self):
        new_mods, notes = apply_http_service_scaffold(dict(MULTI_INIT_MODULES), SHORTENER_SPEC)
        main_code = new_mods["main.py"]
        ast.parse(main_code)
        assert "from database import setup_db" in main_code
        assert "from cache import init_storage" in main_code
        i_setup = main_code.index("setup_db()\n")
        i_storage = main_code.index("init_storage()\n")
        i_serve = main_code.index("serve_forever()")
        assert i_setup < i_storage < i_serve

    def test_end_to_end_both_inits_run_before_the_server_binds(self, tmp_path: Path):
        modules = dict(MULTI_INIT_MODULES)
        new_mods, notes = apply_http_service_scaffold(modules, SHORTENER_SPEC)
        for name, code in new_mods.items():
            (tmp_path / name).write_text(code, encoding="utf-8")
        result = serve_and_check_stdlib(
            tmp_path, "main.py", [{"method": "GET", "path": "/x", "status": 200}]
        )
        assert result["ok"] is True, result["note"]


# --- (5) never raises / garbage input -------------------------------------------------------

class TestFindInitFunctionsNeverRaises:
    def test_garbage_never_raises(self):
        assert find_init_functions(None) == []
        assert find_init_functions("not a dict") == []  # type: ignore[arg-type]
        assert find_init_functions({"broken.py": "def f(:\n"}) == []
        assert find_init_functions({"m.py": ""}) == []

    def test_ignores_class_method_and_nested_function_named_like_init(self):
        modules = {"m.py": (
            "class Store:\n"
            "    def initialize_db(self):\n"
            "        pass\n\n\n"
            "def outer():\n"
            "    def setup_db():\n"
            "        pass\n"
            "    return setup_db\n"
        )}
        assert find_init_functions(modules) == []

    def test_case_insensitive_name_match(self):
        modules = {"m.py": "def INITIALIZE_DB():\n    pass\n"}
        assert find_init_functions(modules) == [{"module": "m", "callable": "INITIALIZE_DB"}]
