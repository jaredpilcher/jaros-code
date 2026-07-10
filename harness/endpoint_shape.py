"""Deterministic endpoint-shape contract repair (EXT-036 TASK-66, REQ-53).

MEASURED ROOT CAUSE (2 code-dumped draws, `scratchpad/restput_diag.out`): the canonical-board
`rest-sqlite-items-put-modify` MODIFY class measures 0/3 -- gemma writes a PERFECT ``do_PUT`` body
(a real SQLite ``UPDATE``, a ``rowcount`` check, a re-``SELECT`` of the updated row, and the
correct 200/404 statuses) but GUARDS it with a path-segment-count guard that can never actually
admit the real request:

    parts = path.strip('/').split('/')
    if len(parts) == 3 and parts[0] == 'items' and parts[1].isdigit():
        ...  # the correct UPDATE logic, entirely unreachable

``"/items/1"`` splits into exactly TWO segments (``['items', '1']``), never three -- so the guard
never matches and every ``PUT`` silently falls through to a generic 404. IDENTICAL across both
draws (deterministic, not sampling variance). The existing length-guard repair
(``harness.system_builder.repair_guard_index_mismatch``, REQ-39) correctly does NOT fire here --
there is no unreachable-INDEX contradiction (the body only ever indexes ``parts[0]``/``parts[1]``,
both valid at ``len(parts) == 3``); the bug is only provable against the VISIBLE spec's own
endpoint template (``"PUT /items/<id>"`` implies exactly TWO path segments), which is the same
epistemics as the signature-contract repair (REQ-45): a documented contract in the visible spec
vs. the code's actual shape, mechanical + leak-free.

Leak-free (Tenet 3): the corrected segment count comes ONLY from URL path templates parsed out of
the visible build ``spec_text`` -- never a hidden oracle/test/reference implementation.
Non-degrading + conservative: fires ONLY on a simple ``==`` length guard (or the first clause of an
``and``-chained guard) on a name traced to a ``.split('/')`` call within the SAME function, whose
constant is NOT one of the spec's own parsed segment counts, and only rewrites it to a count that
is provably consistent with the guard's own true-branch body (large enough to cover every constant
index the body actually reads off that name) -- the smallest such count when several qualify.
Never touches a chained/other comparison beyond the leading ``==`` clause, never guesses when the
literal's source span can't be located, and returns the input BYTE-IDENTICAL on any parse failure
or when no provable repair applies. Never raises.
"""
# #EXT-036-REQ-53 Start
import ast
import re

_SEG = r"(?:<[A-Za-z_]\w*>|\{[A-Za-z_]\w*\}|:[A-Za-z_]\w*|[A-Za-z_][\w\-]*)"
_PATH_RE = re.compile(rf"(?<!\w)/{_SEG}(?:/{_SEG})*")


def endpoint_segment_counts(spec_text: "str | None") -> "set[int]":
    """Parse every URL path TEMPLATE (a ``/``-starting token, e.g. ``/items``,
    ``/items/<id>``, ``/items/{id}``, ``/items/:id``, ``/users/<user_id>/orders``) out of the
    visible ``spec_text`` and return the SET of segment counts those templates imply (each
    counted the same way the built code would: ``path.strip('/').split('/')``). Returns an
    empty set for absent/garbage/no-match spec text. Never raises."""
    out: "set[int]" = set()
    if not spec_text or not isinstance(spec_text, str):
        return out
    for m in _PATH_RE.finditer(spec_text):
        segs = [s for s in m.group(0).strip("/").split("/") if s]
        if segs:
            out.add(len(segs))
    return out


def _apply_line_col_edits(code: str, edits: list) -> str:
    """Apply `(start=(lineno, col), end=(lineno, col), text)` edits (AST 1-based-line/
    0-based-col positions) to `code`, rightmost-first so earlier offsets stay valid. Mirrors
    `harness.system_builder._apply_line_col_edits`, reimplemented locally to avoid a circular
    import between this module and `harness.system_builder` (which imports this module)."""
    lines = code.splitlines(keepends=True)
    line_offsets = [0]
    for ln in lines:
        line_offsets.append(line_offsets[-1] + len(ln))

    def _offset(pos: tuple) -> "int | None":
        lineno, col = pos
        if lineno is None or col is None or not (1 <= lineno <= len(lines)):
            return None
        return line_offsets[lineno - 1] + col

    resolved = []
    for start, end, text in edits:
        s, e = _offset(start), _offset(end)
        if s is None or e is None or e < s:
            continue
        resolved.append((s, e, text))
    resolved.sort(key=lambda t: t[0], reverse=True)

    result = code
    for s, e, text in resolved:
        result = result[:s] + text + result[e:]
    return result


def _statements_excluding_nested_defs(body: list):
    """Yield every statement/expression reachable from `body` WITHOUT descending into a nested
    function/class/lambda definition -- mirrors
    `harness.system_builder._max_body_index`'s traversal (a nested def's own body isn't
    necessarily executed within this guarded frame)."""
    stack = list(body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _is_split_slash_call(node: "ast.expr | None") -> bool:
    """True for any call chain ending in `.split('/')` (e.g. `path.split('/')`,
    `path.strip('/').split('/')`) -- the intermediate chain is never inspected, only the final
    call's method name and its first (literal `'/'`) argument."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "split"):
        return False
    if not node.args:
        return False
    first = node.args[0]
    return isinstance(first, ast.Constant) and first.value == "/"


def _split_derived_names(body: list) -> "set[str]":
    """The set of simple names assigned (anywhere in `body`, not descending into a nested
    def/class/lambda) from a `.split('/')` call, e.g. `parts = path.strip('/').split('/')` ->
    `{'parts'}`."""
    names: "set[str]" = set()
    for node in _statements_excluding_nested_defs(body):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and _is_split_slash_call(node.value)):
            names.add(node.targets[0].id)
    return names


def _len_call_name(expr: "ast.expr | None") -> "str | None":
    if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) and expr.func.id == "len"
            and len(expr.args) == 1 and not expr.keywords and isinstance(expr.args[0], ast.Name)):
        return expr.args[0].id
    return None


def _int_const(expr: "ast.expr | None") -> "ast.Constant | None":
    if isinstance(expr, ast.Constant) and isinstance(expr.value, int) and not isinstance(expr.value, bool):
        return expr
    return None


def _first_eq_len_guard(test: "ast.expr") -> "tuple[str, ast.Constant, int] | None":
    """If `test` is a simple `len(<Name>) == <int constant>` comparison (either operand
    order), OR the FIRST clause of an `and`-BoolOp is such a comparison, returns
    `(seq_name, n_constant_node, n_value)`. Anything else (a bare `!=`/`<`/`>`/chained
    comparison, a non-`len`/non-constant/non-Name operand, an `or`) -> `None`. Only the
    LEADING `==` clause of a compound `and` guard is ever inspected -- later clauses are never
    touched."""
    first = test
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And) and test.values:
        first = test.values[0]
    if not isinstance(first, ast.Compare) or len(first.ops) != 1 or not isinstance(first.ops[0], ast.Eq):
        return None
    if len(first.comparators) != 1:
        return None
    left, right = first.left, first.comparators[0]

    seq = _len_call_name(left)
    n_node = _int_const(right)
    if seq is not None and n_node is not None:
        return seq, n_node, n_node.value

    seq = _len_call_name(right)
    n_node = _int_const(left)
    if seq is not None and n_node is not None:
        return seq, n_node, n_node.value
    return None


def _subscript_const_index(node: ast.Subscript) -> "int | None":
    idx = node.slice
    if isinstance(idx, ast.Index):  # py<3.9 compatibility shim
        idx = idx.value
    if isinstance(idx, ast.Constant) and isinstance(idx.value, int) and not isinstance(idx.value, bool) and idx.value >= 0:
        return idx.value
    return None


def _max_true_branch_index(body: list, seq_name: str) -> "int | None":
    """The largest constant index `seq_name[M]` reachable anywhere within the guard's own true
    `body` (not descending into a nested def/class/lambda). `None` if no such subscript is
    found."""
    best: "int | None" = None
    for node in _statements_excluding_nested_defs(body):
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id == seq_name):
            idx = _subscript_const_index(node)
            if idx is not None and (best is None or idx > best):
                best = idx
    return best


def repair_endpoint_shape_guards(code: "str | None", spec_text: "str | None") -> str:
    """Deterministic, AST-only, NEVER-RAISING repair (TASK-66, REQ-53): rewrite a
    `len(<split-derived name>) == N` guard (bare, or the leading clause of an `and`-chained
    guard) whose `N` does NOT match any endpoint-segment-count implied by the visible
    `spec_text`'s own URL path templates, to the SMALLEST count that DOES appear in
    `endpoint_segment_counts(spec_text)` AND is provably consistent with the guard's own
    true-branch body (strictly greater than the largest constant index the body reads off that
    same name -- so the rewrite can never make a previously-safe index access go
    out-of-range). Conservative by construction (Tenet 3 -- a false repair is a real
    regression): a no-op whenever `spec_text` yields no parseable endpoint templates, the
    guarded name isn't traceably `.split('/')`-derived within the SAME function, the guard's
    own `N` already matches a spec-derived count, no spec-derived count is consistent with the
    body's own index usage, or the literal's source span can't be located. Returns `code`
    BYTE-IDENTICAL on any parse failure or when no repair applies."""
    if not code:
        return code or ""
    try:
        tree = ast.parse(code)
    except Exception:
        return code

    counts = endpoint_segment_counts(spec_text)
    if not counts:
        return code

    edits = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        split_names = _split_derived_names(func.body)
        if not split_names:
            continue
        for node in _statements_excluding_nested_defs(func.body):
            if not isinstance(node, ast.If):
                continue
            parsed = _first_eq_len_guard(node.test)
            if parsed is None:
                continue
            seq_name, n_node, n_value = parsed
            if seq_name not in split_names:
                continue
            if n_value in counts:
                continue  # guard already consistent with a spec-declared endpoint shape
            max_index = _max_true_branch_index(node.body, seq_name)
            baseline = -1 if max_index is None else max_index
            candidates = sorted(c for c in counts if c > baseline)
            if not candidates:
                continue  # no spec-derived count is safe against the body's own index usage
            new_n = candidates[0]
            start = (getattr(n_node, "lineno", None), getattr(n_node, "col_offset", None))
            end = (getattr(n_node, "end_lineno", None), getattr(n_node, "end_col_offset", None))
            if None in start or None in end:
                continue  # can't safely locate the literal's span -- never guess
            edits.append((start, end, str(new_n)))

    if not edits:
        return code
    return _apply_line_col_edits(code, edits)


def apply_endpoint_shape(modules: "dict[str, str] | None", spec_text: "str | None") -> "dict[str, str]":
    """Map `repair_endpoint_shape_guards` across a `{module_name: code}` dict using endpoint
    templates parsed from `spec_text`. Returns a NEW dict (never mutates `modules`); a module
    whose repair fails to apply cleanly, or that has no matching defect, is left unchanged in
    the returned dict. Never raises."""
    result: "dict[str, str]" = {}
    if not isinstance(modules, dict):
        return result
    for name, code in modules.items():
        try:
            result[name] = repair_endpoint_shape_guards(code, spec_text)
        except Exception:
            result[name] = code
    return result
# #EXT-036-REQ-53 End
