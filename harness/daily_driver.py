"""Daily-driver parity-suite runner (EXT-005 / REQ-13).

The Pursuit scoreboard's HEADLINE instrument: a frequency-weighted, CLI-end-to-end
task suite with deterministic oracles and a dev/holdout split (schema + weights in
``evals/daily_driver/README.md``). This module loads the suite, routes each task to
its oracle mechanism, and produces a weighted scorecard.

Fully offline + test-gated (Tenet 3): the ONLY model-calling piece is asking the CLI
a navigate/ops question, and it is injectable as ``answer_fn`` (default stub returns
``""`` so the core runs with no Jetson / model reachable). The pytest-oracle path
reuses the PROVEN isolated ``harness.eval_runner.setup_task`` + ``harness.coding_loop.
fix_loop`` — it is not reimplemented here (Tenet 3: single source of truth).
"""

from __future__ import annotations

import json
import keyword
import re
import tempfile
from pathlib import Path

from harness.report import wilson_interval
from harness.solution_memory import record_verified

ROOT = Path(__file__).resolve().parents[1]
DAILY_ROOT = ROOT / "evals" / "daily_driver"

# #EXT-005-REQ-13 Start
# Category weights (single source of truth — matches evals/daily_driver/README.md table).
CATEGORY_WEIGHTS: dict[str, int] = {
    "navigate": 20,
    "edit": 20,
    "fix": 15,
    "write-tests": 10,
    "refactor": 10,
    "build-module": 10,
    "multi-file": 10,
    "ops": 5,
}

# #EXT-027-REQ-3 Start
# Code-producing categories the flywheel corpus captures a verified solve for, mapped to
# the solution_memory ``problem_class`` label (per EXT-027 REQ-3 — capture only, no recall/
# inject wired anywhere here; injection stays REQ-2-kill-test-gated).
_CAPTURE_PROBLEM_CLASS: dict[str, str] = {
    "edit": "standalone-fn-gen",
    "fix": "standalone-fn-gen",
    "build-module": "standalone-fn-gen",
    "multi-file": "multi-file",
}
# #EXT-027-REQ-3 End


def load_daily_tasks(root: str | Path = DAILY_ROOT, split: str | None = None) -> list[dict]:
    """Load every ``*.json`` task under ``dev/`` and ``holdout/`` (or just ``split``).

    Sorted by ``(category, id)``. Tolerates a missing ``holdout/`` directory (the
    suite starts dev-only).
    """
    root_path = Path(root)
    if not root_path.is_absolute():
        root_path = ROOT / root_path
    splits = [split] if split else ["dev", "holdout"]
    tasks: list[dict] = []
    for sp in splits:
        split_dir = root_path / sp
        if not split_dir.is_dir():
            continue  # tolerate a missing holdout/ dir
        for path in sorted(split_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            tasks.append(data)
    tasks.sort(key=lambda t: (t.get("category", ""), t.get("id", "")))
    return tasks


_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# A small, GENERIC English connector/stop-word list (not task-specific, not derived
# from any file's identifier universe — that would be a leaky "candidate set" and is
# explicitly disallowed). It only strips ordinary prose glue words so a natural-language
# answer like "start and reload" scores the same as "start, reload"; it never removes a
# real identifier the model actually named (e.g. an extra, wrong function name still
# counts against the match).
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "is", "are", "was", "were", "be", "been",
    "being", "to", "of", "in", "on", "at", "by", "with", "that", "which", "who",
    "whom", "this", "these", "those", "it", "its", "as", "for", "from", "just",
    "only", "directly", "call", "calls", "calling", "called", "function",
    "functions", "method", "methods", "answer", "name", "names", "also",
}


def check_answer(answer: str, oracle: dict) -> bool:
    """Deterministic answer-oracle check (navigate/ops answer tasks). Pure."""
    match = oracle.get("match")
    expect = oracle.get("expect")
    if match == "set":
        tokens = {t for t in _TOKEN_RE.findall(answer) if t.lower() not in _STOPWORDS}
        return tokens == set(expect)
    if match == "exact":
        return str(answer).strip().casefold() == str(expect).strip().casefold()
    if match == "regex":
        patterns = expect if isinstance(expect, list) else [expect]
        return all(re.search(p, answer) for p in patterns)
    raise ValueError(f"unknown oracle match type: {match!r}")


def check_state(workdir: str | Path, oracle: dict) -> bool:
    """Deterministic state-oracle check (ops tasks): assert repo/file state in
    ``workdir``. Dispatch is implemented even though no ``ops`` seed task exists yet.

    Supports ``check``:
      - ``file_exists``: ``oracle["path"]`` exists relative to ``workdir``
      - ``file_contains``: ``oracle["path"]`` exists and contains every pattern in
        ``oracle["expect"]`` (str or list of regex patterns)
      - ``cmd_exit0``: run ``oracle["cmd"]`` in ``workdir`` and assert exit code 0
    """
    workdir = Path(workdir)
    check = oracle.get("check")
    if check == "file_exists":
        return (workdir / oracle["path"]).exists()
    if check == "file_contains":
        target = workdir / oracle["path"]
        if not target.is_file():
            return False
        content = target.read_text(encoding="utf-8")
        patterns = oracle["expect"] if isinstance(oracle["expect"], list) else [oracle["expect"]]
        return all(re.search(p, content) for p in patterns)
    if check == "cmd_exit0":
        import subprocess
        res = subprocess.run(oracle["cmd"], shell=True, cwd=str(workdir),
                             capture_output=True, text=True, timeout=oracle.get("timeout", 30))
        return res.returncode == 0
    raise ValueError(f"unknown state oracle check type: {check!r}")


def _default_answer_fn(task: dict) -> str:
    """Offline default: no model/CLI call, so the core runs with no Jetson reachable."""
    return ""


def _write_files(workdir: Path, files: dict) -> None:
    for name, content in files.items():
        (workdir / name).write_text(content, encoding="utf-8")


def _run_build_module_task(task: dict, *, max_iters: int) -> tuple[bool, str]:
    """Route a ``build-module`` task through the proven generative spine
    (``harness.intent_loop.build_from_intent``, EXT-008) and score it by its HELD-OUT
    ``oracle_test`` — the first DISCRIMINATING category (a spec, not a failing test, is
    handed to the model; contrast fix/edit which lean on a given failing test).

    HONESTY (Tenet 3): ``build_from_intent`` builds the solution in its own isolated temp
    dir using only ``intent``/``target``/``func``/``signature``/``test_cmd`` for the
    model-facing steps (the test-writer agent + ``fix_loop``) — ``task["oracle_test"]`` is
    read only by its separate, POST-build ``_run_oracle`` step, which writes the oracle into
    a FRESH temp dir distinct from the build dir and runs it there. The oracle is therefore
    never written into the build dir nor shown to any agent/prompt while building; it is
    written + run only to grade, after the build. ``solved`` is exactly the held-out
    oracle-pass verdict — the same un-gameable metric EXT-008 already proves out.

    Returns ``(solved, built_code)`` -- ``built_code`` is the final module content
    (``IntentResult.code``, EXT-027 REQ-3) so ``run_daily`` can auto-capture it into the
    verified-solution store on a solve, without reaching into ``build_from_intent``'s own
    isolated temp dir (already torn down by the time this returns).
    """
    from harness.intent_loop import build_from_intent
    result = build_from_intent(task, max_iters=max_iters)
    # #EXT-027-REQ-3 Start
    return bool(result.oracle_pass), getattr(result, "code", "") or ""
    # #EXT-027-REQ-3 End


def _find_test_file(files: dict) -> str:
    """Convention used across the harness (``multifile_eval.py``, ``cli.py``): the
    failing-test file is the one whose name starts with ``test`` and ends ``.py``."""
    return next((n for n in files if n.startswith("test") and n.endswith(".py")), "")


def _run_multi_file_task(task: dict, workdir: Path, *, max_iters: int) -> tuple[bool, str, str]:
    """Route a ``multi-file`` task through ``harness.multi_file.multi_file_fix`` (EXT-010,
    incl. the REQ-6 minimal-diff pass) — the discriminating CROSS-FILE class: the fault is
    localized (deterministic import-closure walk) and fixed in a DIFFERENT file than the
    failing test (contrast ``fix``/``edit``, which are single-file via ``fix_loop`` against
    a known ``target``). ``solved`` is exactly whether the run reaches all-green.

    Returns ``(solved, fixed_file_content, original_fixed_file_content)`` -- the latter two
    for EXT-027 REQ-3 capture (fixed content is the code artifact captured; the ORIGINAL,
    pre-fix content of that same file is the "source", mirroring the edit/fix capture
    convention below).
    """
    from harness.multi_file import multi_file_fix
    _write_files(workdir, task.get("files", {}))
    test_file = _find_test_file(task.get("files", {}))
    result = multi_file_fix(str(workdir), task["test_cmd"], task.get("instruction", ""),
                            str(workdir / test_file), max_iters=max_iters, verbose=False)
    solved = bool(result.get("solved"))
    fixed_name = result.get("file")
    code, orig_source = "", ""
    if solved and fixed_name:
        try:
            code = (workdir / fixed_name).read_text(encoding="utf-8")
        except OSError:
            code = ""
        orig_source = task.get("files", {}).get(fixed_name, "")
    return solved, code, orig_source


# ---------------------------------------------------------------------------
# refactor routing (TASK-5): TWO-PLANE -- the model makes ONE narrow grounded
# judgment (extract the (old, new) rename pair); the deterministic, already-built
# harness.refactor.rename_symbol applies it. See _run_refactor_task below for the
# two-part honesty oracle.
# ---------------------------------------------------------------------------

_RENAME_PROMPT = (
    "A refactor instruction describes renaming ONE Python identifier to another.\n"
    "INSTRUCTION: {instruction}\n\n"
    "Reply with ONLY the two identifiers, in the exact form OLD->NEW "
    "(the current name, an arrow, then the new name; no spaces, no other words).\n"
    "Example: _calc->_compute_total"
)

_RENAME_PAIR_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*->\s*([A-Za-z_][A-Za-z0-9_]*)")


def _extract_rename(instruction: str) -> tuple[str, str] | None:
    """MODEL judgment (two-plane): the ONE narrow grounded classification this branch asks
    of the local model -- pull the ``(old, new)`` symbol pair out of a natural-language
    refactor instruction. Uses the same ``build_llm()`` + ``LlmRequest`` call convention as
    ``LocateBoundary`` (``.jaros-data/agents/locate_agent.py``).

    Degeneracy guard: the reply must parse to the strict ``OLD->NEW`` form with two
    DISTINCT, valid, non-keyword Python identifiers; anything else (drift, free text, a
    missing arrow, an unreachable model) is treated as extraction failure. Unlike
    ``LocateBoundary`` this does NOT fall back to a guess -- a wrong guess here would let a
    no-op or bogus rename silently score as attempted, so failure must propagate as
    ``solved=False`` (never a crash), per the two-part oracle below.
    """
    from harness.coding_loop import build_llm
    from jaros.llm import LlmRequest

    prompt = _RENAME_PROMPT.format(instruction=instruction)
    try:
        llm = build_llm()
        raw = llm.complete(LlmRequest(prompt=prompt, params={"temperature": 0.0, "max_tokens": 24})).text
    except Exception:
        return None
    m = _RENAME_PAIR_RE.search(raw or "")
    if not m:
        return None
    old, new = m.group(1), m.group(2)
    if (old == new or not old.isidentifier() or not new.isidentifier()
            or keyword.iskeyword(old) or keyword.iskeyword(new)):
        return None
    return old, new


def _rename_structural_ok(workdir: Path, old: str, new: str, target: str) -> bool:
    """Two-part oracle, part (ii) -- the structural check (Tenet 3 honesty, prevents a
    no-op from passing): the OLD symbol must be GONE as a definition and the NEW symbol
    must be PRESENT as a definition, in ``target``. Reuses the proven AST tool
    ``harness.navigate.find_definition`` rather than a fresh ad-hoc scan."""
    if not target:
        return False
    from harness.navigate import find_definition
    old_defs = [d for d in find_definition(str(workdir), old) if d["file"] == target]
    new_defs = [d for d in find_definition(str(workdir), new) if d["file"] == target]
    return not old_defs and bool(new_defs)


def _run_refactor_task(task: dict, workdir: Path) -> bool:
    """Route a ``refactor`` task through the two planes: (a) MODEL -- ``_extract_rename``
    pulls the ``(old, new)`` pair from ``task["instruction"]``; (b) DETERMINISTIC -- the
    task's ``files`` are written into the isolated ``workdir`` and the already-built,
    test-gated ``harness.refactor.rename_symbol`` (EXT-003 REQ-6) applies the rename.

    TWO-PART ORACLE (Tenet 3 honesty -- a no-op must never score solved): ``solved`` is
    True ONLY IF BOTH (i) ``task["test_cmd"]`` still passes AFTER the rename attempt --
    re-checked HERE independently of ``rename_symbol``'s own internal gate, never trusting
    a single field -- AND (ii) the structural rename actually happened (see
    ``_rename_structural_ok``). If extraction fails (``None``), or the model names a
    symbol that never existed (a no-op: ``rename_symbol`` finds 0 occurrences, the suite
    stays trivially green, but nothing changed), part (ii) catches it and this scores
    ``solved=False`` -- never a crash.
    """
    pair = _extract_rename(task.get("instruction", ""))
    if pair is None:
        return False
    old, new = pair
    _write_files(workdir, task.get("files", {}))
    test_cmd = task.get("test_cmd", "python -m pytest -q")
    from harness.refactor import rename_symbol
    from harness.multi_file import _run
    rename_symbol(str(workdir), old, new, test_cmd)
    ok_behavior, _ = _run(str(workdir), test_cmd)
    ok_structural = _rename_structural_ok(workdir, old, new, task.get("target", ""))
    return ok_behavior and ok_structural


# ---------------------------------------------------------------------------
# write-tests routing (TASK-6): a GENUINE new capability (generating tests for
# given code), not just wiring an existing one. The honest grader is MUTATION
# TESTING -- see _write_tests_oracle_ok below for the two-part honesty oracle.
# ---------------------------------------------------------------------------

_WRITE_TESTS_PROMPT = (
    "Write pytest tests for the following Python code, based on the instruction below.\n\n"
    "INSTRUCTION: {instruction}\n\n"
    "CODE (module(s): {modules}):\n{code}\n\n"
    "Output ONLY Python code: import the needed names with `from <module> import <name>`, "
    "then one or more `def test_...():` functions containing `assert` statements that "
    "verify the described behavior, including typical cases and edge cases. No prose, no "
    "markdown fences, no explanation.\n\nTests:"
)


def _parse_generated_tests(text: str) -> str:
    """Pull runnable test code out of the model reply (mirrors the parsing discipline of
    ``test_writer_agent.parse_tests``): strip markdown fences/chatter, require an actual
    ``def test`` to exist. Empty string means "no usable test code" -- callers must treat
    that as ``solved=False``, never crash."""
    text = re.sub(r"```[\w+-]*", "", text or "").replace("```", "").strip()
    lines = text.split("\n")
    start = 0
    for i, ln in enumerate(lines):
        if ln.startswith(("from ", "import ", "def test")):
            start = i
            break
    code = "\n".join(lines[start:]).strip()
    if "def test" not in code:
        return ""
    return code + "\n"


def _generate_tests(instruction: str, files: dict) -> str:
    """MODEL grain (write-tests): generate pytest test-file CONTENT from the instruction +
    the REFERENCE code ONLY. Mirrors the ``build_llm()``/``LlmRequest`` call convention used
    elsewhere in this module (``_extract_rename``, the build-module test-writer grain).

    HONESTY (Tenet 3): the mutant(s) and any reference test are NEVER shown to the model --
    only ``task["instruction"]`` and the reference ``files`` content go into the prompt. If
    the model is unreachable or emits no usable test code, returns ``""`` (never raises) --
    ``_run_write_tests_task`` treats that as ``solved=False``.
    """
    from harness.coding_loop import build_llm
    from jaros.llm import LlmRequest

    code_blocks = "\n\n".join(f"# {name}\n{content}" for name, content in files.items())
    modules = ", ".join(f"`{Path(name).stem}`" for name in files) or "the code above"
    prompt = _WRITE_TESTS_PROMPT.format(instruction=instruction, code=code_blocks, modules=modules)
    try:
        llm = build_llm()
        raw = llm.complete(LlmRequest(prompt=prompt, params={"temperature": 0.0})).text
    except Exception:
        return ""
    return _parse_generated_tests(raw)


def _write_tests_oracle_ok(task: dict, generated_tests: str) -> bool:
    """MUTATION ORACLE (TASK-6 -- the whole point, Tenet 3 honesty). ``solved`` is True ONLY
    IF BOTH:
      (i) the generated tests PASS when run against the REFERENCE (correct) code -- proves
          the tests are valid, not broken; AND
      (ii) the generated tests KILL EVERY seeded mutant in ``task["mutants"]`` -- for each
           mutant, the mutant version of the corresponding file REPLACES the reference file,
           the SAME generated test runs again, and it MUST FAIL (the tests catch the bug).

    A degenerate ``assert True`` test passes (i) but survives every mutant (fails (ii)) ->
    correctly ``solved=False``. Each run is DETERMINISTIC (reuses ``multi_file._run``, the
    proven tree-kill-safe pytest runner) -- no model-as-judge for grading.
    """
    if not generated_tests.strip():
        return False
    mutants = task.get("mutants") or []
    if not mutants:
        return False  # nothing to prove the tests actually catch a bug
    test_name = task.get("target") or "test_generated.py"
    test_cmd = task.get("test_cmd", "python -m pytest -q")
    files = task.get("files", {})

    from harness.multi_file import _run

    # (i) tests PASS against the reference (correct) code.
    with tempfile.TemporaryDirectory(prefix="jcode-wt-ref-") as d:
        wd = Path(d)
        _write_files(wd, files)
        (wd / test_name).write_text(generated_tests, encoding="utf-8")
        ok_ref, _ = _run(str(wd), test_cmd)
    if not ok_ref:
        return False

    # (ii) tests KILL every seeded mutant (each mutant run MUST fail).
    for mutant in mutants:
        mfile = mutant.get("file")
        if not mfile:
            return False
        with tempfile.TemporaryDirectory(prefix="jcode-wt-mut-") as d:
            wd = Path(d)
            _write_files(wd, files)  # start from the reference set...
            (wd / mfile).write_text(mutant.get("content", ""), encoding="utf-8")  # ...then swap in the mutant
            (wd / test_name).write_text(generated_tests, encoding="utf-8")
            ok_mutant, _ = _run(str(wd), test_cmd)
        if ok_mutant:
            return False  # mutant survived -- the tests didn't catch the bug
    return True


def _run_write_tests_task(task: dict) -> bool:
    """Route a ``write-tests`` task: (a) MODEL generates pytest test content from
    ``task["instruction"]`` + the reference ``files`` (``_generate_tests`` -- never shown a
    mutant or any reference test); (b) DETERMINISTIC grading via the two-part MUTATION
    ORACLE (``_write_tests_oracle_ok``): passes-on-reference AND kills every seeded mutant.
    """
    generated = _generate_tests(task.get("instruction", ""), task.get("files", {}))
    if not generated.strip():
        return False
    return _write_tests_oracle_ok(task, generated)


# ---------------------------------------------------------------------------
# ops routing (TASK-7, the LAST empty category -> 100/100 weighted coverage):
# the model generates the required CONFIG/FILE-STATE artifact CONTENT from the
# instruction; the ALREADY-BUILT check_state oracle (file_exists/file_contains/
# cmd_exit0) grades the REAL produced state. See _run_ops_task below.
# ---------------------------------------------------------------------------

_OPS_PROMPT = (
    "Produce the file described below.\n\n"
    "INSTRUCTION: {instruction}\n\n"
    "Output ONLY the exact file content (no prose, no markdown fences, no explanation)."
)


def _generate_ops_files(task: dict) -> dict[str, str]:
    """MODEL grain (ops): generate the required artifact(s) CONTENT from
    ``task["instruction"]`` ONLY. Mirrors the ``build_llm()``/``LlmRequest`` call
    convention used elsewhere in this module (``_extract_rename``, ``_generate_tests``).

    HONESTY (Tenet 3): the prompt carries ONLY the instruction -- never the oracle's
    ``check``/``path``/``expect`` fields (its exact regex/expected content), so the model
    must produce a genuinely correct artifact, not an echo of the grader.

    Returns a ``{filename: content}`` map to write into the workdir: either the model's own
    JSON filename->content map (multi-file ops), or the raw text written to
    ``task["target"]`` (the common single-file case). Returns ``{}`` (never raises) if the
    model is unreachable or emits nothing usable -- ``_run_ops_task`` treats that as
    ``solved=False``.
    """
    from harness.coding_loop import build_llm
    from jaros.llm import LlmRequest

    prompt = _OPS_PROMPT.format(instruction=task.get("instruction", ""))
    try:
        llm = build_llm()
        raw = llm.complete(LlmRequest(prompt=prompt, params={"temperature": 0.0})).text
    except Exception:
        return {}
    cleaned = re.sub(r"```[\w+-]*", "", raw or "").replace("```", "").strip()
    if not cleaned:
        return {}
    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, dict) and parsed and all(
            isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()):
        return parsed
    target = task.get("target") or "output.txt"
    return {target: cleaned + "\n"}


def _run_ops_task(task: dict, workdir: Path) -> bool:
    """Route an ``ops`` task: (a) MODEL generates the artifact content from
    ``task["instruction"]`` ONLY (``_generate_ops_files``); (b) DETERMINISTIC -- the
    generated file(s) are written into the isolated ``workdir``; (c) GRADE -- the
    already-built ``check_state`` oracle (``file_exists``/``file_contains``/``cmd_exit0``)
    runs against the REAL produced state (never the expected artifact written for the
    model). Any pre-given ``task["files"]`` (fixture inputs the artifact should sit
    alongside) are written first for back-compat, then the model-generated artifact
    overlays them. A missing/unusable model reply scores ``solved=False``, never crashes.
    """
    _write_files(workdir, task.get("files", {}))
    generated = _generate_ops_files(task)
    if not generated:
        return False
    _write_files(workdir, generated)
    oracle = task.get("oracle")
    if not oracle:
        return False
    return check_state(workdir, oracle)


def run_daily(tasks: list[dict], *, answer_fn=None, max_iters: int = 3) -> dict:
    """Run the daily-driver suite, routing each task by its oracle mechanism.

    - ``multi-file`` tasks route through ``harness.multi_file.multi_file_fix`` (checked
      BEFORE the generic pytest branch below so they are never misrouted to the
      single-file ``fix_loop`` path, which has no cross-file localization).
    - ``refactor`` tasks route through ``_run_refactor_task`` (also checked BEFORE the
      generic pytest branch): a model extracts the ``(old, new)`` rename pair, then the
      deterministic ``harness.refactor.rename_symbol`` applies it, graded by the
      two-part oracle (behavior preserved AND the structural rename actually happened).
    - ``write-tests`` tasks route through ``_run_write_tests_task`` (also checked BEFORE
      the generic pytest branch): a model generates test content from the instruction +
      reference code, graded by the MUTATION ORACLE (passes on the reference AND kills
      every seeded mutant -- ``_write_tests_oracle_ok``).
    - pytest-oracle tasks (``test_cmd`` present) reuse the proven isolated
      ``eval_runner.setup_task`` + ``coding_loop.fix_loop`` path.
    - ``ops`` tasks route through ``_run_ops_task`` (checked BEFORE the generic
      ``oracle.type == "state"`` branch below): a model generates the required artifact
      CONTENT from the instruction, the harness writes it, then ``check_state`` grades the
      REAL produced state.
    - answer-oracle tasks (``oracle.type == "answer"``) call ``answer_fn(task) -> str``
      (injectable; default stub returns ``""``) then ``check_answer``.
    - state-oracle tasks (``oracle.type == "state"``, non-``ops``) call ``check_state``
      against pre-given ``files`` -- no model step (back-compat).

    Returns a scorecard: per-category ``{passed,total,rate,wilson}``, the weighted
    headline ``Σ(wᵢ·rateᵢ)/Σwᵢ``, and a dev vs holdout breakdown.
    """
    answer_fn = answer_fn or _default_answer_fn
    from harness.eval_runner import Task, setup_task  # reuse proven pytest path
    from harness.coding_loop import fix_loop

    per_task: list[dict] = []
    for task in tasks:
        oracle = task.get("oracle")
        with tempfile.TemporaryDirectory(prefix=f"jcode-daily-{task['id']}-") as tmp:
            workdir = Path(tmp)
            if task.get("category") == "build-module":
                try:
                    solved, built_code = _run_build_module_task(task, max_iters=max_iters)
                except Exception:  # a single task failure never sinks the suite
                    solved, built_code = False, ""
                # #EXT-027-REQ-3 Start
                # Auto-capture the verified solve into the flywheel corpus (persistence
                # only -- NOT injection; recall_similar/inject_verified_example stay
                # unwired, gated by REQ-2's kill-test). Best-effort: never affects solved.
                if solved:
                    try:
                        record_verified(
                            {"source": task.get("intent", ""),
                             "problem_class": _CAPTURE_PROBLEM_CLASS.get(
                                 task.get("category", ""), "standalone-fn-gen")},
                            built_code,
                        )
                    except Exception:
                        pass
                # #EXT-027-REQ-3 End
            elif task.get("category") == "multi-file":
                # Checked BEFORE the generic test_cmd branch below: multi-file tasks also
                # carry test_cmd (the grader), so without this guard they would misroute
                # into the single-file fix_loop path (no target/cross-file localization).
                try:
                    solved, fixed_code, orig_source = _run_multi_file_task(
                        task, workdir, max_iters=max_iters)
                except Exception:  # a single task failure never sinks the suite
                    solved, fixed_code, orig_source = False, "", ""
                # #EXT-027-REQ-3 Start
                if solved and fixed_code:
                    try:
                        record_verified(
                            {"source": orig_source,
                             "problem_class": _CAPTURE_PROBLEM_CLASS.get(
                                 task.get("category", ""), "multi-file")},
                            fixed_code,
                        )
                    except Exception:
                        pass
                # #EXT-027-REQ-3 End
            elif task.get("category") == "refactor":
                # Checked BEFORE the generic test_cmd branch below: refactor tasks also
                # carry test_cmd (the behavior-preservation grader), so without this guard
                # they would misroute into the single-file fix_loop path (which has no
                # rename-extraction step and no structural oracle).
                try:
                    solved = _run_refactor_task(task, workdir)
                except Exception:  # a single task failure never sinks the suite
                    solved = False
            elif task.get("category") == "write-tests":
                # Checked BEFORE the generic test_cmd branch below: write-tests tasks also
                # carry test_cmd (the mutation-oracle grader), so without this guard they
                # would misroute into the single-file fix_loop path (which has no test-
                # generation step and no mutation oracle).
                try:
                    solved = _run_write_tests_task(task)
                except Exception:  # a single task failure never sinks the suite
                    solved = False
            elif task.get("test_cmd"):
                t = Task(id=task["id"], instruction=task["instruction"],
                         target=task.get("target", ""), test_cmd=task["test_cmd"],
                         files=task.get("files", {}), tier=1)
                target = setup_task(t, workdir)
                try:
                    res = fix_loop(str(target), t.instruction, t.test_cmd,
                                   max_iters=max_iters, cwd=str(workdir), verbose=False)
                    solved = bool(res.success)
                except Exception:  # a single task failure never sinks the suite
                    solved = False
                # #EXT-027-REQ-3 Start
                # Auto-capture verified edit/fix/multi-file solves (read the solved target
                # file's final content BEFORE this temp dir is cleaned up below). Only the
                # code-producing categories the flywheel wants; navigate/ops/write-tests/
                # refactor are out of scope for REQ-3 and are not captured here.
                if solved and task.get("category") in _CAPTURE_PROBLEM_CLASS:
                    try:
                        final_code = target.read_text(encoding="utf-8")
                        record_verified(
                            {"source": task.get("files", {}).get(task.get("target", ""), ""),
                             "problem_class": _CAPTURE_PROBLEM_CLASS[task.get("category")]},
                            final_code,
                        )
                    except Exception:
                        pass
                # #EXT-027-REQ-3 End
            elif task.get("category") == "ops":
                # Checked BEFORE the generic oracle.type=="state" branch below: ops tasks
                # also carry a "state" oracle (the check_state grader), so without this
                # guard they would fall into the back-compat branch that only writes the
                # GIVEN files with no model step -- ops tasks have no pre-given artifact,
                # the model must generate it (TASK-7).
                try:
                    solved = _run_ops_task(task, workdir)
                except Exception:  # a single task failure never sinks the suite
                    solved = False
            elif oracle and oracle.get("type") == "answer":
                _write_files(workdir, task.get("files", {}))
                answer = answer_fn(task)
                solved = check_answer(answer, oracle)
            elif oracle and oracle.get("type") == "state":
                _write_files(workdir, task.get("files", {}))
                solved = check_state(workdir, oracle)
            else:
                raise ValueError(
                    f"task {task.get('id')!r} has neither test_cmd nor a recognized oracle")
        per_task.append({
            "id": task.get("id"),
            "category": task.get("category", "unknown"),
            "split": task.get("split", "dev"),
            "solved": solved,
        })

    per_category: dict[str, dict] = {}
    for row in per_task:
        cat = row["category"]
        stats = per_category.setdefault(cat, {"passed": 0, "total": 0})
        stats["total"] += 1
        if row["solved"]:
            stats["passed"] += 1
    for stats in per_category.values():
        stats["rate"] = round(stats["passed"] / stats["total"], 4) if stats["total"] else 0.0
        lo, hi = wilson_interval(stats["passed"], stats["total"])
        stats["wilson"] = {"low": round(lo, 4), "high": round(hi, 4)}

    weighted_num = sum(CATEGORY_WEIGHTS.get(cat, 0) * stats["rate"]
                       for cat, stats in per_category.items())
    weighted_den = sum(CATEGORY_WEIGHTS.get(cat, 0) for cat in per_category)
    weighted = round(weighted_num / weighted_den, 4) if weighted_den else 0.0

    by_split: dict[str, dict] = {}
    for row in per_task:
        sp = row["split"]
        stats = by_split.setdefault(sp, {"passed": 0, "total": 0})
        stats["total"] += 1
        if row["solved"]:
            stats["passed"] += 1
    for stats in by_split.values():
        stats["rate"] = round(stats["passed"] / stats["total"], 4) if stats["total"] else 0.0

    return {
        "perCategory": per_category,
        "weighted": weighted,
        "bySplit": by_split,
        "perTask": per_task,
        "total": len(per_task),
        "solved": sum(1 for r in per_task if r["solved"]),
    }
# #EXT-005-REQ-13 End
