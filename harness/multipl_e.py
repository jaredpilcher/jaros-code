"""Real multi-language benchmark adapter: MultiPL-E (EXT-005 / REQ-5).

MultiPL-E translates the HumanEval problems into ~18 languages. This is the honest
*multi-language* bar — far beyond a hand-written JS toy. We run the languages whose
toolchain is present locally; JavaScript (node) is wired here. Each problem becomes the
same isolated, exit-code-honest Task the rest of the harness uses.

Program assembly (JS): the model produces a COMPLETE `solution.js` (the prompt's
signature + docstring with a filled body); `run.js` evals `solution.js + tests.js`
together so the test harness's bare function reference resolves in one scope — exactly
MultiPL-E's "prompt + completion + tests" program, run with `node`.

Datasets are NOT vendored. Place the parquet at
`evals/benchmarks/multipl-e/humaneval-<lang>.parquet` (from HuggingFace
`nuprl/MultiPL-E`). Absent → the runner says so, never a silent pass (Tenet 3).
"""

from __future__ import annotations

from pathlib import Path

from harness.eval_runner import Task, run_task_list

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "evals" / "benchmarks" / "multipl-e"
MULTIPLE_TIER = 5  # multi-language external bar sits above single-language HumanEval

# run.js evals the complete solution and the test harness in one scope so the test's
# bare `candidate = <fn>` reference resolves to the function solution.js declares.
_JS_RUNNER = (
    "const fs = require('fs');\n"
    "const program = fs.readFileSync('solution.js','utf8') + '\\n' "
    "+ fs.readFileSync('tests.js','utf8');\n"
    "eval(program);\n"
)

_LANGS = {
    "js": {"ext": "js", "test_cmd": "node run.js", "stub": "\n  return undefined;\n}\n",
           "runner_name": "run.js", "runner": _JS_RUNNER},
}


def _read_problems(lang: str) -> list[dict]:
    import pyarrow.parquet as pq  # available locally; never installed by the harness
    path = BENCH / f"humaneval-{lang}.parquet"
    if not path.is_file():
        raise FileNotFoundError(
            f"MultiPL-E humaneval-{lang} not found at {path}. Obtain it from HuggingFace "
            f"nuprl/MultiPL-E (humaneval-{lang}/test-00000-of-00001.parquet)."
        )
    return pq.read_table(str(path)).to_pylist()


def problem_to_task(p: dict, lang: str) -> Task:
    cfg = _LANGS[lang]
    ext = cfg["ext"]
    solution = p["prompt"] + cfg["stub"]            # complete-but-wrong seed file
    return Task(
        id=f"mple_{lang}_{p['name']}",
        instruction=(
            f"Complete the {lang} function so it satisfies its docstring and passes the "
            "tests. Keep the given signature and function name; replace the placeholder "
            "body with a correct implementation. Output the complete file."
        ),
        target=f"solution.{ext}",
        test_cmd=cfg["test_cmd"],
        files={f"solution.{ext}": solution, "tests.js": p["tests"],
               cfg["runner_name"]: cfg["runner"]},
        tier=MULTIPLE_TIER,
    )


def run_multipl_e(lang: str = "js", limit: int | None = 20, max_iters: int = 3,
                  verbose: bool = False, workers: int = 1) -> dict:
    if lang not in _LANGS:
        raise ValueError(f"MultiPL-E lang {lang!r} not wired (have: {list(_LANGS)})")
    problems = _read_problems(lang)
    if limit is not None:
        problems = problems[:limit]
    tasks = [problem_to_task(p, lang) for p in problems]
    return run_task_list(tasks, max_iters=max_iters, verbose=verbose, suite=f"multipl-e-{lang}", workers=workers)
