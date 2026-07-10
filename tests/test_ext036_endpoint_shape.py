"""Offline tests for EXT-036 REQ-53: deterministic endpoint-shape contract repair.

No model/Jetson call anywhere in this file. MEASURED MOTIVATION (2 code-dumped draws,
`scratchpad/restput_diag.out`): `rest-sqlite-items-put-modify` measures 0/3 because gemma writes a
PERFECT `do_PUT` body (a real SQLite UPDATE + rowcount check + re-SELECT + correct statuses) but
guards it with `if len(parts) == 3 and parts[0] == 'items' and parts[1].isdigit():` -- `"/items/1"`
always splits into exactly TWO segments, so the guard never matches and every PUT falls through to
a generic 404. The END-TO-END cases below are proven against a REAL running stdlib server via
`harness.server_oracle.serve_and_check_stdlib` -- the same oracle `harness.real_systems_suite` uses
to grade the "service" oracle_kind -- so a green here is a genuine offline proof the repaired code
actually serves a real PUT round-trip, with an unrepaired control confirming the bug is real.
"""
# #EXT-036-REQ-53 Start
from __future__ import annotations

import ast
from pathlib import Path

from harness.endpoint_shape import (
    apply_endpoint_shape,
    endpoint_segment_counts,
    repair_endpoint_shape_guards,
)
from harness.server_oracle import serve_and_check_stdlib
from harness.system_builder import _apply_deterministic_repairs

PUT_SPEC = (
    "Write a Python web service in a file named main.py using only the standard library "
    "(http.server + json). On startup it listens on the TCP port given by the PORT environment "
    "variable. It serves a JSON REST API for `items`: `POST /items` inserts a new item and "
    "responds 201 with the created item as JSON; `PUT /items/<id>` updates an existing item's "
    "name and responds 200 with the updated item as JSON, or 404 if absent."
)

# The MEASURED broken shape: a path-segment-count guard that can never actually admit a real
# `/items/<id>` request (needs `== 2`, not `== 3`) even though the gated UPDATE body itself is
# entirely correct.
BROKEN_DO_PUT_MAIN_PY = '''
import json
import os
import socketserver
from http.server import BaseHTTPRequestHandler

_ITEMS = {1: {"id": 1, "name": "alpha"}}
_NEXT_ID = [2]


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/items":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        item_id = _NEXT_ID[0]
        _NEXT_ID[0] += 1
        item = {"id": item_id, "name": body.get("name")}
        _ITEMS[item_id] = item
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(item).encode())

    def do_PUT(self):
        path = self.path
        parts = path.strip('/').split('/')
        if len(parts) == 3 and parts[0] == 'items' and parts[1].isdigit():
            item_id = int(parts[1])
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            if item_id not in _ITEMS:
                self.send_response(404)
                self.end_headers()
                return
            _ITEMS[item_id]["name"] = body.get("name")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(_ITEMS[item_id]).encode())
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    with socketserver.TCPServer(("", port), Handler) as httpd:
        httpd.serve_forever()
'''

# Not `.split('/')`-derived -- must never be touched.
NOT_SPLIT_DERIVED_PY = '''
def handle(parts):
    if len(parts) == 3:
        return parts[0], parts[1]
    return None
'''

NE_GUARD_PY = '''
def handle(path):
    parts = path.strip('/').split('/')
    if len(parts) != 3:
        return None
    return parts[1]
'''

LT_GUARD_PY = '''
def handle(path):
    parts = path.strip('/').split('/')
    if len(parts) < 3:
        return None
    return parts[1]
'''

ALREADY_CONSISTENT_PY = '''
def handle(path):
    parts = path.strip('/').split('/')
    if len(parts) == 2 and parts[0] == 'items':
        return parts[1]
    return None
'''

NO_INDEX_BODY_PY = '''
def handle(path):
    parts = path.strip('/').split('/')
    if len(parts) == 3:
        return "matched"
    return None
'''


class TestEndpointSegmentCounts:
    def test_parses_items_and_items_id_variants(self):
        spec = (
            "POST /items creates an item. PUT /items/<id> updates it. "
            "DELETE /items/{id} removes it. GET /items/:id fetches it."
        )
        assert endpoint_segment_counts(spec) == {1, 2}

    def test_parses_multi_segment_template(self):
        spec = ("GET /users/<user_id>/orders lists a user's orders. "
                 "GET /users/<user_id> fetches one user.")
        assert endpoint_segment_counts(spec) == {2, 3}

    def test_empty_or_garbage_spec_yields_empty_set(self):
        assert endpoint_segment_counts("") == set()
        assert endpoint_segment_counts(None) == set()
        assert endpoint_segment_counts("just prose, no paths here") == set()
        assert endpoint_segment_counts(12345) == set()  # type: ignore[arg-type]


class TestRepairMeasuredShape:
    """(2) THE MEASURED SHAPE: the exact broken do_PUT is rewritten to `len(parts) == 2`,
    everything else byte-identical; the repaired module compiles."""

    def test_measured_broken_guard_is_repaired_to_two(self):
        repaired = repair_endpoint_shape_guards(BROKEN_DO_PUT_MAIN_PY, PUT_SPEC)
        assert repaired != BROKEN_DO_PUT_MAIN_PY
        assert "len(parts) == 2 and parts[0] == 'items' and parts[1].isdigit():" in repaired
        assert "len(parts) == 3" not in repaired
        compile(repaired, "<main.py>", "exec")  # genuinely compiles

    def test_only_the_literal_changed_everything_else_byte_identical(self):
        repaired = repair_endpoint_shape_guards(BROKEN_DO_PUT_MAIN_PY, PUT_SPEC)
        before_lines = BROKEN_DO_PUT_MAIN_PY.splitlines()
        after_lines = repaired.splitlines()
        assert len(before_lines) == len(after_lines)
        diffs = [(b, a) for b, a in zip(before_lines, after_lines) if b != a]
        assert len(diffs) == 1
        before_line, after_line = diffs[0]
        assert before_line.replace("== 3", "== 2") == after_line


class TestEndToEndRepair:
    """(3) END-TO-END: the repaired do_PUT genuinely serves a real PUT round-trip; the
    UNREPAIRED control genuinely fails the same check."""

    def test_repaired_put_genuinely_serves(self, tmp_path: Path):
        repaired = repair_endpoint_shape_guards(BROKEN_DO_PUT_MAIN_PY, PUT_SPEC)
        (tmp_path / "main.py").write_text(repaired, encoding="utf-8")
        checks = [
            {"method": "POST", "path": "/items", "json_body": {"name": "alpha"}, "status": 201},
            {"method": "PUT", "path": "/items/1", "json_body": {"name": "beta"},
             "status": 200, "json_contains": {"name": "beta", "id": 1}},
        ]
        result = serve_and_check_stdlib(tmp_path, "main.py", checks)
        assert result["ok"] is True, result["note"]
        for r in result["results"]:
            assert r["passed"], r

    def test_unrepaired_put_genuinely_fails_the_same_check(self, tmp_path: Path):
        (tmp_path / "main.py").write_text(BROKEN_DO_PUT_MAIN_PY, encoding="utf-8")
        checks = [
            {"method": "POST", "path": "/items", "json_body": {"name": "alpha"}, "status": 201},
            {"method": "PUT", "path": "/items/1", "json_body": {"name": "beta"},
             "status": 200, "json_contains": {"name": "beta", "id": 1}},
        ]
        result = serve_and_check_stdlib(tmp_path, "main.py", checks)
        assert result["ok"] is False


class TestNonFiringSafety:
    """(4) Non-firing safety: never touches a guard that doesn't need it, and never raises."""

    def test_guard_already_in_endpoint_set_is_unchanged(self):
        assert repair_endpoint_shape_guards(ALREADY_CONSISTENT_PY, PUT_SPEC) == ALREADY_CONSISTENT_PY

    def test_no_endpoints_parseable_is_unchanged(self):
        assert repair_endpoint_shape_guards(BROKEN_DO_PUT_MAIN_PY, "no paths mentioned here") == BROKEN_DO_PUT_MAIN_PY
        assert repair_endpoint_shape_guards(BROKEN_DO_PUT_MAIN_PY, "") == BROKEN_DO_PUT_MAIN_PY
        assert repair_endpoint_shape_guards(BROKEN_DO_PUT_MAIN_PY, None) == BROKEN_DO_PUT_MAIN_PY

    def test_name_not_split_derived_is_unchanged(self):
        assert repair_endpoint_shape_guards(NOT_SPLIT_DERIVED_PY, PUT_SPEC) == NOT_SPLIT_DERIVED_PY

    def test_ne_guard_is_unchanged(self):
        assert repair_endpoint_shape_guards(NE_GUARD_PY, PUT_SPEC) == NE_GUARD_PY

    def test_lt_guard_is_unchanged(self):
        assert repair_endpoint_shape_guards(LT_GUARD_PY, PUT_SPEC) == LT_GUARD_PY

    def test_no_index_in_body_still_fires_with_smallest_consistent_count(self):
        # No constant index is read off `parts` at all -- nothing to contradict, so the
        # smallest spec-derived count (1) is the provably-safe pick.
        repaired = repair_endpoint_shape_guards(NO_INDEX_BODY_PY, PUT_SPEC)
        assert "len(parts) == 1" in repaired

    def test_never_raises_on_garbage(self):
        assert repair_endpoint_shape_guards(None, PUT_SPEC) == ""
        assert repair_endpoint_shape_guards("", PUT_SPEC) == ""
        assert repair_endpoint_shape_guards("def f(:\n", PUT_SPEC) == "def f(:\n"
        assert repair_endpoint_shape_guards("   not python !! @#$", PUT_SPEC) == "   not python !! @#$"
        assert repair_endpoint_shape_guards(BROKEN_DO_PUT_MAIN_PY, object()) == BROKEN_DO_PUT_MAIN_PY  # type: ignore[arg-type]

    def test_apply_endpoint_shape_never_raises_on_garbage(self):
        assert apply_endpoint_shape(None, PUT_SPEC) == {}
        assert apply_endpoint_shape({}, PUT_SPEC) == {}
        assert apply_endpoint_shape("not a dict", PUT_SPEC) == {}  # type: ignore[arg-type]
        assert apply_endpoint_shape({"a.py": None}, PUT_SPEC) == {"a.py": ""}
        assert apply_endpoint_shape({"broken.py": "def f(:\n"}, PUT_SPEC) == {"broken.py": "def f(:\n"}

    def test_multi_module_only_offending_module_changes(self):
        modules = {
            "main.py": BROKEN_DO_PUT_MAIN_PY,
            "helpers.py": NOT_SPLIT_DERIVED_PY,
            "already_ok.py": ALREADY_CONSISTENT_PY,
        }
        result = apply_endpoint_shape(modules, PUT_SPEC)
        assert result["main.py"] != modules["main.py"]
        assert "len(parts) == 2" in result["main.py"]
        assert result["helpers.py"] == modules["helpers.py"]
        assert result["already_ok.py"] == modules["already_ok.py"]

    def test_never_mutates_input_dict(self):
        modules = {"main.py": BROKEN_DO_PUT_MAIN_PY}
        original = dict(modules)
        apply_endpoint_shape(modules, PUT_SPEC)
        assert modules == original


class TestApplyViaModifyChain:
    """(5) apply via `_apply_deterministic_repairs`: a modules dict with the broken shape + an
    http `spec_text` goes through the MODIFY chain and comes out repaired -- proves the wire."""

    def test_modify_chain_repairs_the_broken_put_guard(self):
        modules = {"main.py": BROKEN_DO_PUT_MAIN_PY}
        result = _apply_deterministic_repairs(modules, PUT_SPEC)
        assert "len(parts) == 2" in result["main.py"]
        assert "len(parts) == 3" not in result["main.py"]
        ast.parse(result["main.py"])  # still compiles after the full chain

    def test_modify_chain_leaves_the_guard_unrepaired_for_a_non_http_spec(self):
        # The endpoint-shape lever specifically must NOT fire when the spec implies no
        # endpoint templates -- other, unrelated chain members (e.g. port-coercion, which
        # always wraps a bind-site port reference regardless of spec text) may still
        # re-serialize the module, so this asserts the ENDPOINT-SHAPE invariant precisely
        # rather than whole-file byte-identity.
        modules = {"main.py": BROKEN_DO_PUT_MAIN_PY}
        result = _apply_deterministic_repairs(modules, "Build a CLI that reverses a string.")
        assert "len(parts) == 3" in result["main.py"]
        assert "len(parts) == 2" not in result["main.py"]
# #EXT-036-REQ-53 End
