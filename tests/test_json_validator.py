"""Tests for converter.json_validator and validate_json CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from converter.json_validator import ValidationIssue, validate_data, validate_json, VALID_TYPES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_data(
    algo_name: str = "MyAlgo",
    params: list[dict] | None = None,
) -> dict:
    """Return a minimal valid descriptor dict."""
    if params is None:
        params = [
            {
                "P1": {
                    "NAME": "myParam",
                    "DESCRIPTION": "A parameter",
                    "TYPE": "String_t",
                    "FIXTAGNUMBER": 5001,
                    "SUPPORTED_VALUES": ["A", "B"],
                }
            }
        ]
    return {algo_name: {"PARAMETERS": params}}


def _rule_ids(issues: list[ValidationIssue]) -> list[str]:
    return [i.rule_id for i in issues]


def _errors(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [i for i in issues if i.severity == "error"]


# ---------------------------------------------------------------------------
# JSON-01 — root must be an object
# ---------------------------------------------------------------------------

class TestJSON01:
    def test_root_list_fails(self):
        issues = validate_data([])
        assert "JSON-01" in _rule_ids(issues)

    def test_root_string_fails(self):
        issues = validate_data("hello")
        assert "JSON-01" in _rule_ids(issues)

    def test_root_null_fails(self):
        issues = validate_data(None)
        assert "JSON-01" in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-02 — exactly one top-level key
# ---------------------------------------------------------------------------

class TestJSON02:
    def test_empty_object_fails(self):
        issues = validate_data({})
        assert "JSON-02" in _rule_ids(issues)

    def test_multiple_keys_fails(self):
        issues = validate_data({"AlgoA": {}, "AlgoB": {}})
        assert "JSON-02" in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-03 — algo name must be non-empty string
# ---------------------------------------------------------------------------

class TestJSON03:
    def test_empty_algo_name_fails(self):
        issues = validate_data({"": {"PARAMETERS": []}})
        assert "JSON-03" in _rule_ids(issues)

    def test_whitespace_algo_name_fails(self):
        issues = validate_data({"   ": {"PARAMETERS": []}})
        assert "JSON-03" in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-04 — algo body must be object with PARAMETERS key
# ---------------------------------------------------------------------------

class TestJSON04:
    def test_algo_body_not_dict_fails(self):
        issues = validate_data({"MyAlgo": [1, 2, 3]})
        assert "JSON-04" in _rule_ids(issues)

    def test_missing_parameters_key_fails(self):
        issues = validate_data({"MyAlgo": {"OTHER": []}})
        assert "JSON-04" in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-05 — PARAMETERS must be a list
# ---------------------------------------------------------------------------

class TestJSON05:
    def test_parameters_is_dict_fails(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": {}}})
        assert "JSON-05" in _rule_ids(issues)

    def test_parameters_is_string_fails(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": "bad"}})
        assert "JSON-05" in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-06 — PARAMETERS must not be empty
# ---------------------------------------------------------------------------

class TestJSON06:
    def test_empty_parameters_fails(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": []}})
        assert "JSON-06" in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-07 — each entry must be a single-key dict
# ---------------------------------------------------------------------------

class TestJSON07:
    def test_entry_is_not_dict_fails(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": ["bad"]}})
        assert "JSON-07" in _rule_ids(issues)

    def test_entry_has_multiple_keys_fails(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [{"A": {}, "B": {}}]}
        })
        assert "JSON-07" in _rule_ids(issues)

    def test_entry_has_zero_keys_fails(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": [{}]}})
        assert "JSON-07" in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-08 — parameter body must be a dict
# ---------------------------------------------------------------------------

class TestJSON08:
    def test_param_body_is_list_fails(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": [{"P1": [1, 2]}]}})
        assert "JSON-08" in _rule_ids(issues)

    def test_param_body_is_string_fails(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": [{"P1": "bad"}]}})
        assert "JSON-08" in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-09 / JSON-10 / JSON-11 — required fields
# ---------------------------------------------------------------------------

class TestRequiredFields:
    def _param(self, **overrides):
        base = {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001}
        for k in overrides:
            if overrides[k] is None:
                base.pop(k, None)
            else:
                base[k] = overrides[k]
        return {"MyAlgo": {"PARAMETERS": [{"P": base}]}}

    def test_missing_name_fails(self):
        issues = validate_data(self._param(NAME=None))
        assert "JSON-09" in _rule_ids(issues)

    def test_missing_type_fails(self):
        issues = validate_data(self._param(TYPE=None))
        assert "JSON-10" in _rule_ids(issues)

    def test_missing_fixtagnumber_fails(self):
        issues = validate_data(self._param(FIXTAGNUMBER=None))
        assert "JSON-11" in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-12 — NAME must be non-empty string
# ---------------------------------------------------------------------------

class TestJSON12:
    def test_name_empty_string_fails(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [{"P": {"NAME": "", "TYPE": "String_t", "FIXTAGNUMBER": 5001}}]}
        })
        assert "JSON-12" in _rule_ids(issues)

    def test_name_integer_fails(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [{"P": {"NAME": 123, "TYPE": "String_t", "FIXTAGNUMBER": 5001}}]}
        })
        assert "JSON-12" in _rule_ids(issues)

    def test_name_whitespace_fails(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [{"P": {"NAME": "  ", "TYPE": "String_t", "FIXTAGNUMBER": 5001}}]}
        })
        assert "JSON-12" in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-13 — TYPE must be a valid FIXATDL type
# ---------------------------------------------------------------------------

class TestJSON13:
    def test_unknown_type_fails(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [{"P": {"NAME": "p", "TYPE": "Widget_t", "FIXTAGNUMBER": 5001}}]}
        })
        assert "JSON-13" in _rule_ids(issues)

    def test_type_not_string_fails(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [{"P": {"NAME": "p", "TYPE": 42, "FIXTAGNUMBER": 5001}}]}
        })
        assert "JSON-13" in _rule_ids(issues)

    def test_all_valid_types_accepted(self):
        for t in VALID_TYPES:
            issues = validate_data({
                "MyAlgo": {"PARAMETERS": [{"P": {"NAME": "p", "TYPE": t, "FIXTAGNUMBER": 5001}}]}
            })
            type_errors = [i for i in issues if i.rule_id == "JSON-13"]
            assert not type_errors, f"Type '{t}' was incorrectly rejected"


# ---------------------------------------------------------------------------
# JSON-14 — FIXTAGNUMBER must be a positive integer
# ---------------------------------------------------------------------------

class TestJSON14:
    def test_fixtagnumber_zero_fails(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [{"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 0}}]}
        })
        assert "JSON-14" in _rule_ids(issues)

    def test_fixtagnumber_negative_fails(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [{"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": -1}}]}
        })
        assert "JSON-14" in _rule_ids(issues)

    def test_fixtagnumber_string_fails(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [{"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": "5001"}}]}
        })
        assert "JSON-14" in _rule_ids(issues)

    def test_fixtagnumber_float_fails(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [{"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001.0}}]}
        })
        assert "JSON-14" in _rule_ids(issues)

    def test_fixtagnumber_bool_fails(self):
        # bool is a subclass of int in Python — must be rejected
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [{"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": True}}]}
        })
        assert "JSON-14" in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-15 — NAME uniqueness
# ---------------------------------------------------------------------------

class TestJSON15:
    def test_duplicate_names_fails(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [
                {"P1": {"NAME": "myParam", "TYPE": "String_t", "FIXTAGNUMBER": 5001}},
                {"P2": {"NAME": "myParam", "TYPE": "Int_t",    "FIXTAGNUMBER": 5002}},
            ]}
        })
        assert "JSON-15" in _rule_ids(issues)

    def test_unique_names_pass(self):
        issues = validate_data(_make_valid_data(params=[
            {"P1": {"NAME": "alpha", "TYPE": "String_t", "FIXTAGNUMBER": 5001}},
            {"P2": {"NAME": "beta",  "TYPE": "Int_t",    "FIXTAGNUMBER": 5002}},
        ]))
        assert "JSON-15" not in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-16 — FIXTAGNUMBER uniqueness
# ---------------------------------------------------------------------------

class TestJSON16:
    def test_duplicate_fixtagnumbers_fails(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [
                {"P1": {"NAME": "alpha", "TYPE": "String_t", "FIXTAGNUMBER": 5001}},
                {"P2": {"NAME": "beta",  "TYPE": "Int_t",    "FIXTAGNUMBER": 5001}},
            ]}
        })
        assert "JSON-16" in _rule_ids(issues)

    def test_unique_tags_pass(self):
        issues = validate_data(_make_valid_data(params=[
            {"P1": {"NAME": "alpha", "TYPE": "String_t", "FIXTAGNUMBER": 5001}},
            {"P2": {"NAME": "beta",  "TYPE": "Int_t",    "FIXTAGNUMBER": 5002}},
        ]))
        assert "JSON-16" not in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-17 — DESCRIPTION must be a string
# ---------------------------------------------------------------------------

class TestJSON17:
    def test_description_integer_fails(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [
                {"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001, "DESCRIPTION": 42}}
            ]}
        })
        assert "JSON-17" in _rule_ids(issues)

    def test_description_string_passes(self):
        issues = validate_data(_make_valid_data())
        assert "JSON-17" not in _rule_ids(issues)

    def test_description_absent_passes(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [
                {"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001}}
            ]}
        })
        assert "JSON-17" not in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-18 / JSON-19 — SUPPORTED_VALUES
# ---------------------------------------------------------------------------

class TestSupportedValues:
    def test_supported_values_not_list_fails(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [
                {"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001,
                       "SUPPORTED_VALUES": "A,B"}}
            ]}
        })
        assert "JSON-18" in _rule_ids(issues)

    def test_supported_values_empty_item_fails(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [
                {"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001,
                       "SUPPORTED_VALUES": ["A", ""]}}
            ]}
        })
        assert "JSON-19" in _rule_ids(issues)

    def test_supported_values_non_string_item_fails(self):
        issues = validate_data({
            "MyAlgo": {"PARAMETERS": [
                {"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001,
                       "SUPPORTED_VALUES": ["A", 99]}}
            ]}
        })
        assert "JSON-19" in _rule_ids(issues)

    def test_valid_supported_values_passes(self):
        issues = validate_data(_make_valid_data())
        sv_issues = [i for i in issues if i.rule_id in ("JSON-18", "JSON-19")]
        assert not sv_issues


# ---------------------------------------------------------------------------
# Happy path — valid descriptors
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_minimal_valid_descriptor(self):
        data = {
            "MyAlgo": {"PARAMETERS": [
                {"P1": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001}}
            ]}
        }
        assert validate_data(data) == []

    def test_full_valid_descriptor_no_issues(self):
        assert validate_data(_make_valid_data()) == []

    def test_multiple_params_valid(self):
        issues = validate_data(_make_valid_data(params=[
            {"P1": {"NAME": "alpha", "TYPE": "String_t",  "FIXTAGNUMBER": 5001}},
            {"P2": {"NAME": "beta",  "TYPE": "Int_t",     "FIXTAGNUMBER": 5002}},
            {"P3": {"NAME": "gamma", "TYPE": "Boolean_t", "FIXTAGNUMBER": 5003}},
        ]))
        assert issues == []

    def test_stealth_descriptor_valid(self):
        """The STEALTH sample file must produce zero issues."""
        stealth = Path(__file__).parent.parent / "stealth.json"
        if stealth.exists():
            issues = validate_json(stealth)
            assert issues == [], [i.message for i in issues]


# ---------------------------------------------------------------------------
# validate_json() — file-based
# ---------------------------------------------------------------------------

class TestValidateJsonFile:
    def test_valid_file_returns_empty_list(self, tmp_path: Path):
        f = tmp_path / "valid.json"
        f.write_text(json.dumps(_make_valid_data()), encoding="utf-8")
        assert validate_json(f) == []

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            validate_json(Path("nonexistent_file_xyz.json"))

    def test_invalid_json_raises(self, tmp_path: Path):
        f = tmp_path / "bad.json"
        f.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON"):
            validate_json(f)


# ---------------------------------------------------------------------------
# CLI — validate_json.py
# ---------------------------------------------------------------------------

class TestCli:
    def _write(self, tmp_path: Path, data: dict) -> Path:
        f = tmp_path / "input.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        return f

    def test_valid_file_exit_0(self, tmp_path: Path):
        from validate_json import main
        f = self._write(tmp_path, _make_valid_data())
        assert main([str(f)]) == 0

    def test_invalid_file_exit_1(self, tmp_path: Path):
        from validate_json import main
        f = self._write(tmp_path, {"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "Widget_t", "FIXTAGNUMBER": 5001}}
        ]}})
        assert main([str(f)]) == 1

    def test_file_not_found_exit_2(self):
        from validate_json import main
        assert main(["nonexistent_xyz.json"]) == 2

    def test_json_output_format(self, tmp_path: Path, capsys):
        from validate_json import main
        f = self._write(tmp_path, {"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "BadType_t", "FIXTAGNUMBER": 5001}}
        ]}})
        main([str(f), "--format", "json"])
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert isinstance(parsed, list)
        assert any(item["rule_id"] == "JSON-13" for item in parsed)

    def test_quiet_suppresses_output(self, tmp_path: Path, capsys):
        from validate_json import main
        f = self._write(tmp_path, {"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "Bad_t", "FIXTAGNUMBER": 5001}}
        ]}})
        main([str(f), "--quiet"])
        out, err = capsys.readouterr()
        assert out == ""
        assert err == ""

    def test_text_output_valid_file_says_passed(self, tmp_path: Path, capsys):
        from validate_json import main
        f = self._write(tmp_path, _make_valid_data())
        main([str(f)])
        out = capsys.readouterr().out
        assert "Validation passed" in out


# ---------------------------------------------------------------------------
# JSON-20 — NAME must match FIXATDL identifier pattern
# ---------------------------------------------------------------------------

class TestJSON20:
    def _param(self, name: str) -> dict:
        return {"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": name, "TYPE": "String_t", "FIXTAGNUMBER": 5001}}
        ]}}

    def test_name_starting_with_digit_fails(self):
        issues = validate_data(self._param("1param"))
        assert "JSON-20" in _rule_ids(issues)

    def test_name_with_space_fails(self):
        issues = validate_data(self._param("my param"))
        assert "JSON-20" in _rule_ids(issues)

    def test_name_with_hyphen_fails(self):
        issues = validate_data(self._param("my-param"))
        assert "JSON-20" in _rule_ids(issues)

    def test_name_with_dot_fails(self):
        issues = validate_data(self._param("my.param"))
        assert "JSON-20" in _rule_ids(issues)

    def test_name_underscore_only_fails(self):
        # underscore is not a letter — fails because it doesn't start with [A-Za-z]
        issues = validate_data(self._param("_param"))
        assert "JSON-20" in _rule_ids(issues)

    def test_valid_simple_name_passes(self):
        issues = validate_data(self._param("myParam"))
        assert "JSON-20" not in _rule_ids(issues)

    def test_valid_name_with_digits_and_underscores_passes(self):
        issues = validate_data(self._param("Param1_ABC"))
        assert "JSON-20" not in _rule_ids(issues)

    def test_single_letter_name_passes(self):
        issues = validate_data(self._param("p"))
        assert "JSON-20" not in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-21 — FIXTAGNUMBER in standard FIX range produces a warning
# ---------------------------------------------------------------------------

class TestJSON21:
    def _param(self, tag: int) -> dict:
        return {"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": tag}}
        ]}}

    def test_tag_in_standard_range_warns(self):
        issues = validate_data(self._param(100))
        warnings = [i for i in issues if i.rule_id == "JSON-21"]
        assert warnings, "Expected a JSON-21 warning for tag 100"
        assert warnings[0].severity == "warning"

    def test_tag_4999_warns(self):
        issues = validate_data(self._param(4999))
        assert "JSON-21" in _rule_ids(issues)

    def test_tag_5000_no_warning(self):
        issues = validate_data(self._param(5000))
        assert "JSON-21" not in _rule_ids(issues)

    def test_tag_5001_no_warning(self):
        issues = validate_data(self._param(5001))
        assert "JSON-21" not in _rule_ids(issues)

    def test_standard_tag_is_warning_not_error(self):
        issues = validate_data(self._param(1))
        errors = _errors(issues)
        assert not any(i.rule_id == "JSON-21" for i in errors), \
            "JSON-21 must be a warning, not an error"

    def test_standard_tag_does_not_change_exit_code(self, tmp_path: Path):
        from validate_json import main
        f = tmp_path / "t.json"
        f.write_text(json.dumps(self._param(100)), encoding="utf-8")
        # Only warnings → exit 0 (not exit 1)
        assert main([str(f)]) == 0


# ---------------------------------------------------------------------------
# JSON-22 — SUPPORTED_VALUES items must be unique within a parameter
# ---------------------------------------------------------------------------

class TestJSON22:
    def test_duplicate_supported_value_fails(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001,
                   "SUPPORTED_VALUES": ["A", "B", "A"]}}
        ]}})
        assert "JSON-22" in _rule_ids(issues)

    def test_all_duplicate_supported_values_fail(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001,
                   "SUPPORTED_VALUES": ["X", "X"]}}
        ]}})
        assert "JSON-22" in _rule_ids(issues)

    def test_unique_supported_values_pass(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001,
                   "SUPPORTED_VALUES": ["A", "B", "C"]}}
        ]}})
        assert "JSON-22" not in _rule_ids(issues)

    def test_single_supported_value_passes(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001,
                   "SUPPORTED_VALUES": ["Only"]}}
        ]}})
        assert "JSON-22" not in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-23 — Boolean_t SUPPORTED_VALUES must have 0 or 2 entries
# ---------------------------------------------------------------------------

class TestJSON23:
    def _bool_param(self, sv) -> dict:
        body: dict = {"NAME": "flag", "TYPE": "Boolean_t", "FIXTAGNUMBER": 5001}
        if sv is not None:
            body["SUPPORTED_VALUES"] = sv
        return {"MyAlgo": {"PARAMETERS": [{"P": body}]}}

    def test_boolean_one_supported_value_fails(self):
        issues = validate_data(self._bool_param(["Y"]))
        assert "JSON-23" in _rule_ids(issues)

    def test_boolean_three_supported_values_fails(self):
        issues = validate_data(self._bool_param(["Y", "N", "X"]))
        assert "JSON-23" in _rule_ids(issues)

    def test_boolean_zero_supported_values_passes(self):
        issues = validate_data(self._bool_param(None))
        assert "JSON-23" not in _rule_ids(issues)

    def test_boolean_two_supported_values_passes(self):
        issues = validate_data(self._bool_param(["Y", "N"]))
        assert "JSON-23" not in _rule_ids(issues)

    def test_non_boolean_type_not_constrained(self):
        # String_t with 3 SUPPORTED_VALUES must NOT trigger JSON-23
        issues = validate_data({"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001,
                   "SUPPORTED_VALUES": ["A", "B", "C"]}}
        ]}})
        assert "JSON-23" not in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-24 — Char_t / MultipleCharValue_t SUPPORTED_VALUES must be single chars
# ---------------------------------------------------------------------------

class TestJSON24:
    def test_char_t_multi_char_entry_fails(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "Char_t", "FIXTAGNUMBER": 5001,
                   "SUPPORTED_VALUES": ["AB"]}}
        ]}})
        assert "JSON-24" in _rule_ids(issues)

    def test_multiple_char_value_t_multi_char_entry_fails(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "MultipleCharValue_t", "FIXTAGNUMBER": 5001,
                   "SUPPORTED_VALUES": ["ABC", "D"]}}
        ]}})
        assert "JSON-24" in _rule_ids(issues)

    def test_char_t_single_char_entries_pass(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "Char_t", "FIXTAGNUMBER": 5001,
                   "SUPPORTED_VALUES": ["A", "B", "C"]}}
        ]}})
        assert "JSON-24" not in _rule_ids(issues)

    def test_string_t_multi_char_entry_not_flagged(self):
        # JSON-24 only applies to Char_t / MultipleCharValue_t
        issues = validate_data({"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001,
                   "SUPPORTED_VALUES": ["LONG_VALUE"]}}
        ]}})
        assert "JSON-24" not in _rule_ids(issues)


# ---------------------------------------------------------------------------
# JSON-25 — unrecognised parameter body fields produce a warning
# ---------------------------------------------------------------------------

class TestJSON25:
    def test_unknown_field_warns(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001,
                   "EXTRA_FIELD": "unexpected"}}
        ]}})
        warnings = [i for i in issues if i.rule_id == "JSON-25"]
        assert warnings, "Expected a JSON-25 warning for unknown field"
        assert warnings[0].severity == "warning"
        assert "EXTRA_FIELD" in warnings[0].message

    def test_multiple_unknown_fields_each_warn(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001,
                   "FOO": 1, "BAR": 2}}
        ]}})
        j25 = [i for i in issues if i.rule_id == "JSON-25"]
        assert len(j25) == 2

    def test_all_known_fields_no_warning(self):
        issues = validate_data({"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001,
                   "DESCRIPTION": "desc", "SUPPORTED_VALUES": ["A"]}}
        ]}})
        assert "JSON-25" not in _rule_ids(issues)

    def test_unknown_field_does_not_change_exit_code(self, tmp_path: Path):
        from validate_json import main
        f = tmp_path / "t.json"
        f.write_text(json.dumps({"MyAlgo": {"PARAMETERS": [
            {"P": {"NAME": "p", "TYPE": "String_t", "FIXTAGNUMBER": 5001,
                   "UNKNOWN": "val"}}
        ]}}), encoding="utf-8")
        # Only warnings → exit 0
        assert main([str(f)]) == 0
