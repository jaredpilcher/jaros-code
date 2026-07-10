"""Offline tests for EXT-036 REQ-52 (TASK-65): wire the deterministic repair CHAIN into the
MODIFY path.

MEASURED MOTIVATION: the build path runs a deterministic repair chain
(``apply_signature_contract``, ``apply_port_coercion``, ``apply_http_service_scaffold``,
``apply_agent_scaffold`` -- REQ-45/48/49/50, plus the REQ-51 routing-contract wired into
``_build_module``) over every module it BUILDS -- and the SaaS CREATE class improved 0/3 -> 1/3
on these levers. ``modify_system`` regenerates a module the SAME way (``_regenerate_module``/
``_build_new_module`` reuse the same syntax-gate/repair loop), so it can reintroduce the SAME
mechanical protocol bugs -- but until this task NOTHING repaired them on the MODIFY path
(measured: ``rest-put-modify`` stuck at 0/3 while CREATE improved).

No model/Jetson call anywhere in this file -- a stub ``llm`` (``.complete(LlmRequest) -> .text``)
mirrors the convention used across every ``tests/test_ext036_*.py`` file for ``modify_system``.
Tests (a)/(b) are proven END-TO-END against a REAL running stdlib server via
``harness.server_oracle.serve_and_check_stdlib``, the same oracle
``harness.real_systems_suite`` uses to grade the "service" oracle_kind -- so a green here is a
genuine offline proof the repaired code actually binds PORT and serves real HTTP after a
MODIFICATION, not just a CREATE.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("OLLAMA_MODEL", "gemma2:2b")

from harness.server_oracle import serve_and_check_stdlib
from harness.system_builder import _apply_deterministic_repairs, modify_system

# #EXT-036-REQ-52 Start


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text


# --- (a) port-coercion fires on a MODIFY-regenerated module -------------------------------

# A plausible, already-CORRECT pre-modification server (int-coerced port).
_HEALTH_MAIN_ORIGINAL = '''
import os
import socketserver
from http.server import BaseHTTPRequestHandler


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    with socketserver.TCPServer(("", port), Handler) as httpd:
        httpd.serve_forever()
'''

# gemma's MEASURED regeneration shape (mirrors tests/test_ext036_port_coercion.py's
# TCPSERVER_STR_PORT_MAIN_PY): the modification's own change is fine, but the REGENERATED
# module drops the int() coercion at the bind site again.
_HEALTH_MAIN_STR_PORT_REGEN = '''
import os
import socketserver
from http.server import BaseHTTPRequestHandler


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok", "version": 2}')

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = os.getenv("PORT")
    with socketserver.TCPServer(("", port), Handler) as httpd:
        httpd.serve_forever()
'''

_PORT_MOD_SENTENCE = "Add a version field to the health response."

_HEALTH_CHECKS = [
    {"method": "GET", "path": "/health", "status": 200, "body_contains": "ok"},
]


class _PortBugModifyLlm:
    """Routes `.complete()` the SAME way `tests/test_ext036_modify.py`'s `_CannedModifyLlm`
    does: "MODIFICATION TARGET" / "APPLY MODIFICATION" (the regenerated body, here the MEASURED
    str-PORT regression shape) / "ACCEPTANCE CHECKS" (both derivations skipped -- `[]` -- so
    this test is isolated to the REQ-52 seam, not the checklist-derivation machinery)."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "MODIFICATION TARGET" in prompt:
            return _Resp('["main.py"]')
        if "APPLY MODIFICATION" in prompt:
            return _Resp(_HEALTH_MAIN_STR_PORT_REGEN)
        if "SYNTAX ERROR" in prompt:
            return _Resp("")
        if "RUNNABLE PYTHON CODE" in prompt:
            return _Resp("[]")
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp("[]")
        return _Resp("")


def test_port_coercion_fires_on_modify_regenerated_module(tmp_path):
    root = tmp_path / "sys"
    llm = _PortBugModifyLlm()
    result = modify_system({"main.py": _HEALTH_MAIN_ORIGINAL}, _PORT_MOD_SENTENCE, root, llm=llm)

    assert result["applied"] is True
    modified_main = result["modules"]["main.py"]
    # the str-PORT bug the regeneration reintroduced is REPAIRED at the bind site
    assert "int(port)" in modified_main
    assert (root / "main.py").read_text() == modified_main

    # genuinely RUNS: a real stdlib server, launched with a str-typed PORT env var (the real
    # 12-factor contract `serve_and_check_stdlib` always uses), actually binds and serves.
    check_result = serve_and_check_stdlib(root, "main.py", _HEALTH_CHECKS)
    assert check_result["ok"] is True, check_result["note"]
    for r in check_result["results"]:
        assert r["passed"], r


# --- (b) http-service scaffold (route() precedence, REQ-51) fires via `spec_hint` ----------

_HTTP_SPEC_HINT = (
    "Write a Python web service in a file named main.py using only the standard library "
    "(http.server + json). It listens on the TCP PORT environment variable and serves "
    "`GET /items`."
)

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

# The MEASURED broken shape (mirrors tests/test_ext036_routing_contract.py): a plain function
# passed where TCPServer needs a handler CLASS -- `has_real_serve_loop` would (pre-REQ-51) see
# `TCPServer(` and call this "already working," leaving a service that crashes on every request.
BROKEN_MAIN_TCPSERVER_PY = '''
import os
import socketserver


def handle_request(request, db_manager):
    request.end_positive()


port = int(os.environ.get("PORT", "8000"))
with socketserver.TCPServer(("", port), handle_request) as httpd:
    httpd.serve_forever()
'''

_ITEMS_HTTP_CHECKS = [
    {"method": "POST", "path": "/items", "json_body": {"name": "alpha"}, "status": 201,
     "json_contains": {"name": "alpha", "id": 1}},
    {"method": "GET", "path": "/items", "status": 200, "body_contains": "alpha"},
    {"method": "DELETE", "path": "/items/1", "status": 204},
    {"method": "GET", "path": "/items/1", "status": 404},
]

_ROUTE_MOD_SENTENCE = "Wire the items GET route into the running server."


class _RouteScaffoldModifyLlm:
    """Regenerates TWO existing modules: `service.py` (gains a correct top-level `route()`) and
    `main.py` (regenerated with a BROKEN model-authored serve loop that doesn't even call
    `route()`) -- the exact shape `_apply_deterministic_repairs`'s
    `apply_http_service_scaffold` step must recognize and replace wholesale (REQ-51
    precedence)."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "MODIFICATION TARGET" in prompt:
            return _Resp('["service.py", "main.py"]')
        if "APPLY MODIFICATION" in prompt:
            if "`service.py`" in prompt:
                return _Resp(ROUTE_MODULE_CODE)
            if "`main.py`" in prompt:
                return _Resp(BROKEN_MAIN_TCPSERVER_PY)
            return _Resp("")
        if "SYNTAX ERROR" in prompt:
            return _Resp("")
        if "RUNNABLE PYTHON CODE" in prompt:
            return _Resp("[]")
        if "ACCEPTANCE CHECKS" in prompt:
            return _Resp("[]")
        return _Resp("")


def test_http_service_scaffold_fires_on_modify_via_spec_hint(tmp_path):
    root = tmp_path / "sys"
    llm = _RouteScaffoldModifyLlm()
    # No exports in either baseline module -> the deterministic smoke-fallback baseline check
    # (REQ-2/6, engaged because the canned llm returns "[]" for every ACCEPTANCE CHECKS call)
    # asserts only "modules import without error", so it stays satisfied after the modification
    # regardless of which NAMES the regenerated modules end up exporting -- isolating this test
    # to the REQ-52 seam under test, not an unrelated smoke-check name mismatch.
    baseline = {"service.py": "# placeholder\n", "main.py": "# placeholder\n"}
    result = modify_system(baseline, _ROUTE_MOD_SENTENCE, root, llm=llm, spec_hint=_HTTP_SPEC_HINT)

    assert result["applied"] is True
    # the recognized route() module is untouched -- only the entrypoint is replaced
    assert result["modules"]["service.py"].strip() == ROUTE_MODULE_CODE.strip()
    assert result["modules"]["main.py"] != BROKEN_MAIN_TCPSERVER_PY
    assert "from service import route" in result["modules"]["main.py"]
    assert (root / "main.py").read_text() == result["modules"]["main.py"]

    # genuinely RUNS: a real POST/GET/DELETE round-trip against the repaired server.
    check_result = serve_and_check_stdlib(root, "main.py", _ITEMS_HTTP_CHECKS)
    assert check_result["ok"] is True, check_result["note"]
    for r in check_result["results"]:
        assert r["passed"], r


def test_http_service_scaffold_does_not_fire_without_indicator_text(tmp_path):
    """Honest scope: a `mod_sentence` that names an HTTP method+path (e.g. "Add a `PUT
    /items/<id>` endpoint...") but never says "REST"/"web service"/"http.server"/"PORT
    environment variable" does NOT satisfy `spec_demands_stdlib_http_service` on its own (no
    `spec_hint` given) -- the routing-contract detector's indicator+endpoint AND-gate is
    unaffected by this task, only fed a wider spec_text when a caller supplies `spec_hint`."""
    from harness.http_service_scaffold import spec_demands_stdlib_http_service
    put_only_sentence = "Add a `PUT /items/<id>` endpoint that updates an item's name."
    assert spec_demands_stdlib_http_service(put_only_sentence) is False


# --- (c) non-http modify -> module set unchanged by the seam (byte-identical pass-through) --

CALC_ORIGINAL = "def add(a, b):\n    return a + b\n"
CALC_WITH_MUL = "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"

_CALC_MOD_SENTENCE = "add a mul(a, b) function to calc.py"

_CALC_BASELINE_CHECKLIST = (
    '[{"name": "adds correctly", "code": "from calc import add\\nassert add(1, 2) == 3\\n"}]'
)
_CALC_NEW_CHECKLIST = (
    '[{"name": "multiplies correctly", "code": "from calc import mul\\nassert mul(2, 3) == 6\\n"}]'
)


class _CalcModifyLlm:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "MODIFICATION TARGET" in prompt:
            return _Resp('["calc.py"]')
        if "APPLY MODIFICATION" in prompt:
            return _Resp(CALC_WITH_MUL)
        if "SYNTAX ERROR" in prompt:
            return _Resp("")
        if "RUNNABLE PYTHON CODE" in prompt:
            return _Resp("[]")
        if "ACCEPTANCE CHECKS" in prompt:
            if _CALC_MOD_SENTENCE in prompt:
                return _Resp(_CALC_NEW_CHECKLIST)
            return _Resp(_CALC_BASELINE_CHECKLIST)
        return _Resp("")


def test_non_http_modification_is_byte_identical_pass_through(tmp_path):
    root = tmp_path / "sys"
    llm = _CalcModifyLlm()
    result = modify_system({"calc.py": CALC_ORIGINAL}, _CALC_MOD_SENTENCE, root, llm=llm)

    assert result["applied"] is True
    # the seam never touches a plain, non-http/agent/port/signature-documented module -- the
    # regenerated content ships EXACTLY as the model wrote it (module-level equality; a leading/
    # trailing-newline normalization happens upstream in the shared syntax-gate/repair loop,
    # unrelated to this task, so compare stripped like every other EXT-036 modify test does).
    assert result["modules"]["calc.py"].strip() == CALC_WITH_MUL.strip()
    assert (root / "calc.py").read_text().strip() == CALC_WITH_MUL.strip()


def test_apply_deterministic_repairs_is_a_no_op_for_plain_code():
    modules = {"calc.py": CALC_WITH_MUL}
    result = _apply_deterministic_repairs(modules, _CALC_MOD_SENTENCE)
    assert result == modules
    assert result is not modules   # never mutates/aliases the input dict


# --- (d) `_apply_deterministic_repairs` never raises on garbage ----------------------------

def test_apply_deterministic_repairs_never_raises_on_garbage():
    assert _apply_deterministic_repairs(None, None) == {}
    assert _apply_deterministic_repairs("not a dict", "some spec") is not None
    assert isinstance(_apply_deterministic_repairs({"broken.py": "def f(:\n"}, "x"), dict)
    assert isinstance(_apply_deterministic_repairs({}, None), dict)
    # a spec_text that demands an http service but modules are garbage -- still never raises
    assert isinstance(
        _apply_deterministic_repairs({"m.py": None}, _HTTP_SPEC_HINT), dict  # type: ignore[dict-item]
    )


# --- (e) the regression gate still holds with the repair chain wired in --------------------

CALC_MUL_BREAKS_ADD = "def add(a, b):\n    return a * b\n\n\ndef mul(a, b):\n    return a * b\n"


class _RegressingCalcModifyLlm(_CalcModifyLlm):
    def complete(self, request):
        prompt = request.prompt
        self.prompts.append(prompt)
        if "APPLY MODIFICATION" in prompt:
            return _Resp(CALC_MUL_BREAKS_ADD)
        return super().complete(request)


def test_regression_gate_still_rejects_a_genuinely_regressing_modification(tmp_path):
    """The repair chain running (here a no-op, since `calc.py` has no http/port/agent/
    signature-default shape) must NEVER rescue a modification that breaks existing behavior --
    REQ-14's regression gate is unweakened by REQ-52."""
    root = tmp_path / "sys"
    llm = _RegressingCalcModifyLlm()
    result = modify_system({"calc.py": CALC_ORIGINAL}, _CALC_MOD_SENTENCE, root, llm=llm)

    assert result["applied"] is False
    assert result["regressed"] == ["adds correctly"]
    # reverted to the PRE-modification content, byte-identical -- disk AND the returned dict
    assert result["modules"]["calc.py"] == CALC_ORIGINAL
    assert (root / "calc.py").read_text() == CALC_ORIGINAL

# #EXT-036-REQ-52 End
