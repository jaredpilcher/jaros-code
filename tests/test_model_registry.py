"""Tests for harness/model_registry.py — EXT-021 TASK-1 (REQ-1).

Loads the REAL founding profile from .jaros-data/config/models/ and verifies:
  - lookup_by_id returns the gemma profile
  - lookup_by_class returns gemma for its measured classes
  - lookup_by_class returns [] for a class with no evidence
  - default_model() resolves to the founding id
  - a profile is NOT returned for a class it has no entry for (honesty / Tenet 3)
"""
import sys
from pathlib import Path

# Ensure the repo root is on the import path when running standalone
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from harness.model_registry import ModelProfile, ModelRegistry, from_dir, load_registry

# ---------------------------------------------------------------------------
# Path to the real config dir used by all tests below
# ---------------------------------------------------------------------------
_MODELS_DIR = _REPO_ROOT / ".jaros-data" / "config" / "models"

FOUNDING_ID = "gemma-4-e2b"


# ---------------------------------------------------------------------------
# Helper: load from the real config dir
# ---------------------------------------------------------------------------
def _load() -> ModelRegistry:
    return from_dir(_MODELS_DIR)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLoadRegistry:
    def test_registry_loads_without_error(self):
        reg = _load()
        assert reg is not None

    def test_all_profiles_not_empty(self):
        reg = _load()
        profiles = reg.all_profiles()
        assert len(profiles) >= 1, "Expected at least the founding Gemma profile"


class TestLookupById:
    def test_founding_id_returns_profile(self):
        reg = _load()
        profile = reg.lookup_by_id(FOUNDING_ID)
        assert profile is not None, f"Expected profile for id='{FOUNDING_ID}'"
        assert profile.id == FOUNDING_ID

    def test_founding_alias_is_set(self):
        reg = _load()
        profile = reg.lookup_by_id(FOUNDING_ID)
        assert profile.alias == FOUNDING_ID

    def test_unknown_id_returns_none(self):
        reg = _load()
        assert reg.lookup_by_id("nonexistent-model-xyz") is None


class TestLookupByClass:
    def test_standalone_fn_gen_includes_gemma(self):
        reg = _load()
        ids = reg.lookup_by_class("standalone-fn-gen")
        assert FOUNDING_ID in ids, (
            f"Expected '{FOUNDING_ID}' in lookup_by_class('standalone-fn-gen'), got {ids}"
        )

    def test_single_file_repair_includes_gemma(self):
        reg = _load()
        ids = reg.lookup_by_class("single-file-repair")
        assert FOUNDING_ID in ids, (
            f"Expected '{FOUNDING_ID}' in lookup_by_class('single-file-repair'), got {ids}"
        )

    def test_nonexistent_class_returns_empty(self):
        reg = _load()
        ids = reg.lookup_by_class("nonexistent-hard-class")
        assert ids == [], (
            f"Expected [] for 'nonexistent-hard-class', got {ids}"
        )

    def test_class_with_no_evidence_is_not_returned(self):
        """Honesty check (Tenet 3): a class NOT in the profile's `classes` list must
        never be returned, even if the class name sounds plausible."""
        reg = _load()
        # "multi-repo-orchestration" is NOT in Gemma's measured classes
        ids = reg.lookup_by_class("multi-repo-orchestration")
        assert FOUNDING_ID not in ids, (
            f"Profile for '{FOUNDING_ID}' must NOT appear in lookup for a class it has "
            "no measured evidence for — that would violate Tenet 3 (honest profiling)."
        )


class TestDefaultModel:
    def test_default_model_is_founding_id(self):
        reg = _load()
        assert reg.default_model() == FOUNDING_ID

    def test_default_model_has_a_profile(self):
        """The default model id must resolve to an actual loaded profile."""
        reg = _load()
        default_id = reg.default_model()
        assert reg.lookup_by_id(default_id) is not None, (
            f"default_model() returned '{default_id}' but no profile was loaded for it"
        )


class TestModelProfileDataclass:
    def test_from_dict_roundtrip(self):
        data = {
            "id": "test-model",
            "alias": "test-alias",
            "serve": {"gguf": "/path/to/model.gguf", "ctx": 2048, "ngl": 32, "fits_jetson": True},
            "classes": [
                {"name": "standalone-fn-gen", "bar": "HumanEval", "score": "70%", "date": "2026-01-01"}
            ],
            "adaptation": {"tools": ["fs_read_tool"], "agents": [], "config": {}, "prompts": {}},
        }
        profile = ModelProfile.from_dict(data)
        assert profile.id == "test-model"
        assert profile.alias == "test-alias"
        assert profile.handled_class_names() == ["standalone-fn-gen"]

    def test_handled_class_names_empty_when_no_classes(self):
        profile = ModelProfile(id="x", alias="x")
        assert profile.handled_class_names() == []


class TestFromDirWithFakeDir:
    """Offline tests using a temporary in-memory directory structure."""

    def test_skips_underscore_files(self, tmp_path):
        # Write a valid profile and a meta-file
        (tmp_path / "my-model.json").write_text(
            '{"id": "my-model", "alias": "my-model"}', encoding="utf-8"
        )
        (tmp_path / "_roster.json").write_text(
            '{"default": "my-model", "order": ["my-model"]}', encoding="utf-8"
        )
        reg = from_dir(tmp_path)
        assert reg.lookup_by_id("my-model") is not None
        # _roster.json must NOT appear as a profile
        assert reg.lookup_by_id("_roster") is None

    def test_malformed_json_skipped_gracefully(self, tmp_path):
        (tmp_path / "bad.json").write_text("{not valid json", encoding="utf-8")
        (tmp_path / "_roster.json").write_text('{"default": "gemma-4-e2b"}', encoding="utf-8")
        reg = from_dir(tmp_path)
        assert reg.lookup_by_id("bad") is None

    def test_default_falls_back_when_roster_absent(self, tmp_path):
        # No _roster.json in dir
        (tmp_path / "gemma-4-e2b.json").write_text(
            '{"id": "gemma-4-e2b", "alias": "gemma-4-e2b"}', encoding="utf-8"
        )
        reg = from_dir(tmp_path)
        # Fallback default is the hardcoded FALLBACK_DEFAULT = "gemma-4-e2b"
        assert reg.default_model() == "gemma-4-e2b"

    def test_lookup_by_class_honest_with_fake_profiles(self, tmp_path):
        (tmp_path / "model-a.json").write_text(
            '{"id": "model-a", "alias": "model-a", '
            '"classes": [{"name": "cls-x", "bar": "b", "score": "s", "date": "d"}]}',
            encoding="utf-8",
        )
        (tmp_path / "model-b.json").write_text(
            '{"id": "model-b", "alias": "model-b", "classes": []}',
            encoding="utf-8",
        )
        (tmp_path / "_roster.json").write_text(
            '{"default": "model-a"}', encoding="utf-8"
        )
        reg = from_dir(tmp_path)
        assert reg.lookup_by_class("cls-x") == ["model-a"]
        assert reg.lookup_by_class("cls-x") != ["model-b"]
        assert reg.lookup_by_class("cls-not-present") == []


class TestLoadRegistryFunction:
    def test_load_registry_uses_default_dir(self):
        """load_registry() must find the founding profile without arguments."""
        reg = load_registry()
        assert reg.lookup_by_id(FOUNDING_ID) is not None


# #EXT-021-REQ-1 qwen3-4b-thinking-admission Start
class TestQwen3ThinkingProfile:
    """EXT-021 TASK-34 follow-up: qwen3-4b-thinking is admitted and loads correctly.

    The profile carries extra keys not in ModelProfile's schema
    (status, honesty_caveat, security_vet); from_dict must be tolerant of
    these (Tenet 3 — only the measured fields matter for routing, not
    administrative metadata).
    """

    def test_qwen3_thinking_loads_from_real_config(self):
        """from_dir picks up qwen3-4b-thinking profile without crashing."""
        reg = _load()
        profile = reg.lookup_by_id("qwen3-4b-thinking")
        assert profile is not None, (
            "qwen3-4b-thinking profile must load from .jaros-data/config/models/"
        )

    def test_qwen3_thinking_id_and_alias(self):
        """Loaded profile has the correct id and alias."""
        reg = _load()
        profile = reg.lookup_by_id("qwen3-4b-thinking")
        assert profile.id == "qwen3-4b-thinking"
        assert profile.alias == "qwen3-4b-thinking"

    def test_lookup_by_class_hard_multi_step_repo_returns_qwen3(self):
        """lookup_by_class('hard-multi-step-repo') includes qwen3-4b-thinking."""
        reg = _load()
        ids = reg.lookup_by_class("hard-multi-step-repo")
        assert "qwen3-4b-thinking" in ids, (
            f"Expected 'qwen3-4b-thinking' in lookup_by_class('hard-multi-step-repo'), "
            f"got {ids}"
        )

    def test_qwen3_handled_class_names(self):
        """qwen3-4b-thinking profile lists 'hard-multi-step-repo' as handled."""
        reg = _load()
        profile = reg.lookup_by_id("qwen3-4b-thinking")
        assert "hard-multi-step-repo" in profile.handled_class_names()

    def test_gemma_not_in_hard_multi_step_repo(self):
        """Gemma (founding model) is NOT in lookup_by_class('hard-multi-step-repo')
        — it has no measured coverage for the hard class (Tenet 3, honest profiling)."""
        reg = _load()
        ids = reg.lookup_by_class("hard-multi-step-repo")
        assert FOUNDING_ID not in ids, (
            f"'{FOUNDING_ID}' must NOT appear in hard-multi-step-repo lookup "
            "(no measured evidence)"
        )

    def test_profile_tolerates_extra_keys_in_tmp_dir(self, tmp_path):
        """from_dir is tolerant of extra JSON keys (status, honesty_caveat, security_vet)."""
        import json
        profile_data = {
            "id": "qwen3-tol-test",
            "alias": "qwen3-tol-test",
            "serve": {
                "gguf": "/path/Qwen3.gguf",
                "ctx": 16384,
                "ngl": 99,
                "fits_jetson": True,
            },
            "classes": [
                {
                    "name": "hard-multi-step-repo",
                    "bar": "hard tasks (gemma+qwen 0/8)",
                    "score": "1/4",
                    "date": "2026-06-29",
                }
            ],
            "adaptation": {"prompts": "r1-reasoning"},
            # Extra administrative keys NOT in ModelProfile schema:
            "status": "ADMITTED 2026-06-29",
            "honesty_caveat": "1/4 conclusive; 2 inconclusive due to Jetson RAM",
            "security_vet": {
                "source": "unsloth/Qwen3-4B-Thinking-2507-GGUF",
                "license": "Apache-2.0",
                "offline": True,
                "size_gb": 2.5,
            },
        }
        (tmp_path / "qwen3-tol-test.json").write_text(
            json.dumps(profile_data), encoding="utf-8"
        )
        (tmp_path / "_roster.json").write_text(
            '{"default": "qwen3-tol-test", "order": ["qwen3-tol-test"]}',
            encoding="utf-8",
        )
        reg = from_dir(tmp_path)
        profile = reg.lookup_by_id("qwen3-tol-test")
        assert profile is not None, (
            "Profile with extra JSON keys must load without crashing"
        )
        assert profile.id == "qwen3-tol-test"
        assert "hard-multi-step-repo" in profile.handled_class_names()
# #EXT-021-REQ-1 qwen3-4b-thinking-admission End
