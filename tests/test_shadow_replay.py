"""Offline, synthetic-transcript tests for the shadow-mode parity replay harness
(EXT-005 REQ-15). No real Claude Code data is used or required -- every transcript
here is authored purely to exercise the harness mechanism."""

import json
from pathlib import Path

from harness.shadow_replay import ShadowTask, load_transcripts, run_shadow_replay

# #EXT-005-REQ-15 Start


def _write_jsonl(path: Path, lines) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")


def test_load_transcripts_parses_and_skips_malformed(tmp_path):
    p = tmp_path / "transcript.jsonl"
    good1 = json.dumps({
        "task_id": "t1",
        "prompt": "write a CLI that prints hello",
        "kind": "build",
        "acceptance": {"entry": "main.py", "checks": [[[], None, "hello"]]},
    })
    good2 = json.dumps({
        "task_id": "t2",
        "prompt": "write a CLI that echoes its argument",
        "kind": "build",
        "acceptance": {"entry": "main.py", "checks": [[["x"], None, "x"]]},
    })
    bad_json = "{this is not valid json"
    missing_field = json.dumps({"task_id": "t3", "kind": "build"})  # no "prompt"
    _write_jsonl(p, [good1, bad_json, "", good2, missing_field])

    tasks = load_transcripts(str(p))

    assert [t.task_id for t in tasks] == ["t1", "t2"]
    assert all(isinstance(t, ShadowTask) for t in tasks)


def test_load_transcripts_missing_file_returns_empty():
    assert load_transcripts("this_file_does_not_exist_xyz123.jsonl") == []


def _stub_write(path_name: str, content: str):
    def _solve(prompt, root):
        (Path(root) / path_name).write_text(content, encoding="utf-8")
        return {"entrypoint": path_name}
    return _solve


def test_run_shadow_replay_scores_build_tasks_and_aggregates():
    tasks = [
        ShadowTask(
            task_id="t1",
            prompt="print hello-marker",
            kind="build",
            acceptance={"entry": "main.py", "checks": [[[], None, "hello-marker"]]},
        ),
        ShadowTask(
            task_id="t2",
            prompt="print goodbye-marker",
            kind="build",
            acceptance={"entry": "main.py", "checks": [[[], None, "goodbye-marker"]]},
        ),
    ]

    correct_solve = _stub_write("main.py", "print('hello-marker')\n")
    wrong_solve = _stub_write("main.py", "print('not-the-right-output')\n")

    def solve_fn(prompt, root):
        if prompt == tasks[0].prompt:
            return correct_solve(prompt, root)
        return wrong_solve(prompt, root)

    result = run_shadow_replay(tasks, solve_fn)

    assert result["total"] == 2
    assert result["passed"] == 1
    assert result["parity_rate"] == 0.5

    by_id = {r["task_id"]: r for r in result["per_task"]}
    assert by_id["t1"]["passed"] is True
    assert by_id["t2"]["passed"] is False
    assert by_id["t1"]["kind"] == "build"

    assert result["per_kind"]["build"]["total"] == 2
    assert result["per_kind"]["build"]["passed"] == 1
    assert result["per_kind"]["build"]["rate"] == 0.5


def test_run_shadow_replay_empty_task_that_writes_nothing_fails_cleanly():
    task = ShadowTask(
        task_id="t-empty",
        prompt="do nothing useful",
        kind="build",
        acceptance={"entry": "main.py", "checks": [[[], None, "anything"]]},
    )

    def solve_fn(prompt, root):
        return None  # no file written -> no resolvable entrypoint

    result = run_shadow_replay([task], solve_fn)
    assert result["passed"] == 0
    assert result["per_task"][0]["passed"] is False


def test_run_shadow_replay_never_raises_when_solve_fn_throws():
    task = ShadowTask(
        task_id="t-boom",
        prompt="trigger a solver crash",
        kind="build",
        acceptance={"entry": "main.py", "checks": [[[], None, "x"]]},
    )

    def bad_solve(prompt, root):
        raise RuntimeError("synthetic solver crash")

    result = run_shadow_replay([task], bad_solve)

    assert result["total"] == 1
    assert result["passed"] == 0
    assert result["per_task"][0]["passed"] is False


def test_run_shadow_replay_empty_task_list_has_no_divide_error():
    result = run_shadow_replay([], lambda prompt, root: None)

    assert result["total"] == 0
    assert result["passed"] == 0
    assert result["parity_rate"] == 0.0
    assert result["per_task"] == []
    assert result["per_kind"] == {}


def test_run_shadow_replay_answer_kind_scores_by_substring():
    tasks = [
        ShadowTask(
            task_id="a1",
            prompt="what is 2+2?",
            kind="answer",
            acceptance={"expect_substring": "4"},
        ),
        ShadowTask(
            task_id="a2",
            prompt="name two of the primary colors",
            kind="answer",
            acceptance={"expect_all": ["red", "blue"]},
        ),
        ShadowTask(
            task_id="a3",
            prompt="name two other primary colors",
            kind="answer",
            acceptance={"expect_all": ["red", "blue"]},
        ),
    ]

    def solve_fn(prompt, root):
        if prompt == tasks[0].prompt:
            return "the answer is 4"
        if prompt == tasks[1].prompt:
            return "red and blue are both primary colors"
        return "yellow is a primary color"  # missing both "red" and "blue" -> should fail

    result = run_shadow_replay(tasks, solve_fn)

    by_id = {r["task_id"]: r for r in result["per_task"]}
    assert by_id["a1"]["passed"] is True
    assert by_id["a2"]["passed"] is True
    assert by_id["a3"]["passed"] is False
    assert result["parity_rate"] == 2 / 3
    assert result["per_kind"]["answer"]["total"] == 3
# #EXT-005-REQ-15 End
