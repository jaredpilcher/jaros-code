"""Offline tests for EXT-036 TASK-58 (REQ-45): deterministic signature-contract repair.

No model/Jetson call anywhere in this file -- pure AST transform, exactly the shape MEASURED in
`.jaros-data/sigcontract_probe.py` on the retry/backoff-lib real-system task.
"""
from harness.signature_contract import (
    apply_signature_contract,
    documented_defaults,
    repair_signature_defaults,
)

# gemma's ACTUAL built retry.py from the MEASURED diagnostic (build_path=free-form, done=False):
GEMMA_RETRY = '''import time
from typing import Callable, Type, Union, Tuple, Any

def retry(times: int, exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]]) -> Callable:
    def decorator(func: Callable) -> Callable:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            for attempt in range(times):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if not isinstance(e, exceptions):
                        raise
                    last_exception = e
                    if attempt < times - 1:
                        time.sleep(1)
            if last_exception:
                raise last_exception
        return wrapper
    return decorator
'''

# The visible spec sentence documents: `retry(times, exceptions=Exception)`
RETRY_SPEC = (
    "Build a decorator library. Define exactly one public function named `retry` with the "
    "signature `retry(times, exceptions=Exception)`. Calling `retry(times, "
    "exceptions=Exception)` returns a DECORATOR, used as `@retry(times=N)`."
)


def _usage_works(code):
    ns = {}
    try:
        exec(code, ns)
        ns["retry"](times=3)
        return True
    except Exception:
        return False


class TestDocumentedDefaults:
    def test_parses_retry_signature(self):
        docs = documented_defaults(RETRY_SPEC)
        assert docs == {"retry": {"exceptions": "Exception"}}

    def test_no_signatures_in_spec(self):
        assert documented_defaults("plain prose with no backticks at all") == {}

    def test_empty_or_none_spec_never_raises(self):
        assert documented_defaults("") == {}
        assert documented_defaults(None) == {}

    def test_backtick_signature_without_default_is_skipped(self):
        # no `=` in the params -> not a documented DEFAULT, so it must not be captured
        assert documented_defaults("call it as `foo(a, b)`") == {}

    def test_malformed_signature_never_raises(self):
        # unparsable param list inside the backticks -- must be skipped, not raise
        assert documented_defaults("see `foo(a=, ===)`") == {}


class TestRepairSignatureDefaults:
    def test_a_repairs_gemma_retry_and_usage_then_works(self):
        docs = documented_defaults(RETRY_SPEC)
        assert not _usage_works(GEMMA_RETRY), "sanity: the unrepaired build must actually fail"
        new_code, changed, notes = repair_signature_defaults(GEMMA_RETRY, docs)
        assert changed is True
        assert any("exceptions=Exception" in n for n in notes)
        assert "=Exception" in new_code
        assert _usage_works(new_code), "repaired retry(times=3) must work"

    def test_b_noop_when_default_already_present(self):
        already_ok = '''def retry(times, exceptions=Exception):
    pass
'''
        docs = documented_defaults(RETRY_SPEC)
        new_code, changed, notes = repair_signature_defaults(already_ok, docs)
        assert changed is False
        assert new_code == already_ok

    def test_c_illegal_insertion_is_skipped_never_raises(self):
        # documented default only for `a`; built `foo(a, b)` -- adding a default to `a` while
        # `b` stays bare would be an illegal Python signature (non-default after default).
        code = '''def foo(a, b):
    return a + b
'''
        docs = documented_defaults("use `foo(a=1)` to call it")
        new_code, changed, notes = repair_signature_defaults(code, docs)
        assert changed is False
        assert new_code == code

    def test_d_undocumented_function_is_untouched(self):
        code = '''def retry(times, exceptions):
    pass

def other(x, y):
    pass
'''
        docs = documented_defaults(RETRY_SPEC)  # only documents `retry`
        new_code, changed, notes = repair_signature_defaults(code, docs)
        assert changed is True
        assert "def other(x, y):" in new_code  # byte-identical for the undocumented function

    def test_unparseable_code_returns_unchanged_with_note(self):
        bad_code = "def broken(:\n"
        docs = documented_defaults(RETRY_SPEC)
        new_code, changed, notes = repair_signature_defaults(bad_code, docs)
        assert changed is False
        assert new_code == bad_code
        assert notes

    def test_no_documented_defaults_is_a_noop(self):
        new_code, changed, notes = repair_signature_defaults(GEMMA_RETRY, {})
        assert changed is False
        assert new_code == GEMMA_RETRY

    def test_never_alters_an_existing_default(self):
        code = '''def retry(times, exceptions=ValueError):
    pass
'''
        docs = documented_defaults(RETRY_SPEC)  # documents exceptions=Exception
        new_code, changed, notes = repair_signature_defaults(code, docs)
        # already has a default (a different one) -- must never be overwritten
        assert changed is False
        assert "exceptions=ValueError" in new_code


class TestApplySignatureContract:
    def test_maps_repair_across_modules_and_returns_new_dict(self):
        modules = {"retry.py": GEMMA_RETRY, "unrelated.py": "def foo():\n    pass\n"}
        new_modules, notes = apply_signature_contract(modules, RETRY_SPEC)
        assert new_modules is not modules  # never mutates the input dict
        assert modules["retry.py"] == GEMMA_RETRY  # original untouched
        assert _usage_works(new_modules["retry.py"])
        assert new_modules["unrelated.py"] == modules["unrelated.py"]
        assert any("retry.py" in n for n in notes)

    def test_no_spec_text_is_a_noop(self):
        modules = {"retry.py": GEMMA_RETRY}
        new_modules, notes = apply_signature_contract(modules, "")
        assert new_modules == modules
        assert notes == []

    def test_empty_modules_never_raises(self):
        new_modules, notes = apply_signature_contract({}, RETRY_SPEC)
        assert new_modules == {}
        assert notes == []

    def test_none_inputs_never_raise(self):
        new_modules, notes = apply_signature_contract(None, None)
        assert new_modules == {}
        assert notes == []
