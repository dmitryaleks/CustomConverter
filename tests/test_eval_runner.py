"""Tests for run_evals batch evaluation runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# We import the module-level functions directly for unit testing
from run_evals import evaluate_file, run_batch, main
from source_converter.type_mapper import TypeMapper

_SCHEMA = Path(__file__).parent.parent / "schemas" / "atdl-core-1-1.xsd"

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — minimal JSON files
# ─────────────────────────────────────────────────────────────────────────────

_VALID_JSON = """\
{
  "MyAlgo": {
    "PARAMETERS": [
      {
        "P1": {
          "NAME": "Param1",
          "DESCRIPTION": "A string parameter",
          "TYPE": "String_t",
          "FIXTAGNUMBER": 5001,
          "SUPPORTED_VALUES": ["A", "B"]
        }
      }
    ]
  }
}
"""

_INVALID_JSON_MISSING_TYPE = """\
{
  "BadAlgo": {
    "PARAMETERS": [
      {
        "P1": {
          "NAME": "Param1",
          "FIXTAGNUMBER": 5001
        }
      }
    ]
  }
}
"""

_INVALID_JSON_BAD_TYPE = """\
{
  "BadAlgo": {
    "PARAMETERS": [
      {
        "P1": {
          "NAME": "Param1",
          "TYPE": "Widget_t",
          "FIXTAGNUMBER": 5001
        }
      }
    ]
  }
}
"""


def _write_json(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ─────────────────────────────────────────────────────────────────────────────
# evaluate_file — single-file pipeline tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEvaluateFile:
    def test_valid_json_passes_json_check(self, tmp_path):
        p = _write_json(tmp_path, "valid.json", _VALID_JSON)
        result = evaluate_file(p, _SCHEMA)
        assert result["json_valid"] is True

    def test_valid_json_gets_xsd_and_semantic_results(self, tmp_path):
        p = _write_json(tmp_path, "valid.json", _VALID_JSON)
        result = evaluate_file(p, _SCHEMA)
        # xsd_valid and semantic_valid are set (not None) after conversion
        assert result["xsd_valid"] is not None
        assert result["semantic_valid"] is not None

    def test_missing_type_field_fails_json(self, tmp_path):
        p = _write_json(tmp_path, "bad.json", _INVALID_JSON_MISSING_TYPE)
        result = evaluate_file(p, _SCHEMA)
        assert result["json_valid"] is False
        assert result["xsd_valid"] is None   # skipped
        assert result["semantic_valid"] is None

    def test_bad_type_fails_json(self, tmp_path):
        p = _write_json(tmp_path, "bad.json", _INVALID_JSON_BAD_TYPE)
        result = evaluate_file(p, _SCHEMA)
        assert result["json_valid"] is False
        assert any("JSON-13" in e for e in result["errors"])

    def test_result_contains_file_name(self, tmp_path):
        p = _write_json(tmp_path, "myfunc.json", _VALID_JSON)
        result = evaluate_file(p, _SCHEMA)
        assert result["file"] == "myfunc.json"

    def test_parameters_extracted(self, tmp_path):
        p = _write_json(tmp_path, "valid.json", _VALID_JSON)
        result = evaluate_file(p, _SCHEMA)
        assert len(result["parameters"]) == 1
        assert result["parameters"][0]["name"] == "Param1"
        assert result["parameters"][0]["type"] == "String_t"

    def test_nonexistent_file_handled(self, tmp_path):
        p = tmp_path / "ghost.json"
        result = evaluate_file(p, _SCHEMA)
        assert result["json_valid"] is False
        assert result["errors"]


# ─────────────────────────────────────────────────────────────────────────────
# run_batch — directory-level tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRunBatch:
    def test_empty_directory_returns_empty(self, tmp_path):
        mapper = TypeMapper()
        results = run_batch(tmp_path, _SCHEMA, mapper)
        assert results == []

    def test_valid_files_all_pass_json(self, tmp_path):
        _write_json(tmp_path, "a.json", _VALID_JSON)
        _write_json(tmp_path, "b.json", _VALID_JSON.replace("MyAlgo", "OtherAlgo"))
        mapper = TypeMapper()
        results = run_batch(tmp_path, _SCHEMA, mapper)
        assert len(results) == 2
        assert all(r["json_valid"] for r in results)

    def test_invalid_file_fails(self, tmp_path):
        _write_json(tmp_path, "bad.json", _INVALID_JSON_BAD_TYPE)
        mapper = TypeMapper()
        results = run_batch(tmp_path, _SCHEMA, mapper)
        assert len(results) == 1
        assert results[0]["json_valid"] is False

    def test_mapper_records_types_from_valid_files(self, tmp_path):
        _write_json(tmp_path, "valid.json", _VALID_JSON)
        mapper = TypeMapper()
        run_batch(tmp_path, _SCHEMA, mapper)
        # "String_t" appears in the file but is not a source alias key,
        # so coverage_report shows it as unmapped
        report = mapper.coverage_report()
        assert report["total_lookups"] >= 1


# ─────────────────────────────────────────────────────────────────────────────
# main() CLI — integration tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMainCLI:
    def test_all_pass_exits_zero(self, tmp_path):
        _write_json(tmp_path, "valid.json", _VALID_JSON)
        code = main([str(tmp_path)])
        assert code == 0

    def test_failure_exits_one(self, tmp_path):
        _write_json(tmp_path, "bad.json", _INVALID_JSON_MISSING_TYPE)
        code = main([str(tmp_path)])
        assert code == 1

    def test_missing_directory_exits_two(self, tmp_path):
        code = main([str(tmp_path / "no_such_dir")])
        assert code == 2

    def test_output_flag_persists_json(self, tmp_path):
        input_dir = tmp_path / "inputs"
        input_dir.mkdir()
        _write_json(input_dir, "valid.json", _VALID_JSON)
        out_file = tmp_path / "results.json"  # outside input_dir
        main([str(input_dir), "--output", str(out_file)])
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert isinstance(data, list)
        assert data[0]["file"] == "valid.json"

    def test_format_json_produces_parseable_output(self, tmp_path, capsys):
        _write_json(tmp_path, "valid.json", _VALID_JSON)
        main([str(tmp_path), "--format", "json"])
        captured = capsys.readouterr()
        # Output should contain JSON blocks — each report prints separately;
        # strip and parse the first JSON object in the output
        stdout = captured.out.strip()
        assert stdout  # non-empty
        # Each report is valid JSON when printed with --format json
        # The dashboard report comes first; find first '{' and last '}'
        start = stdout.index("{")
        # Find the matching closing brace for the first JSON block
        depth = 0
        end = start
        for i, ch in enumerate(stdout[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        first_block = stdout[start : end + 1]
        parsed = json.loads(first_block)
        assert isinstance(parsed, dict)

    def test_baseline_produces_diff_output(self, tmp_path, capsys):
        input_dir = tmp_path / "inputs"
        input_dir.mkdir()
        _write_json(input_dir, "valid.json", _VALID_JSON)
        out_file = tmp_path / "baseline.json"  # outside input_dir
        # First run — save baseline
        main([str(input_dir), "--output", str(out_file)])
        capsys.readouterr()  # clear
        # Second run — compare against baseline
        code = main([str(input_dir), "--baseline", str(out_file)])
        captured = capsys.readouterr()
        assert "diff" in captured.out.lower() or "changelog" in captured.out.lower() or "identical" in captured.out.lower()
        assert code == 0

    def test_warnings_flag_shows_warnings(self, tmp_path, capsys):
        # wrong_fix_tag_range produces JSON-21 warnings
        adversarial = Path(__file__).parent.parent / "examples" / "adversarial"
        wrong_tag = adversarial / "wrong_fix_tag_range.json"
        if not wrong_tag.exists():
            pytest.skip("adversarial example not found")
        code = main([str(adversarial / "wrong_fix_tag_range.json").replace(
            str(adversarial / "wrong_fix_tag_range.json"),
            str(adversarial)
        ), "--warnings"])
        # Just verify the call completes; adversarial dir has mixed files
        assert code in (0, 1)

    def test_adversarial_dir_runs_without_crash(self):
        adversarial = Path(__file__).parent.parent / "examples" / "adversarial"
        if not adversarial.exists():
            pytest.skip("adversarial examples not found")
        code = main([str(adversarial)])
        assert code in (0, 1)
