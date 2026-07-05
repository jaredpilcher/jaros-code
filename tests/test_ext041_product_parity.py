"""Tests for the Product-Parity Checklist instrument (EXT-041 REQ-1). Fully deterministic --
no model/gemma calls; the checklist rows are transcribed facts, not agent judgements."""
from dataclasses import replace

import pytest

from harness import product_parity as pp
from harness.product_parity import ProductParityRow


def test_rows_12_to_27_present():
    ids = sorted(row.id for row in pp.PARITY_ROWS)
    assert ids == list(range(12, 28))


def test_all_rows_have_valid_state():
    for row in pp.PARITY_ROWS:
        assert row.state in pp.VALID_STATES, f"row #{row.id} has invalid state {row.state!r}"


def test_all_rows_have_nonempty_fields():
    for row in pp.PARITY_ROWS:
        assert row.feature.strip()
        assert row.current_state.strip()
        assert row.next_lever.strip()


def test_no_row_is_inflated_to_works_today():
    """Honesty guard (Tenet 3): pins the current honest baseline so a future "works" flip is a
    visible diff, not a silent inflation. Row #12 (Sessions continue/resume/fork/name, EXT-044:
    a durable name+timestamp+index session store, `-c`/`-r <id|name>`/`--fork` all test-covered
    end-to-end, resumed context proven via the existing condense()/recent() path, fresh runs
    byte-identical), row #14 (Project-instruction memory hierarchy), and row #13 (Headless +
    piping + structured output, EXT-043: stdin pipe + `--output-format json` + `--max-turns` cap
    + deterministic exit codes, all test-covered; `stream-json` honestly deferred) are the rows
    genuinely delivered end-to-end -- these pins were updated deliberately alongside each
    landing, not silently."""
    works = [row.id for row in pp.PARITY_ROWS if row.state == "works"]
    assert works == [12, 13, 14]


def test_score_aggregate_known_mix():
    rows = [
        ProductParityRow(id=1, feature="a", state="works", current_state="x", next_lever="y"),
        ProductParityRow(id=2, feature="b", state="partial", current_state="x", next_lever="y"),
        ProductParityRow(id=3, feature="c", state="partial", current_state="x", next_lever="y"),
        ProductParityRow(id=4, feature="d", state="missing", current_state="x", next_lever="y"),
    ]
    result = pp.score(rows)
    assert result["n_total"] == 4
    assert result["n_works"] == 1
    assert result["n_partial"] == 2
    assert result["n_missing"] == 1
    # (1*1.0 + 2*0.5 + 1*0.0) / 4 = 2/4 = 50%
    assert result["pct"] == 50.0


def test_score_all_works_is_100_pct():
    rows = [ProductParityRow(id=i, feature=f"f{i}", state="works", current_state="x", next_lever="y")
            for i in range(3)]
    result = pp.score(rows)
    assert result["pct"] == 100.0
    assert result["n_missing"] == 0


def test_score_all_missing_is_0_pct():
    rows = [ProductParityRow(id=i, feature=f"f{i}", state="missing", current_state="x", next_lever="y")
            for i in range(3)]
    result = pp.score(rows)
    assert result["pct"] == 0.0
    assert result["n_works"] == 0


def test_score_default_rows_reflects_honest_current_baseline():
    result = pp.score()
    assert result["n_total"] == 16
    # rows #12 (EXT-044), #13 (EXT-043), and #14 (EXT-042) are genuine "works"
    assert result["n_works"] == 3
    assert result["n_partial"] + result["n_missing"] == 13
    assert 0.0 <= result["pct"] < 100.0


def test_attack_list_surfaces_only_missing_and_partial():
    result = pp.score()
    for row in result["attack_list"]:
        assert row.state in ("missing", "partial")
    # every non-works row must appear somewhere in the ranked attack list
    non_works_ids = {row.id for row in pp.PARITY_ROWS if row.state != "works"}
    attack_ids = {row.id for row in result["attack_list"]}
    assert non_works_ids == attack_ids


def test_attack_list_ranks_missing_before_partial():
    rows = [
        ProductParityRow(id=1, feature="a", state="partial", current_state="x", next_lever="y"),
        ProductParityRow(id=2, feature="b", state="missing", current_state="x", next_lever="y"),
    ]
    result = pp.score(rows)
    assert [row.id for row in result["attack_list"]] == [2, 1]


def test_render_is_nonempty_and_lists_every_feature():
    text = pp.render()
    assert isinstance(text, str) and text.strip()
    for row in pp.PARITY_ROWS:
        assert row.feature in text


def test_render_includes_aggregate_and_last_synced():
    text = pp.render()
    assert "aggregate parity" in text
    assert pp.LAST_SYNCED in text


def test_render_never_raises_on_empty_rows():
    text = pp.render([])
    assert isinstance(text, str)
    assert "aggregate parity" in text


def test_score_never_raises_on_empty_rows():
    result = pp.score([])
    assert result["n_total"] == 0
    assert result["pct"] == 0.0
    assert result["attack_list"] == []


def test_score_never_raises_on_none_rows():
    result = pp.score(None)
    assert result["n_total"] == len(pp.PARITY_ROWS)


def test_score_never_raises_on_malformed_row():
    class Weird:
        pass

    result = pp.score([Weird(), None, 42])
    # malformed rows without a usable .state fall back to "missing" honestly, never raise
    assert result["n_total"] == 3
    assert result["pct"] == 0.0


def test_render_never_raises_on_malformed_row():
    class Weird:
        pass

    text = pp.render([Weird()])
    assert isinstance(text, str)


def test_row_is_immutable_dataclass():
    row = pp.PARITY_ROWS[0]
    original_state = row.state
    with pytest.raises(Exception):
        row.state = "works"  # frozen dataclass -- rows can't be silently mutated
    assert row.state == original_state  # untouched by the failed assignment
    # replace() still works for constructing a modified copy in a test
    copy = replace(row, state="works")
    assert copy.state == "works"


def test_cli_parity_command_renders():
    """/parity wiring: cmd_parity delegates to product_parity.render() and never raises."""
    from harness.cli import JcodeCli

    cli = JcodeCli.__new__(JcodeCli)  # avoid full __init__ (session/model plumbing not needed here)
    out = cli.cmd_parity("")
    assert isinstance(out, str) and out.strip()
    assert "Product-Parity Checklist" in out
