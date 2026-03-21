"""Tests that load each adversarial JSON example from disk and assert
that the expected validator rule IDs are triggered.

Each file in examples/adversarial/ is designed to exercise specific rules
in converter.json_validator.  The tests here document (and enforce) the
exact findings expected from each file.
"""

from __future__ import annotations

from pathlib import Path

from converter.json_validator import ValidationIssue, validate_json

ADVERSARIAL = Path(__file__).parent.parent / "examples" / "adversarial"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rule_ids(issues: list[ValidationIssue]) -> list[str]:
    return [i.rule_id for i in issues]


def _errors(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [i for i in issues if i.severity == "error"]


def _warnings(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [i for i in issues if i.severity == "warning"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAdversarialExamples:

    # ------------------------------------------------------------------
    # wrong_fix_tag_range.json  →  3× JSON-21 warnings, 0 errors
    # ------------------------------------------------------------------

    def test_wrong_fix_tag_range_three_warnings(self):
        issues = validate_json(ADVERSARIAL / "wrong_fix_tag_range.json")
        warnings_21 = [i for i in issues if i.rule_id == "JSON-21"]
        assert len(warnings_21) == 3

    def test_wrong_fix_tag_range_no_errors(self):
        issues = validate_json(ADVERSARIAL / "wrong_fix_tag_range.json")
        assert _errors(issues) == []

    # ------------------------------------------------------------------
    # malformed_names.json  →  3× JSON-20 errors, no other errors
    # ------------------------------------------------------------------

    def test_malformed_names_all_three_flagged(self):
        issues = validate_json(ADVERSARIAL / "malformed_names.json")
        errors_20 = [i for i in issues if i.rule_id == "JSON-20"]
        assert len(errors_20) == 3

    def test_malformed_names_no_other_errors(self):
        issues = validate_json(ADVERSARIAL / "malformed_names.json")
        error_rule_ids = {i.rule_id for i in _errors(issues)}
        assert error_rule_ids == {"JSON-20"}

    # ------------------------------------------------------------------
    # duplicate_parameters.json  →  JSON-15 + JSON-16
    # ------------------------------------------------------------------

    def test_duplicate_parameters_name_conflict(self):
        issues = validate_json(ADVERSARIAL / "duplicate_parameters.json")
        assert any(i.rule_id == "JSON-15" for i in issues)

    def test_duplicate_parameters_tag_conflict(self):
        issues = validate_json(ADVERSARIAL / "duplicate_parameters.json")
        assert any(i.rule_id == "JSON-16" for i in issues)

    # ------------------------------------------------------------------
    # bad_enum_constraints.json  →  JSON-22, JSON-23, JSON-24
    # ------------------------------------------------------------------

    def test_bad_enum_char_t_multichar(self):
        issues = validate_json(ADVERSARIAL / "bad_enum_constraints.json")
        assert any(i.rule_id == "JSON-24" for i in issues)

    def test_bad_enum_boolean_wrong_count(self):
        issues = validate_json(ADVERSARIAL / "bad_enum_constraints.json")
        assert any(i.rule_id == "JSON-23" for i in issues)

    def test_bad_enum_duplicate_value(self):
        issues = validate_json(ADVERSARIAL / "bad_enum_constraints.json")
        assert any(i.rule_id == "JSON-22" for i in issues)

    # ------------------------------------------------------------------
    # unknown_extensions.json  →  3× JSON-25 warnings, 0 errors
    # (DEFAULT_VALUE is now a known field; CATEGORY, DISPLAY_ORDER,
    # DEPRECATED remain unknown)
    # ------------------------------------------------------------------

    def test_unknown_extensions_three_warnings(self):
        issues = validate_json(ADVERSARIAL / "unknown_extensions.json")
        warnings_25 = [i for i in issues if i.rule_id == "JSON-25"]
        assert len(warnings_25) == 3

    def test_unknown_extensions_no_errors(self):
        issues = validate_json(ADVERSARIAL / "unknown_extensions.json")
        assert _errors(issues) == []

    # ------------------------------------------------------------------
    # missing_required_fields.json  →  JSON-09, JSON-10, JSON-11
    # ------------------------------------------------------------------

    def test_missing_name_json09(self):
        issues = validate_json(ADVERSARIAL / "missing_required_fields.json")
        assert any(i.rule_id == "JSON-09" for i in issues)

    def test_missing_type_json10(self):
        issues = validate_json(ADVERSARIAL / "missing_required_fields.json")
        assert any(i.rule_id == "JSON-10" for i in issues)

    def test_missing_tag_json11(self):
        issues = validate_json(ADVERSARIAL / "missing_required_fields.json")
        assert any(i.rule_id == "JSON-11" for i in issues)

    # ------------------------------------------------------------------
    # invalid_types.json  →  3× JSON-13 with bad type names in messages
    # ------------------------------------------------------------------

    def test_invalid_types_three_errors(self):
        issues = validate_json(ADVERSARIAL / "invalid_types.json")
        errors_13 = [i for i in issues if i.rule_id == "JSON-13"]
        assert len(errors_13) == 3

    def test_invalid_types_names_in_messages(self):
        issues = validate_json(ADVERSARIAL / "invalid_types.json")
        messages = " ".join(i.message for i in issues if i.rule_id == "JSON-13")
        assert "Double" in messages
        assert "Integer" in messages
        assert "DateTime" in messages

    # ------------------------------------------------------------------
    # multi_error.json  →  {JSON-13,16,20,21,22,23,25} + both severities
    # ------------------------------------------------------------------

    def test_multi_error_all_rule_ids(self):
        issues = validate_json(ADVERSARIAL / "multi_error.json")
        rule_ids = {i.rule_id for i in issues}
        expected = {"JSON-13", "JSON-16", "JSON-20", "JSON-21", "JSON-22", "JSON-23", "JSON-25"}
        assert expected <= rule_ids

    def test_multi_error_has_both_severities(self):
        issues = validate_json(ADVERSARIAL / "multi_error.json")
        assert any(i.severity == "error" for i in issues)
        assert any(i.severity == "warning" for i in issues)
