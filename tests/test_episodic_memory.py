"""Offline, deterministic tests for harness/episodic_memory.py (EXT-036 REQ-24 / TASK-32).

No model, no network. Every test uses a scoped temp `store=` path so no test shares
state with another (via `reset()` and/or pytest's `tmp_path` fixture).
"""

from __future__ import annotations

import json

from harness import episodic_memory as em


def test_record_and_load_roundtrip(tmp_path):
    store = tmp_path / "actions.jsonl"

    r1 = em.record_action("build a CSV parser", "user asked to read CSV files", tags=["csv", "build"], store=store)
    r2 = em.record_action("build a JSON parser", "user asked to parse JSON config", tags=["json", "build"], store=store)

    assert r1["seq"] == 0
    assert r2["seq"] == 1
    assert r1["action"] == "build a CSV parser"
    assert r1["rationale"] == "user asked to read CSV files"
    assert r1["tags"] == ["csv", "build"]

    loaded = em.load_actions(store=store)
    assert len(loaded) == 2
    assert loaded[0]["action"] == "build a CSV parser"
    assert loaded[1]["action"] == "build a JSON parser"


def test_recall_similar_exact_rank_order(tmp_path):
    store = tmp_path / "actions.jsonl"

    em.record_action(
        "build a CSV parser", "user asked to read CSV files", tags=["csv", "build"], store=store
    )
    em.record_action(
        "build a JSON parser", "user asked to parse JSON config", tags=["json", "build"], store=store
    )
    em.record_action(
        "fix a bug in the CSV parser", "user reported CSV parsing crash", tags=["csv", "fix"], store=store
    )

    results = em.recall_similar("build a CSV parser", store=store)

    # Hand-computed Jaccard ranking (see TASK-32 test design): the exact original
    # sentence scores highest, the same-verb different-domain action is second, the
    # same-domain different-verb action is third.
    assert [r["action"] for r in results] == [
        "build a CSV parser",
        "build a JSON parser",
        "fix a bug in the CSV parser",
    ]
    # Scores must be strictly descending (a genuine ranking, not a tie/coincidence).
    scored = [em._score(em._tokenize("build a CSV parser"), set(), r) for r in results]
    assert scored[0] > scored[1] > scored[2]


def test_recall_similar_tag_filter_narrows(tmp_path):
    store = tmp_path / "actions.jsonl"

    em.record_action("build a CSV parser", "user asked to read CSV files", tags=["csv", "build"], store=store)
    em.record_action("build a JSON parser", "user asked to parse JSON config", tags=["json", "build"], store=store)
    em.record_action("fix a bug in the CSV parser", "user reported CSV parsing crash", tags=["csv", "fix"], store=store)

    results = em.recall_similar("parser", tags=["fix"], store=store)

    assert len(results) == 1
    assert results[0]["action"] == "fix a bug in the CSV parser"


def test_recall_similar_k_limits_count(tmp_path):
    store = tmp_path / "actions.jsonl"

    for i in range(10):
        em.record_action(f"do task {i}", f"because task {i} was requested", tags=["t"], store=store)

    results = em.recall_similar("do task", k=3, store=store)
    assert len(results) == 3


def test_recall_similar_empty_store_and_no_match_return_empty(tmp_path):
    store = tmp_path / "actions.jsonl"

    # Empty/nonexistent store.
    assert em.recall_similar("anything", store=store) == []

    em.record_action("build a CSV parser", "user asked to read CSV files", tags=["csv"], store=store)

    # A query sharing no tokens and no tags with anything in the store.
    assert em.recall_similar("zzz qqq nonexistent gibberish", store=store) == []


def test_recall_similar_ties_broken_by_recency(tmp_path):
    store = tmp_path / "actions.jsonl"

    em.record_action("repeat the deploy", "user asked to deploy again", tags=["deploy"], store=store)
    em.record_action("repeat the deploy", "user asked to deploy again", tags=["deploy"], store=store)

    results = em.recall_similar("repeat the deploy", store=store)
    assert len(results) == 2
    # Identical scores -> the more recently recorded one (higher seq) ranks first.
    assert results[0]["seq"] == 1
    assert results[1]["seq"] == 0


def test_malformed_jsonl_line_skipped(tmp_path):
    store = tmp_path / "actions.jsonl"

    em.record_action("good action one", "good rationale one", tags=["ok"], store=store)
    with open(store, "a", encoding="utf-8") as fh:
        fh.write("{not valid json,,,\n")
        fh.write("42\n")  # valid JSON but not a dict — also skipped
    em.record_action("good action two", "good rationale two", tags=["ok"], store=store)

    loaded = em.load_actions(store=store)
    assert len(loaded) == 2
    assert [r["action"] for r in loaded] == ["good action one", "good action two"]

    # recall_similar must still work fine despite the malformed line.
    results = em.recall_similar("good action", store=store)
    assert len(results) == 2


def test_garbage_input_never_raises(tmp_path):
    store = tmp_path / "actions.jsonl"

    class Unserializable:
        pass

    # record_action with every kind of garbage input.
    rec = em.record_action(None, None, tags=123, outcome=Unserializable(), meta=Unserializable(), store=store)
    assert rec["action"] == ""
    assert rec["rationale"] == ""
    assert rec["tags"] == []

    rec2 = em.record_action(12345, 67.8, tags="single-tag", store=store)
    assert rec2["action"] == "12345"
    assert rec2["tags"] == ["single-tag"]

    # recall_similar with garbage input.
    assert em.recall_similar(None, store=store) == []
    assert em.recall_similar(object(), k="oops", tags=None, store=store) == []
    assert em.recall_similar("action", k=-1, store=store) == []
    assert em.recall_similar("action", tags=object(), store=store) == []

    # load_actions on a directory-shaped (unreadable-as-file) path never raises.
    assert em.load_actions(store=tmp_path) == []


def test_reset_isolates_scoped_stores(tmp_path):
    store_a = tmp_path / "a.jsonl"
    store_b = tmp_path / "b.jsonl"

    em.record_action("action in store A", "rationale A", store=store_a)
    em.record_action("action in store B", "rationale B", store=store_b)

    assert len(em.load_actions(store=store_a)) == 1
    assert len(em.load_actions(store=store_b)) == 1

    em.reset(store=store_a)

    assert em.load_actions(store=store_a) == []
    assert len(em.load_actions(store=store_b)) == 1  # untouched

    # reset on a never-created store is a safe no-op.
    em.reset(store=tmp_path / "never_existed.jsonl")


def test_record_action_write_failure_never_raises(tmp_path, monkeypatch):
    store = tmp_path / "sub" / "actions.jsonl"

    def _boom(*args, **kwargs):
        raise OSError("simulated unwritable path")

    monkeypatch.setattr(em, "open", lambda *a, **k: _boom(), raising=False)
    # Even if the underlying write fails, the function must still return a well-formed
    # record dict rather than raising.
    rec = em.record_action("do a thing", "because reasons", store=store)
    assert rec["action"] == "do a thing"
    assert rec["rationale"] == "because reasons"
