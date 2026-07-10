"""Offline tests for EXT-036 REQ-51: the stdlib-http-service ROUTING CONTRACT.

MEASURED MOTIVATION (4 code-dumped draws, `.jaros-data/artifacts/saas_diag.log` + the
port-coercion/scaffold repairs already landed as REQ-45/46/48/50): gemma's hand-rolled
`http.server` PROTOCOL code is unstable PER DRAW -- a plain function passed where `TCPServer`
needs a handler CLASS, a hallucinated `request.end_positive()`, a router with no serve loop at
all, a str-typed PORT -- so per-draw extraction/repair can never chase every shape.

The two-plane fix, tested here in two halves:
  (A) PROMPT half (`harness/system_builder.py`'s `_routing_contract_guidance`) -- for a spec
      demanding a stdlib `http.server` service, every per-module build prompt is told to expose
      EXACTLY a pure `route(method, path, body) -> (status, body)` function and write NO
      protocol code at all.
  (B) SCAFFOLD half (`harness/http_service_scaffold.py`'s `find_route_function` +
      `generate_route_skeleton`, wired into `apply_http_service_scaffold`) -- whenever a
      top-level `route()` is recognized, the deterministic server ALWAYS owns ALL protocol,
      unconditionally replacing whatever entrypoint/serve-loop code the model emitted (broken
      OR already-working).

No model/Jetson call anywhere in this file -- a stub `llm` (canned `.complete(LlmRequest) ->
.text`) mirrors the convention used across `tests/test_ext036_*.py`. The END-TO-END scaffold
cases (TestApplyScaffoldEndToEnd below) are proven against a REAL running stdlib server via
`harness.server_oracle.serve_and_check_stdlib` -- the same oracle `harness.real_systems_suite`
uses to grade the "service" oracle_kind -- so a green here is a genuine offline proof the
repaired code actually binds PORT and serves real HTTP.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.http_service_scaffold import (
    apply_http_service_scaffold,
    find_route_function,
    generate_route_skeleton,
)
from harness.server_oracle import serve_and_check_stdlib
from harness.system_builder import (
    ROUTING_CONTRACT_GUIDANCE,
    _build_module,
    _routing_contract_guidance,
)

# #EXT-036-REQ-51 Start

REST_SPEC = (
    "Write a Python web service in a file named main.py using only the standard library "
    "(http.server + json). On startup it listens on the TCP port given by the PORT "
    "environment variable. It serves a JSON REST API for `items`: `POST /items` inserts a new "
    "item and responds 201 with the created item as JSON; `GET /items` responds 200 with a "
    "JSON array of all items; `DELETE /items/<id>` deletes it and responds 204, or 404 if "
    "absent."
)

NON_HTTP_SPEC = "Build a CLI that reverses a string from stdin."


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


class _RecordingLlm:
    """A trivial stub that always returns the same canned body and records every prompt it
    was called with -- the same convention `tests/test_ext036_interface_seam.py` uses."""

    def __init__(self, response: str = "def f():\n    pass\n") -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, request):
        self.prompts.append(request.prompt)
        return _Resp(self.response)


# --- (1) PROMPT half: routing-contract text injection -----------------------------------

class TestRoutingContractGuidance:
    def test_guidance_text_present_for_http_service_spec(self):
        guidance = _routing_contract_guidance(REST_SPEC)
        assert guidance == ROUTING_CONTRACT_GUIDANCE
        assert "def route(method: str, path: str, body: dict | None)" in guidance
        assert "http.server" in guidance
        assert "PORT" in guidance

    def test_guidance_empty_for_non_http_spec(self):
        assert _routing_contract_guidance(NON_HTTP_SPEC) == ""

    def test_guidance_never_raises_on_garbage(self):
        assert _routing_contract_guidance(None) == ""
        assert _routing_contract_guidance(12345) == ""  # type: ignore[arg-type]


class TestBuildModulePromptInjection:
    """Exercise the actual prompt-assembly seam (`_build_module`) directly -- the routing
    contract must reach the model's prompt for an http-service spec and must NOT appear for an
    unrelated spec."""

    def test_routing_contract_appears_in_prompt_for_http_service_spec(self):
        m = {"name": "service.py", "responsibility": "routes requests",
             "exports": [{"name": "route", "signature": "def route(method, path, body):"}],
             "imports": []}
        llm = _RecordingLlm()
        _build_module(REST_SPEC, m, {}, llm)
        assert len(llm.prompts) == 1
        prompt = llm.prompts[0]
        assert "ROUTING CONTRACT" in prompt
        assert "def route(method: str, path: str, body: dict | None)" in prompt
        assert "do NOT read the PORT environment variable" in prompt

    def test_routing_contract_absent_for_non_http_spec(self):
        m = {"name": "reverser.py", "responsibility": "reverses a string",
             "exports": [{"name": "reverse", "signature": "def reverse(s):"}], "imports": []}
        llm = _RecordingLlm()
        _build_module(NON_HTTP_SPEC, m, {}, llm)
        assert len(llm.prompts) == 1
        assert "ROUTING CONTRACT" not in llm.prompts[0]

    def test_routing_contract_wiring_never_breaks_the_syntax_gate(self):
        m = {"name": "service.py", "responsibility": "routes requests",
             "exports": [{"name": "route", "signature": "def route(method, path, body):"}],
             "imports": []}
        llm = _RecordingLlm(response="def route(method, path, body):\n    return 200, {}\n")
        code, ok = _build_module(REST_SPEC, m, {}, llm)
        assert ok is True
        assert code.strip() == "def route(method, path, body):\n    return 200, {}"


# --- (2) SCAFFOLD half: find_route_function ----------------------------------------------

ROUTE_MODULE_CODE = '''
_ITEMS = {}
_NEXT_ID = [1]


def route(method, path, body):
    """Pure routing contract function -- (status, body) tuple, no protocol code."""
    if path == "/items":
        if method == "POST":
            name = (body or {}).get("name")
            if not name:
                return 400, {"error": "missing name"}
            item_id = _NEXT_ID[0]
            _NEXT_ID[0] += 1
            item = {"id": item_id, "name": name}
            _ITEMS[item_id] = item
            return 201, item
        if method == "GET":
            return 200, list(_ITEMS.values())
    if path.startswith("/items/"):
        try:
            item_id = int(path.split("/")[-1])
        except ValueError:
            return 404, {"error": "bad id"}
        if method == "GET":
            item = _ITEMS.get(item_id)
            return (200, item) if item else (404, {"error": "not found"})
        if method == "DELETE":
            if item_id in _ITEMS:
                del _ITEMS[item_id]
                return 204, None
            return 404, {"error": "not found"}
    return 404, {"error": "not found"}
'''


class TestFindRouteFunction:
    def test_finds_route_across_modules(self):
        modules = {
            "unrelated.py": "def helper():\n    return 1\n",
            "service.py": ROUTE_MODULE_CODE,
        }
        found = find_route_function(modules)
        assert found is not None
        assert found["module"] == "service"
        assert found["callable"] == "route"
        assert found["kind"] == "function"

    def test_ignores_wrong_arity_too_few(self):
        modules = {"m.py": "def route(method, path):\n    return 200, None\n"}
        assert find_route_function(modules) is None

    def test_ignores_wrong_arity_too_many(self):
        modules = {"m.py": "def route(method, path, body, extra):\n    return 200, None\n"}
        assert find_route_function(modules) is None

    def test_ignores_route_nested_in_a_class(self):
        modules = {"m.py": (
            "class Handler:\n"
            "    def route(self, method, path, body):\n"
            "        return 200, None\n"
        )}
        assert find_route_function(modules) is None

    def test_ignores_route_nested_in_a_function(self):
        modules = {"m.py": (
            "def outer():\n"
            "    def route(method, path, body):\n"
            "        return 200, None\n"
            "    return route\n"
        )}
        assert find_route_function(modules) is None

    def test_ignores_varargs_route(self):
        modules = {"m.py": "def route(method, path, *rest):\n    return 200, None\n"}
        assert find_route_function(modules) is None

    def test_garbage_never_raises(self):
        assert find_route_function(None) is None
        assert find_route_function("not a dict") is None  # type: ignore[arg-type]
        assert find_route_function({"broken.py": "def f(:\n"}) is None
        assert find_route_function({"m.py": ""}) is None


_HTTP_CHECKS = [
    {"method": "POST", "path": "/items", "json_body": {"name": "alpha"}, "status": 201,
     "json_contains": {"name": "alpha", "id": 1}},
    {"method": "GET", "path": "/items", "status": 200, "body_contains": "alpha"},
    {"method": "DELETE", "path": "/items/1", "status": 204},
    {"method": "GET", "path": "/items/1", "status": 404},
]


class TestApplyScaffoldEndToEndRouteContract:
    """(3) A hand-written CORRECT route() module: apply the scaffold, then run the result
    through `serve_and_check_stdlib` -- a genuine end-to-end pass (server binds, routes,
    correct statuses)."""

    def test_correct_route_module_is_wired_and_serves_for_real(self, tmp_path: Path):
        modules = {"service.py": ROUTE_MODULE_CODE}
        new_mods, notes = apply_http_service_scaffold(modules, REST_SPEC)
        assert "main.py" in new_mods
        assert any("routing contract" in n for n in notes)
        # service.py itself is untouched (byte-identical)
        assert new_mods["service.py"] == modules["service.py"]

        for name, code in new_mods.items():
            (tmp_path / name).write_text(code, encoding="utf-8")

        result = serve_and_check_stdlib(tmp_path, "main.py", _HTTP_CHECKS)
        assert result["ok"] is True, result["note"]
        for r in result["results"]:
            assert r["passed"], r

    def test_never_mutates_input_dict(self):
        modules = {"service.py": ROUTE_MODULE_CODE}
        original = dict(modules)
        apply_http_service_scaffold(modules, REST_SPEC)
        assert modules == original


# The MEASURED broken shape: a plain function passed where TCPServer needs a handler CLASS --
# `has_real_serve_loop` sees the `TCPServer(` text and would (pre-REQ-51) call this "already
# working" and no-op, leaving a service that crashes on the first real request.
BROKEN_MAIN_TCPSERVER_PY = '''
import os
import socketserver


def handle_request(request, db_manager):
    request.end_positive()


port = int(os.environ.get("PORT", "8000"))
with socketserver.TCPServer(("", port), handle_request) as httpd:
    httpd.serve_forever()
'''


class TestScaffoldReplacesBrokenServeLoopWhenRouteExists:
    """(4) route() exists alongside a broken model serve loop (measured
    `TCPServer(("", port), handler_function)` shape) -- the repaired tree passes the same
    serve check."""

    def test_broken_serve_loop_is_replaced_by_the_route_driver(self, tmp_path: Path):
        modules = {"service.py": ROUTE_MODULE_CODE, "main.py": BROKEN_MAIN_TCPSERVER_PY}
        new_mods, notes = apply_http_service_scaffold(modules, REST_SPEC)
        assert new_mods["main.py"] != BROKEN_MAIN_TCPSERVER_PY
        assert "from service import route" in new_mods["main.py"]
        assert any("routing contract" in n for n in notes)

        for name, code in new_mods.items():
            (tmp_path / name).write_text(code, encoding="utf-8")

        result = serve_and_check_stdlib(tmp_path, "main.py", _HTTP_CHECKS)
        assert result["ok"] is True, result["note"]
        for r in result["results"]:
            assert r["passed"], r


# --- (5) Non-degrading -------------------------------------------------------------------

DISPATCH_HANDLER_PY = (
    "def handle(method, path, data):\n"
    "    if method == 'GET':\n"
    "        return 200, {'ok': True}\n"
    "    return 404, {'ok': False}\n"
)

ALREADY_CORRECT_MAIN_PY = (
    "import os\nfrom http.server import HTTPServer, BaseHTTPRequestHandler\n"
    "from dispatch import handle\n"
    "class H(BaseHTTPRequestHandler):\n    pass\n"
    "if __name__ == '__main__':\n"
    "    port = int(os.environ.get('PORT', '8000'))\n"
    "    HTTPServer(('', port), H).serve_forever()\n"
)


class TestNonDegrading:
    def test_no_route_and_already_correct_serve_loop_is_byte_identical(self):
        modules = {"dispatch.py": DISPATCH_HANDLER_PY, "main.py": ALREADY_CORRECT_MAIN_PY}
        new_mods, notes = apply_http_service_scaffold(modules, REST_SPEC)
        assert new_mods == modules
        assert any("already exists" in n for n in notes)

    def test_non_http_spec_is_unchanged(self):
        modules = {"service.py": ROUTE_MODULE_CODE}
        new_mods, notes = apply_http_service_scaffold(modules, NON_HTTP_SPEC)
        assert new_mods == modules
        assert notes == []

    def test_garbage_input_never_raises(self):
        new_mods, notes = apply_http_service_scaffold(None, None)  # type: ignore[arg-type]
        assert new_mods == {}
        new_mods, notes = apply_http_service_scaffold("not a dict", REST_SPEC)  # type: ignore[arg-type]
        assert isinstance(new_mods, dict)
        new_mods, notes = apply_http_service_scaffold({"main.py": "def f(:\n"}, REST_SPEC)
        assert isinstance(new_mods, dict)


class TestGenerateRouteSkeletonUnit:
    def test_import_mode_wires_route_from_module(self):
        handler = {"module": "service", "kind": "function", "class": None, "callable": "route"}
        code = generate_route_skeleton(handler, same_module=False)
        assert "from service import route" in code
        assert "route(method, path, body)" in code
        assert "serve_forever()" in code
        import ast as _ast
        _ast.parse(code)  # must be syntactically valid

    def test_same_module_mode_strips_old_main_guard_and_appends(self):
        handler = {"module": "main", "kind": "function", "class": None, "callable": "route"}
        existing = (
            "def route(method, path, body):\n    return 200, {}\n\n"
            "if __name__ == '__main__':\n    print('old broken entrypoint')\n"
        )
        code = generate_route_skeleton(handler, same_module=True, existing_code=existing)
        assert "old broken entrypoint" not in code
        assert "def route(method, path, body):" in code
        assert "serve_forever()" in code
        import ast as _ast
        _ast.parse(code)

    def test_204_status_forces_empty_body_even_when_body_given(self):
        handler = {"module": "service", "kind": "function", "class": None, "callable": "route"}
        code = generate_route_skeleton(handler, same_module=False)
        assert 'if status == 204' in code
        assert 'payload = b""' in code

# #EXT-036-REQ-51 End
