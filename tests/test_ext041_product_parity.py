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
    byte-identical), row #14 (Project-instruction memory hierarchy), row #13 (Headless +
    piping + structured output, EXT-043: stdin pipe + `--output-format json` + `--max-turns` cap
    + deterministic exit codes, all test-covered; `stream-json` honestly deferred), row #15
    (Custom commands / skills, EXT-046: `.jcode/skills/<name>.md` project+user registry, a
    built-in-always-wins dispatch fallback, `$ARGUMENTS`/`$1`/`$2` argument substitution routed
    through the existing plain-language chain, `/skills` discovery command; argument-hint
    validation/autocomplete and model-invocable auto-suggestion honestly deferred), and row #24
    (Terminal UX polish, EXT-045: streaming tool-event lines from the same Decision-logging
    seam, suppressed under `--output-format json`/non-TTY, `statusline()` + `/statusline`
    toggle, `/help` updated; a live in-flight spinner, `/export`, tab-completion, and themes
    honestly deferred), and row #16 (User-configurable hooks, EXT-047: `.jcode/hooks.json`
    project+user config maps PreToolUse/PostToolUse/SessionStart/Stop to shell commands fired at
    the real `Runtime.apply` gate->executor choke point every tool call passes through, a
    PreToolUse hook exiting non-zero blocks the call, every hook command runs through the same
    gated `shell.exec` path via a hooks-disabled Runtime to prevent recursion, no config is a
    byte-identical no-op; a richer stream/permission UX around hooks honestly deferred), and row
    #17 (Permission rules + modes UX, EXT-048: `.jcode/permissions.json` project+user rules
    (allow/ask/deny, first-match-wins glob) consulted at the same `Runtime.apply` seam STRICTLY
    AFTER the hard gate already accepted the Decision -- a user `allow` rule can never un-block a
    hard-gate refusal (explicit test); an `ask` result prompts interactively in the REPL only and
    safely denies by default headless; `/mode [plan|default|acceptEdits]` wired at the same seam
    -- `plan` withholds every write/shell Decision before the gate/hooks ever see it, `acceptEdits`
    narrowly auto-approves an `ask`-resolving WRITE Decision (never `shell.exec`); `/permissions`
    lists configured rules; no config anywhere is byte-identical), row #18 (External-tool
    extensibility protocol / MCP client, EXT-054 slice 1 + slice 2: two-tier `.jcode/mcp.json`
    config, a bounded stdio JSON-RPC client (`harness/mcp_client.py`) that never hangs on a dead/
    hung/slow server, a `MCPSessionManager` (`harness/mcp_session.py`) that keeps each configured
    server's subprocess ALIVE and reused across calls -- evicting + transparently relaunching a
    crashed session, closing every live session unconditionally at `JcodeCli.on_stop` (no leaked
    subprocess) -- every `tools/call` reaching the host ONLY as a gated `mcp.tool_call` Decision
    whose `validate()` mirrors `shell.exec`'s own denylist on the server's launch command; `/mcp`/
    `/mcp call` for manual invocation PLUS a model-invocable routing step in `_route_plain` that
    lets the same small local router pick a discovered MCP tool for a plain request, gated
    EXACTLY against the live discovered-tool registry so a hallucinated/stale pick can never
    reach the gate (proven never to hijack an ordinary request, and proven the can't-escalate
    invariant holds identically on this path); resources/prompts/notifications/the HTTP/SSE
    transport remain honestly deferred), and row #19 (Subagent
    authoring surface, EXT-050: `.jcode/agents/<name>.md` project+user registry (frontmatter
    `description`/`tools`/`model`), delegation via `/subagent`/a deterministic "delegate to X
    subagent" phrasing routed through the SAME plain-language chain, a `tool_allowlist` at the
    same `Runtime.apply` gate seam consulted ONLY AFTER the hard gate accepts the Decision so it
    can only narrow never widen (explicit test), `/agents` additively lists discovered subagents;
    narrowing `/agent`'s own Runtimes and a model-invocable auto-suggestion honestly deferred), and
    row #22 (Context management for long sessions, EXT-051: `@path`/`@dir/` refs deterministically
    inlined into ANY plain request via `harness/atrefs.py`, reading through the EXISTING gated
    `fs.read`/`fs.list` tools and wired into the SAME `_route_plain` chain a typed request and a
    skill template already share; `/compact` durably folds + persists a session's older turns by
    REUSING the existing `_summarize_turns()`/`condense()` mechanism, not a second summarizer; an
    already-short session is an honest no-op), and row #23 (Background runs surface, EXT-052:
    `jcode --bg` submits a request to run DETACHED via a real `subprocess.Popen` worker
    (`harness/bg_worker.py`) whose unit of work is the UNCHANGED EXT-043 `_run_one_shot` path (any
    host write still passes through the real gated Decision); a durable `JobRecord` persists under
    `.jaros-data/bg_jobs/`; `jcode jobs`/`logs <id>`/`attach <id>`/`stop <id>` (plus `/jobs`/
    `/logs <id>`/`/stop <id>` in the REPL) list/read/stream/cancel a job, `stop` killing only the
    job's recorded pid/tree (mirrors `harness.secure_exec._kill_tree`, never by name); a REPL
    `/attach` is honestly deferred), and row #25 (Install + health story, EXT-053:
    `harness/doctor.py`'s deterministic check battery -- Python version, git/docker presence via a
    bounded `subprocess.run`, `.jaros-data/` writability via a read-only `os.access` query,
    `JCODE_LLM_BACKEND` config sanity, and a bounded probe of the Jetson llama.cpp endpoint reusing
    `harness.llamacpp_client.health` that degrades to an honest WARN (never a hang/raise/FAIL) when
    unreachable -- wired as `/doctor` (REPL) and `jcode doctor`/`--doctor` (headless, deterministic
    exit code); a minimal `pyproject.toml` adds a `jcode` console-script entry point without
    touching `python -m harness.cli`/serve/jcode scripts; auto-update and a signed release artifact
    honestly deferred) are the rows genuinely delivered end-to-end -- these pins were updated
    deliberately alongside each landing, not silently."""
    works = [row.id for row in pp.PARITY_ROWS if row.state == "works"]
    assert works == [12, 13, 14, 15, 16, 17, 18, 19, 20, 22, 23, 24, 25]


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
    # rows #12 (EXT-044), #13 (EXT-043), #14 (EXT-042), #15 (EXT-046), #16 (EXT-047), #17
    # (EXT-048), #18 (EXT-054, MCP client slice 1 + slice 2: persistent connections + a
    # model-invocable routing path, both gated identically to the manual `/mcp call` path), #19
    # (EXT-050), #20 (EXT-049), #22 (EXT-051), #23 (EXT-052), #24 (EXT-045), and #25 (EXT-053) are
    # genuine "works"
    assert result["n_works"] == 13
    assert result["n_partial"] == 0
    assert result["n_partial"] + result["n_missing"] == 3
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
