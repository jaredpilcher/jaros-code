"""EXT-036 REQ-48: deterministic ``http.server`` SCAFFOLD repair for stdlib SaaS builds.

MEASURED (`.jaros-data/artifacts/saas_diag.log`, the first on-Jetson SaaS build, 0/3):
gemma's ``REST_SQLITE_CRUD_TASK`` build gets the BUSINESS LOGIC right -- a SQLite DB layer
(``database.py``) and a request-routing handler (``api.py``'s ``APIHandler.handle_request(method,
path, data) -> (status, body)``) -- but the entrypoint (``main.py``) it emits NEVER calls
``HTTPServer(...).serve_forever()``: it imports ``http.server``/``socketserver``, then just
re-declares a stray ``DatabaseManager`` stub and stops. No real server ever binds the ``PORT``
the ``service`` oracle (``harness.server_oracle.serve_and_check_stdlib``) expects, so EVERY http
check fails before a single request is sent.

Two-plane fix, the same shape as the already-landed filename/signature/guard-index contract
repairs (EXT-036 REQ-45/REQ-46, EXT-035 REQ-3): the MODEL supplies the judgement (the routing +
DB logic already sitting in ``built``); this module supplies the MECHANICAL scaffold (a correct
stdlib ``http.server`` event loop that reads ``PORT``, parses the request, and dispatches to
whatever handler the model already wrote).

Validated via ``.jaros-data/saas_scaffold_probe.py``: gemma's measured shape (a class method with
EXACTLY 3 params after ``self`` -- ``(method, path, data)`` -- returning >=2 distinct
``(status, body)`` 2-tuples) is recognized with a plain AST scan (:func:`find_dispatch_handler`),
and the generated skeleton wired to that handler, when actually RUN with ``PORT`` set, binds the
port and passes a full ``serve_and_check_stdlib`` POST/GET/DELETE round-trip end-to-end -- no
model re-call needed for this (the common, most-confident) shape. When no such handler can be
confidently recognized, the repair is a safe no-op UNLESS an ``llm`` is supplied, in which case it
falls back to a single TARGETED CLEAN-PROMPT retry (the REQ-43 analog) that re-asks the model for
one ``main.py`` implementing the endpoints INSIDE this module's own skeleton contract, built ONLY
from the visible spec text (no oracle leak).

Non-degrading: fires ONLY when the spec demands a stdlib ``http.server`` service AND no module
already has a real serve loop (``serve_forever(``/``HTTPServer(``/``ThreadingHTTPServer(``/
``TCPServer(``) -- an already-working service, a Flask/FastAPI service (covered by the OTHER
oracle path, ``harness.server_oracle.detect_web_service``), or a spec that isn't a web service at
all, is left untouched. Never raises.
"""
# #EXT-036-REQ-48 Start
from __future__ import annotations

import ast
import re

# Reuse (never reimplement) the FastAPI/Flask detector so this repair never fires on a
# framework-based service already covered by the OTHER oracle path.
from harness.server_oracle import detect_web_service

_SERVICE_INDICATOR_RE = re.compile(
    r"\bhttp\.server\b|\bweb service\b|\bREST\b|\bPORT\s+environment variable\b",
    re.IGNORECASE,
)
_ENDPOINT_RE = re.compile(r"`?\b(GET|POST|PUT|DELETE|PATCH)\b\s*/\S*", re.IGNORECASE)
_SERVE_LOOP_RE = re.compile(
    r"\bserve_forever\s*\(|\bHTTPServer\s*\(|\bThreadingHTTPServer\s*\(|\bTCPServer\s*\(",
)


def spec_demands_stdlib_http_service(spec_text: "str | None") -> bool:
    """True when the visible ``spec_text`` demands a plain stdlib ``http.server`` web service:
    it mentions ``http.server``/"web service"/"REST"/"PORT environment variable" AND names at
    least one HTTP-method endpoint (e.g. `` `GET /items` ``). Never raises -- any non-string or
    empty input is simply not a demand."""
    if not spec_text:
        return False
    text = str(spec_text)
    if not _SERVICE_INDICATOR_RE.search(text):
        return False
    if not _ENDPOINT_RE.search(text):
        return False
    return True


def has_real_serve_loop(modules: "dict[str, str] | None") -> bool:
    """True when ANY module in ``modules`` already contains a real stdlib serve-loop
    construct (``serve_forever(``/``HTTPServer(``/``ThreadingHTTPServer(``/``TCPServer(``) --
    the non-degrading guard: this repair must never touch an already-working service. Never
    raises."""
    try:
        items = list((modules or {}).items())
    except (AttributeError, TypeError):
        return False
    for name, code in items:
        try:
            if not name or not str(name).endswith(".py") or not code:
                continue
            if _SERVE_LOOP_RE.search(str(code)):
                return True
        except Exception:
            continue
    return False


def _init_all_defaulted(cls_node: "ast.ClassDef") -> bool:
    """True when ``cls_node`` has no ``__init__`` at all, or its ``__init__`` can be called
    with zero arguments (every positional/keyword-only param beyond ``self`` has a default,
    no bare ``*args``-driven requirement). Used to gate CONFIDENT no-arg instantiation --
    never guessed."""
    init = next(
        (n for n in cls_node.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"),
        None,
    )
    if init is None:
        return True
    n_params = len(init.args.args) - 1  # drop `self`
    n_defaults = len(init.args.defaults)
    required = max(0, n_params - n_defaults)
    kwonly_required = sum(1 for d in (init.args.kw_defaults or []) if d is None)
    return required == 0 and kwonly_required == 0


def _is_dispatcher_shape(func_node: "ast.FunctionDef", *, skip_first: bool) -> bool:
    """True when ``func_node`` has EXACTLY 3 params (after dropping ``self``/``cls`` when
    ``skip_first``) and contains at least 2 ``return`` statements each returning a literal
    2-element tuple -- gemma's measured ``handle_request(method, path, data) -> (status,
    body)`` shape. A confident, generic heuristic (arity + return shape), not tied to any
    specific parameter or task name."""
    args = [a.arg for a in func_node.args.args]
    if skip_first:
        if not args:
            return False
        args = args[1:]
    if len(args) != 3:
        return False
    returns = [
        n for n in ast.walk(func_node)
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Tuple) and len(n.value.elts) == 2
    ]
    return len(returns) >= 2


def find_dispatch_handler(modules: "dict[str, str] | None") -> "dict | None":
    """Best-effort, NEVER-RAISE AST scan of ``{filename: source}`` module SOURCES for a
    confidently-recognizable request-dispatcher callable: a top-level class method (or a
    top-level function) taking exactly 3 params (after ``self``, for a method) and returning
    at least two distinct 2-tuples (gemma's measured ``(method, path, data) -> (status,
    body)`` shape).

    Returns ``{"module": <stem>, "kind": "method"|"function", "class": <name>|None,
    "callable": <name>}`` for the FIRST match (module dict order), or ``None`` when nothing
    confidently matches, or on any malformed input. For a ``"method"`` match, the enclosing
    class's ``__init__`` must be callable with zero arguments (see
    :func:`_init_all_defaulted`) -- a class requiring constructor arguments is skipped, never
    guessed at."""
    try:
        items = list((modules or {}).items())
    except (AttributeError, TypeError):
        return None
    for name, code in items:
        try:
            if not name or not str(name).endswith(".py") or not code:
                continue
            tree = ast.parse(str(code))
        except (SyntaxError, TypeError, ValueError):
            continue
        stem = str(name)[:-3]
        try:
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    if not _init_all_defaulted(node):
                        continue
                    for meth in node.body:
                        if isinstance(meth, ast.FunctionDef) and _is_dispatcher_shape(meth, skip_first=True):
                            return {"module": stem, "kind": "method", "class": node.name,
                                    "callable": meth.name}
                elif isinstance(node, ast.FunctionDef):
                    if _is_dispatcher_shape(node, skip_first=False):
                        return {"module": stem, "kind": "function", "class": None,
                                "callable": node.name}
        except Exception:
            continue
    return None


_SKELETON_HEADER = (
    "import json\n"
    "import os\n"
    "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
    "from urllib.parse import urlparse\n"
)

_SERVER_BLOCK_TEMPLATE = '''

def _dispatch(method, path, data):
    return {dispatch_call}


class _ScaffoldHTTPHandler(BaseHTTPRequestHandler):
    def _handle(self, method):
        path = urlparse(self.path).path
        data = None
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except (TypeError, ValueError):
            length = 0
        if length:
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw)
            except Exception:
                data = None
        status, body = _dispatch(method, path, data)
        payload = json.dumps(body).encode("utf-8") if body is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")

    def do_PATCH(self):
        self._handle("PATCH")

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    HTTPServer(("", port), _ScaffoldHTTPHandler).serve_forever()
'''


def _dispatch_call_expr(handler: dict) -> str:
    if handler.get("kind") == "method":
        return "_handler_instance." + handler["callable"] + "(method, path, data)"
    return handler["callable"] + "(method, path, data)"


def _instantiate_line(handler: dict) -> str:
    if handler.get("kind") == "method":
        return f"_handler_instance = {handler['class']}()\n"
    return ""


def generate_skeleton(handler: dict, *, same_module: bool,
                       existing_code: "str | None" = None) -> str:
    """Build the DETERMINISTIC ``http.server`` MAIN skeleton wired to ``handler`` (a dict from
    :func:`find_dispatch_handler`): reads ``PORT`` via ``os.environ.get("PORT", "8000")``,
    defines a ``BaseHTTPRequestHandler`` subclass whose ``do_GET``/``do_POST``/``do_PUT``/
    ``do_DELETE``/``do_PATCH`` parse the method/path/JSON body and dispatch to ``handler``,
    and runs ``HTTPServer(("", port), ...).serve_forever()`` under ``if __name__ ==
    "__main__":``.

    When ``same_module`` is True (the handler is already defined in the entry module itself),
    the wiring block is APPENDED to ``existing_code`` (no import needed -- the handler is
    already in scope). Otherwise a fresh, self-contained module is generated that imports the
    handler from ``handler['module']``. Pure string composition -- never executes anything."""
    instantiate = _instantiate_line(handler)
    body = _SERVER_BLOCK_TEMPLATE.format(dispatch_call=_dispatch_call_expr(handler))
    if same_module:
        base = (existing_code or "").rstrip("\n")
        return base + "\n\n\n" + _SKELETON_HEADER + "\n" + instantiate + body.lstrip("\n")
    target = handler.get("class") or handler["callable"]
    import_line = f"from {handler['module']} import {target}\n"
    return _SKELETON_HEADER + import_line + "\n" + instantiate + body.lstrip("\n")


# #EXT-036-REQ-51 Start
# TASK-64: the SCAFFOLD half of the stdlib-http-service ROUTING CONTRACT (the PROMPT half
# lives in `harness/system_builder.py`'s `_routing_contract_guidance`). MEASURED (4
# code-dumped draws, `.jaros-data/artifacts/saas_diag.log`): the model's hand-rolled
# `http.server` PROTOCOL code is unstable PER DRAW -- a plain function passed where
# `TCPServer` needs a handler CLASS, a hallucinated `request.end_positive()`, a router with
# no serve loop at all, a str-typed PORT -- so extraction/repair can never chase every shape.
# Instead of recognizing one more per-draw shape, this recognizes the CONTRACT ITSELF: a
# top-level `def route(method, path, body):` -- and, whenever one exists, the deterministic
# server ALWAYS owns ALL protocol, unconditionally REPLACING whatever serve-loop/entrypoint
# code the model emitted (broken OR already-working) with a generated, correct
# `BaseHTTPRequestHandler`/`HTTPServer` driver wired to it. This is checked BEFORE the
# `has_real_serve_loop` non-degrading guard below, so route() precedence is:
#   route() contract  >  existing recognized dispatch shapes (`find_dispatch_handler`)  >
#   skeleton fallback / clean-prompt retry.
# Non-degrading for the OLDER shapes: when no route() exists, this block is a complete no-op
# and the pre-existing find_dispatch_handler/has_real_serve_loop precedence is unchanged.
def find_route_function(modules: "dict[str, str] | None") -> "dict | None":
    """Best-effort, NEVER-RAISE AST scan of ``{filename: source}`` module SOURCES for the
    ROUTING CONTRACT function (REQ-51): a TOP-LEVEL ``def route(...)`` with EXACTLY 3
    parameters (e.g. ``route(method, path, body)``), no ``*args``. A ``route`` def NESTED
    inside a class or another function is ignored (only a genuine top-level, module-scope
    function counts as the contract being honored), as is a wrong-arity ``route`` def.

    Returns ``{"module": <stem>, "kind": "function", "class": None, "callable": "route"}``
    for the FIRST match (module dict order), or ``None`` when nothing matches or on any
    malformed input."""
    try:
        items = list((modules or {}).items())
    except (AttributeError, TypeError):
        return None
    for name, code in items:
        try:
            if not name or not str(name).endswith(".py") or not code:
                continue
            tree = ast.parse(str(code))
        except (SyntaxError, TypeError, ValueError):
            continue
        stem = str(name)[:-3]
        try:
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name == "route":
                    args = node.args
                    n_params = len(list(args.posonlyargs or [])) + len(args.args or [])
                    if n_params == 3 and not args.vararg:
                        return {"module": stem, "kind": "function", "class": None,
                                "callable": "route"}
        except Exception:
            continue
    return None


def _is_main_guard_if(node: "ast.stmt") -> bool:
    """True when ``node`` is a top-level ``if __name__ == "__main__":`` (or the reversed
    ``"__main__" == __name__``) guard -- used to strip a model's own entrypoint block before
    appending the deterministic routing driver in the same module. Never raises."""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)):
        return False
    operands = [test.left, *test.comparators]
    has_name = any(isinstance(o, ast.Name) and o.id == "__name__" for o in operands)
    has_main = any(isinstance(o, ast.Constant) and o.value == "__main__" for o in operands)
    return has_name and has_main


def _strip_main_guard(code: str) -> str:
    """Remove any top-level ``if __name__ == "__main__":`` block(s) from ``code`` -- so
    appending the routing driver's OWN ``__main__`` block never lands behind a model's
    broken/duplicate one. Returns ``code`` UNCHANGED (byte-identical, no re-serialization) when
    there is nothing to strip or on any parse/unparse failure -- never raises."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code
    new_body = [n for n in tree.body if not _is_main_guard_if(n)]
    if len(new_body) == len(tree.body):
        return code
    tree.body = new_body
    try:
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
    except Exception:
        return code


_ROUTE_SKELETON_HEADER = (
    "import json\n"
    "import os\n"
    "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
    "from urllib.parse import urlparse\n"
)

_ROUTE_SERVER_BLOCK = '''

class _RouteHTTPHandler(BaseHTTPRequestHandler):
    def _handle(self, method):
        path = urlparse(self.path).path
        body = None
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except (TypeError, ValueError):
            length = 0
        if length:
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw)
            except Exception:
                body = None
        status, resp_body = route(method, path, body)
        if status == 204:
            payload = b""
        else:
            payload = json.dumps(resp_body).encode("utf-8") if resp_body is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")

    def do_PATCH(self):
        self._handle("PATCH")

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    HTTPServer(("", port), _RouteHTTPHandler).serve_forever()
'''


def generate_route_skeleton(handler: dict, *, same_module: bool,
                             existing_code: "str | None" = None) -> str:
    """Build the DETERMINISTIC ``http.server`` MAIN driver wired to the ROUTING CONTRACT
    function found by :func:`find_route_function`: a ``BaseHTTPRequestHandler`` subclass whose
    ``do_GET``/``do_POST``/``do_PUT``/``do_DELETE``/``do_PATCH`` parse the method/path/JSON
    body, call ``route(method, path, body)``, and write the returned status + JSON body
    (empty body for a 204, correct ``Content-Length`` always), then
    ``HTTPServer(("", port), ...).serve_forever()`` under ``if __name__ == "__main__":``,
    reading ``PORT`` via ``os.environ.get("PORT", "8000")``.

    When ``same_module`` is True (``route`` is already defined in the entry module itself),
    any of the model's OWN ``if __name__ == "__main__":`` block(s) are stripped
    (:func:`_strip_main_guard`) and the driver is APPENDED to what remains -- ``route`` is
    already in scope, no import needed. Otherwise a fresh, self-contained module is generated
    that imports ``route`` from ``handler['module']``. Pure string composition -- never
    executes anything."""
    if same_module:
        base = _strip_main_guard(existing_code or "").rstrip("\n")
        return base + "\n\n\n" + _ROUTE_SKELETON_HEADER + _ROUTE_SERVER_BLOCK.lstrip("\n")
    import_line = f"from {handler['module']} import route\n"
    return _ROUTE_SKELETON_HEADER + import_line + "\n" + _ROUTE_SERVER_BLOCK.lstrip("\n")
# #EXT-036-REQ-51 End


_SCAFFOLD_RETRY_PROMPT = (
    "Write a COMPLETE, correct Python program in ONE file (main.py) that satisfies this "
    "spec:\n\n{spec}\n\n"
    "The file MUST use only the standard library http.server module: read the port via "
    "port = int(os.environ.get(\"PORT\", \"8000\")), define a BaseHTTPRequestHandler "
    "subclass with do_GET/do_POST/do_PUT/do_DELETE methods that parse the request path and "
    "(for POST/PUT) a JSON body, and call HTTPServer((\"\", port), "
    "<YourHandlerClass>).serve_forever() inside if __name__ == \"__main__\":. Output ONLY "
    "the Python code, no prose, no markdown fences."
)


def _strip_fences(text: str) -> str:
    text = re.sub(r"^```[a-zA-Z]*\n", "", (text or "").strip())
    return re.sub(r"\n```$", "", text).strip()


def _retry_via_clean_prompt(spec_text: "str | None", llm) -> "str | None":
    """The targeted clean-prompt retry (the REQ-43 analog): a SINGLE, self-contained call
    that re-asks the model for ONE ``main.py`` implementing the endpoints described in the
    VISIBLE spec text INSIDE this module's own ``http.server`` skeleton contract -- no
    plan/ledger context, no oracle leak (only ``spec_text`` is ever shown to the model).
    Returns the generated code only if it parses AND itself contains a real serve-loop
    construct; ``None`` on any failure (bad response, syntax error, no serve loop). Never
    raises."""
    try:
        from jaros.llm import LlmRequest
        prompt = _SCAFFOLD_RETRY_PROMPT.format(spec=spec_text or "")
        text = llm.complete(LlmRequest(prompt=prompt, params={"temperature": 0.0, "max_tokens": 1400})).text
        code = _strip_fences(text)
        ast.parse(code)
        if not _SERVE_LOOP_RE.search(code):
            return None
        return code
    except Exception:
        return None


def _resolve_entry_name(modules: "dict[str, str]", spec_text: "str | None") -> str:
    from harness.filename_contract import demanded_filenames
    demanded = demanded_filenames(spec_text)
    if demanded:
        return demanded[0].split("/")[-1]
    if "main.py" in modules:
        return "main.py"
    py_mods = [k for k in modules if k.endswith(".py")]
    if len(py_mods) == 1:
        return py_mods[0]
    return "main.py"


def apply_http_service_scaffold(modules: "dict[str, str]", spec_text: "str | None", *,
                                 llm=None) -> "tuple[dict[str, str], list[str]]":
    """The public, never-raising repair: fires ONLY when ``spec_text`` demands a stdlib
    ``http.server`` service (:func:`spec_demands_stdlib_http_service`) AND no Flask/FastAPI/
    Starlette service was detected (:func:`harness.server_oracle.detect_web_service` -- that
    shape is handled by the OTHER oracle path).

    **REQ-51 routing-contract precedence (checked FIRST):** when a top-level ``def
    route(method, path, body):`` is confidently recognized (:func:`find_route_function`), the
    deterministic server ALWAYS owns ALL protocol -- a generated, correct driver
    (:func:`generate_route_skeleton`) unconditionally REPLACES whatever entrypoint/serve-loop
    code the model emitted at the spec-demanded entrypoint filename, whether that code was
    broken OR already a real serve loop (so the ``has_real_serve_loop`` guard below is
    deliberately bypassed for this path -- the routing contract, once honored, is a stronger
    signal than a merely-present serve loop).

    Otherwise (no ``route()`` recognized), the PRE-EXISTING precedence is unchanged: a no-op
    when a real serve loop already exists (:func:`has_real_serve_loop`); else, when a
    dispatcher callable is confidently recognized (:func:`find_dispatch_handler`), wired into
    a freshly generated ``http.server`` skeleton (:func:`generate_skeleton`) at the
    spec-demanded entrypoint filename (reusing ``harness.filename_contract.
    demanded_filenames``, falling back to ``main.py``); otherwise, when ``llm`` is supplied,
    falls back to a single targeted clean-prompt retry (:func:`_retry_via_clean_prompt`); with
    no recognizable handler and no ``llm``, a safe no-op.

    Returns a NEW dict (never mutates ``modules``) plus a list of explanatory notes. Never
    raises -- any internal failure leaves ``modules`` unchanged."""
    try:
        mods = dict(modules or {})
        notes: "list[str]" = []

        if not spec_demands_stdlib_http_service(spec_text):
            return mods, notes
        if not mods:
            return mods, notes

        try:
            if detect_web_service(mods):
                notes.append("a Flask/FastAPI/Starlette service was detected -- scaffold repair not applicable")
                return mods, notes
        except Exception:
            pass

        entry_name = _resolve_entry_name(mods, spec_text)

        # #EXT-036-REQ-51 Start
        route_handler = find_route_function(mods)
        if route_handler is not None:
            same_module = (route_handler["module"] + ".py") == entry_name and entry_name in mods
            existing = mods.get(entry_name) if same_module else None
            try:
                new_code = generate_route_skeleton(route_handler, same_module=same_module,
                                                     existing_code=existing)
                ast.parse(new_code)
            except SyntaxError as exc:
                notes.append(f"generated route() skeleton failed to parse -- no-op: {exc}")
                return mods, notes
            if mods.get(entry_name) == new_code:
                notes.append("route() already correctly wired -- no-op")
                return mods, notes
            mods[entry_name] = new_code
            notes.append(
                f"wired {route_handler['module']}.route into a generated http.server "
                f"skeleton at {entry_name} (routing contract, REQ-51)"
            )
            return mods, notes
        # #EXT-036-REQ-51 End

        if has_real_serve_loop(mods):
            notes.append("a real serve loop already exists -- no-op")
            return mods, notes

        handler = find_dispatch_handler(mods)
        if handler is not None:
            same_module = (handler["module"] + ".py") == entry_name and entry_name in mods
            existing = mods.get(entry_name) if same_module else None
            try:
                new_code = generate_skeleton(handler, same_module=same_module, existing_code=existing)
                ast.parse(new_code)
            except SyntaxError as exc:
                notes.append(f"generated skeleton failed to parse -- no-op: {exc}")
                return mods, notes
            mods[entry_name] = new_code
            handler_label = (
                f"{handler['module']}.{handler['class']}.{handler['callable']}"
                if handler.get("class") else f"{handler['module']}.{handler['callable']}"
            )
            notes.append(f"wired {handler_label} into a generated http.server skeleton at {entry_name}")
            return mods, notes

        if llm is not None:
            retried = _retry_via_clean_prompt(spec_text, llm)
            if retried is not None:
                mods[entry_name] = retried
                notes.append(f"no recognizable handler -- clean-prompt retry produced {entry_name}")
                return mods, notes
            notes.append("no recognizable handler and clean-prompt retry failed -- no-op")
            return mods, notes

        notes.append("no recognizable handler and no llm supplied for retry -- no-op")
        return mods, notes
    except Exception as exc:
        try:
            fallback = dict(modules or {})
        except (TypeError, ValueError):
            fallback = {}
        return fallback, [f"apply_http_service_scaffold failed -- no-op: {exc}"]
# #EXT-036-REQ-48 End
