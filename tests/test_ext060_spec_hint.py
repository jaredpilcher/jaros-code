"""EXT-060 TASK-18: offline tests for threading `spec_hint` from the real-systems MODIFY driver
into `harness.system_builder.modify_system` (REQ-23) -- the explicitly-flagged follow-up of
EXT-036 REQ-52.

CONTEXT: ``modify_system`` accepts a keyword-only ``spec_hint: str | None = None`` (REQ-52,
already landed) and combines it with ``mod_sentence`` as the spec text its deterministic repair
chain's scaffold detectors (``spec_demands_stdlib_http_service``/``spec_demands_tool_calling_
agent``) inspect. The MEASURED gap this task closes: a bare `mod_sentence` for a real MODIFY task
(e.g. "Add a `PUT /items/<id>` endpoint...") typically does NOT itself contain those protocol
keywords, so without a hint those scaffolds never fire on a real modify task even though they DO
fire on the matching CREATE task's full sentence.

FULLY OFFLINE -- no Jetson/LLM call anywhere. The end-to-end wiring test stubs ``modify_system``
via monkeypatch (never calls the real one); the detector tests call the already-landed pure
detector functions directly on plain strings.
"""

# #EXT-060-REQ-23 Start
from __future__ import annotations

from harness.agent_scaffold import spec_demands_tool_calling_agent
from harness.http_service_scaffold import spec_demands_stdlib_http_service
from harness.real_systems_suite import (
    AGENT_ADD_STEP_GUARD_MODIFY,
    HELPDESK_ADD_STATE_MODIFY,
    INI_DEFAULT_FLAG_MODIFY_TASK,
    INVENTORY_ADD_BACKORDER_MODIFY,
    IRV_ADD_TIE_RULE_MODIFY,
    LOCKOUT_ADMIN_UNLOCK_MODIFY,
    ORDER_ADD_REFUND_MODIFY,
    REAL_SYSTEMS_MODIFY_TASKS,
    REAL_SYSTEMS_TASKS,
    REST_SQLITE_ADD_UPDATE_MODIFY,
    RETRY_BASE_DELAY_MODIFY_TASK,
    SHORTENER_ADD_DELETE_MODIFY,
    TAX_ADD_CAP_MODIFY,
)


# --------------------------------------------------------------------------------------------
# (a) every modify task in the roster carries a non-empty base_sentence
# --------------------------------------------------------------------------------------------

def test_every_modify_task_has_a_nonempty_base_sentence():
    for task in REAL_SYSTEMS_MODIFY_TASKS:
        assert isinstance(task.base_sentence, str), task.name
        assert task.base_sentence.strip(), f"{task.name} has no base_sentence"


def test_base_sentences_are_the_matching_create_tasks_sentences():
    # Sanity-check membership: each modify task's base_sentence is drawn from the CREATE half's
    # own roster of sentences (never a fresh, undeclared spec), i.e. it names a real original
    # build spec rather than an ad hoc string.
    create_sentences = {t.sentence for t in REAL_SYSTEMS_TASKS}
    for task in REAL_SYSTEMS_MODIFY_TASKS:
        assert task.base_sentence in create_sentences, task.name


# --------------------------------------------------------------------------------------------
# (b) the two protocol modifies' combined text (base_sentence + " " + mod_sentence) triggers
# their respective spec detectors -- the concrete gap this task closes.
# --------------------------------------------------------------------------------------------

def test_rest_sqlite_put_modify_combined_text_triggers_http_service_detector():
    base = REST_SQLITE_ADD_UPDATE_MODIFY.base_sentence
    mod = REST_SQLITE_ADD_UPDATE_MODIFY.mod_sentence
    assert base, "REST_SQLITE_ADD_UPDATE_MODIFY must carry a base_sentence"
    combined = base + " " + mod
    assert spec_demands_stdlib_http_service(combined) is True


def test_rest_sqlite_put_modify_bare_mod_sentence_alone_does_not_trigger_the_detector():
    # Proves the gap this task closes: WITHOUT the base_sentence, the scaffold never fires on
    # this real modify task's bare change request.
    mod = REST_SQLITE_ADD_UPDATE_MODIFY.mod_sentence
    assert spec_demands_stdlib_http_service(mod) is False


def test_agent_step_guard_modify_combined_text_triggers_tool_calling_agent_detector():
    base = AGENT_ADD_STEP_GUARD_MODIFY.base_sentence
    mod = AGENT_ADD_STEP_GUARD_MODIFY.mod_sentence
    assert base, "AGENT_ADD_STEP_GUARD_MODIFY must carry a base_sentence"
    combined = base + " " + mod
    assert spec_demands_tool_calling_agent(combined) is True


# --------------------------------------------------------------------------------------------
# (c) the driver passes spec_hint through to modify_system (stubbed via monkeypatch)
# --------------------------------------------------------------------------------------------

def test_driver_passes_base_sentence_as_spec_hint_to_modify_system(monkeypatch):
    import harness.real_systems_suite as suite_mod

    captured = {}

    def _fake_modify_system(modules, mod_sentence, root, *, llm=None, spec_hint=None, **kwargs):
        captured["spec_hint"] = spec_hint
        captured["mod_sentence"] = mod_sentence
        return {"applied": False, "note": "stubbed -- never reaches grading"}

    monkeypatch.setattr(suite_mod, "modify_system", _fake_modify_system)

    rec = suite_mod._run_one_modify_task(
        REST_SQLITE_ADD_UPDATE_MODIFY, llm=object(), python_exe="python")

    assert rec["applied"] is False  # stub never applies -- this test only cares about the kwarg
    assert captured["spec_hint"] == REST_SQLITE_ADD_UPDATE_MODIFY.base_sentence
    assert captured["mod_sentence"] == REST_SQLITE_ADD_UPDATE_MODIFY.mod_sentence


def test_driver_passes_none_spec_hint_when_base_sentence_is_empty(monkeypatch):
    import harness.real_systems_suite as suite_mod
    from harness.real_systems_suite import RealSystemModifyTask

    task_without_base = RealSystemModifyTask(
        name="no-base-sentence-task",
        cls="library-modify",
        start_system={"retry.py": "def retry(): pass\n"},
        mod_sentence="Modify retry.py to do something trivial.",
        oracle_kind="import",
        oracle_spec={"module": "retry", "api_calls": [], "checks": []},
        # base_sentence deliberately left at its "" default
    )

    captured = {}

    def _fake_modify_system(modules, mod_sentence, root, *, llm=None, spec_hint=None, **kwargs):
        captured["spec_hint"] = spec_hint
        return {"applied": False, "note": "stubbed"}

    monkeypatch.setattr(suite_mod, "modify_system", _fake_modify_system)

    suite_mod._run_one_modify_task(task_without_base, llm=object(), python_exe="python")

    assert captured["spec_hint"] is None


# --------------------------------------------------------------------------------------------
# (d) the MODIFY roster is unchanged by this task -- this task only threads an existing field
# through, it never adds/removes a MODIFY roster task. (The CREATE roster's size below reflects
# whatever it is as of REQ-24..30's later additions -- this test only pins the MODIFY half,
# which REQ-23 does not touch.)
# --------------------------------------------------------------------------------------------

def test_roster_size_unchanged():
    # bumped 19 -> 22 -> 26 -> 30 -> 34 -> 38: EXT-060 REQ-28/29/30 (tests/test_ext060_clock_agent_
    # tasks.py) added three more CREATE tasks after this module's own REQ-23 landed, then
    # REQ-31..34 (tests/test_ext060_atlas_wave2_tasks.py), REQ-40..43 (tests/test_ext060_atlas_
    # wave7_tasks.py), REQ-44..47 (tests/test_ext060_atlas_batch4_tasks.py), REQ-48..51
    # (tests/test_ext060_wave8_import_tasks.py), REQ-52..55 (tests/test_ext060_batch5_tasks.py),
    # and REQ-56..59 (tests/test_ext060_batch6_tasks.py) each added four more. The CREATE count is
    # still unchanged by this file. MODIFY bumped 6 -> 11: REQ-35..39
    # (tests/test_ext060_modify_wave2.py) added five more MODIFY tasks, growing the previously
    # lopsided 26-CREATE-vs-6-MODIFY split (now 46-vs-11).
    assert len(REAL_SYSTEMS_TASKS) == 46
    assert len(REAL_SYSTEMS_MODIFY_TASKS) == 11
    names = {t.name for t in REAL_SYSTEMS_MODIFY_TASKS}
    assert names == {
        RETRY_BASE_DELAY_MODIFY_TASK.name,
        INI_DEFAULT_FLAG_MODIFY_TASK.name,
        REST_SQLITE_ADD_UPDATE_MODIFY.name,
        AGENT_ADD_STEP_GUARD_MODIFY.name,
        ORDER_ADD_REFUND_MODIFY.name,
        INVENTORY_ADD_BACKORDER_MODIFY.name,
        HELPDESK_ADD_STATE_MODIFY.name,
        TAX_ADD_CAP_MODIFY.name,
        IRV_ADD_TIE_RULE_MODIFY.name,
        SHORTENER_ADD_DELETE_MODIFY.name,
        LOCKOUT_ADMIN_UNLOCK_MODIFY.name,
    }
# #EXT-060-REQ-23 End
