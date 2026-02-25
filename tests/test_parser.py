"""Tests for converter.parser."""

import json
import tempfile
from pathlib import Path

import pytest

from converter.parser import AlgoDef, ParameterDef, parse_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(data: dict, directory: Path) -> Path:
    path = directory / "input.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


MINIMAL_JSON = {
    "MyAlgo": {
        "PARAMETERS": [
            {
                "MyParam1": {
                    "NAME": "myParam1",
                    "DESCRIPTION": "My first parameter",
                    "TYPE": "String_t",
                    "FIXTAGNUMBER": 5001,
                    "SUPPORTED_VALUES": ["A", "B", "C"],
                }
            }
        ]
    }
}

NO_ENUM_JSON = {
    "AnotherAlgo": {
        "PARAMETERS": [
            {
                "P1": {
                    "NAME": "param1",
                    "DESCRIPTION": "",
                    "TYPE": "Int_t",
                    "FIXTAGNUMBER": 5002,
                    "SUPPORTED_VALUES": [],
                }
            }
        ]
    }
}


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

class TestParseJsonHappyPath:
    def test_algo_name(self, tmp_path):
        path = _write_json(MINIMAL_JSON, tmp_path)
        algo = parse_json(path)
        assert algo.name == "MyAlgo"

    def test_parameter_count(self, tmp_path):
        path = _write_json(MINIMAL_JSON, tmp_path)
        algo = parse_json(path)
        assert len(algo.parameters) == 1

    def test_parameter_fields(self, tmp_path):
        path = _write_json(MINIMAL_JSON, tmp_path)
        algo = parse_json(path)
        p = algo.parameters[0]
        assert p.name == "myParam1"
        assert p.description == "My first parameter"
        assert p.type == "String_t"
        assert p.fix_tag == 5001

    def test_supported_values(self, tmp_path):
        path = _write_json(MINIMAL_JSON, tmp_path)
        algo = parse_json(path)
        assert algo.parameters[0].supported_values == ["A", "B", "C"]

    def test_empty_supported_values(self, tmp_path):
        path = _write_json(NO_ENUM_JSON, tmp_path)
        algo = parse_json(path)
        assert algo.parameters[0].supported_values == []

    def test_returns_algo_def(self, tmp_path):
        path = _write_json(MINIMAL_JSON, tmp_path)
        algo = parse_json(path)
        assert isinstance(algo, AlgoDef)
        assert all(isinstance(p, ParameterDef) for p in algo.parameters)

    def test_multiple_parameters(self, tmp_path):
        data = {
            "MultiAlgo": {
                "PARAMETERS": [
                    {"P1": {"NAME": "p1", "TYPE": "Int_t", "FIXTAGNUMBER": 1}},
                    {"P2": {"NAME": "p2", "TYPE": "String_t", "FIXTAGNUMBER": 2}},
                ]
            }
        }
        path = _write_json(data, tmp_path)
        algo = parse_json(path)
        assert len(algo.parameters) == 2
        assert algo.parameters[0].name == "p1"
        assert algo.parameters[1].name == "p2"

    def test_missing_description_defaults_to_empty(self, tmp_path):
        data = {
            "A": {
                "PARAMETERS": [
                    {"P": {"NAME": "p", "TYPE": "Int_t", "FIXTAGNUMBER": 1}}
                ]
            }
        }
        path = _write_json(data, tmp_path)
        algo = parse_json(path)
        assert algo.parameters[0].description == ""

    def test_missing_supported_values_defaults_to_empty_list(self, tmp_path):
        data = {
            "A": {
                "PARAMETERS": [
                    {"P": {"NAME": "p", "TYPE": "Int_t", "FIXTAGNUMBER": 1}}
                ]
            }
        }
        path = _write_json(data, tmp_path)
        algo = parse_json(path)
        assert algo.parameters[0].supported_values == []


# ---------------------------------------------------------------------------
# Error-path tests
# ---------------------------------------------------------------------------

class TestParseJsonErrors:
    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_json(tmp_path / "nonexistent.json")

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not valid json}", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_json(path)

    def test_multiple_top_level_keys(self, tmp_path):
        data = {"AlgoA": {"PARAMETERS": []}, "AlgoB": {"PARAMETERS": []}}
        path = _write_json(data, tmp_path)
        with pytest.raises(ValueError, match="exactly one top-level key"):
            parse_json(path)

    def test_missing_parameters_key(self, tmp_path):
        data = {"MyAlgo": {"OTHER": []}}
        path = _write_json(data, tmp_path)
        with pytest.raises(ValueError, match="PARAMETERS"):
            parse_json(path)

    def test_missing_required_field(self, tmp_path):
        data = {
            "A": {
                "PARAMETERS": [
                    {"P": {"NAME": "p", "FIXTAGNUMBER": 1}}  # missing TYPE
                ]
            }
        }
        path = _write_json(data, tmp_path)
        with pytest.raises(ValueError, match="TYPE"):
            parse_json(path)
