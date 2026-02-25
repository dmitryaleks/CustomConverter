"""Tests for converter.validator."""

from pathlib import Path

import pytest
from lxml import etree

from converter.builder import build_fixatdl, write_fixatdl
from converter.parser import AlgoDef, ParameterDef
from converter.validator import validate

SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "atdl-core-1-1.xsd"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_algo():
    return AlgoDef(
        name="MyAlgo",
        parameters=[
            ParameterDef(
                name="myParam1",
                description="My first parameter",
                type="String_t",
                fix_tag=5001,
                supported_values=["A", "B", "C"],
            )
        ],
    )


def _write_valid_xml(tmp_path: Path) -> Path:
    algo = _make_valid_algo()
    root = build_fixatdl(algo)
    out = tmp_path / "valid.xml"
    write_fixatdl(root, out)
    return out


def _write_invalid_xml(tmp_path: Path) -> Path:
    """Write XML that is well-formed but violates the schema."""
    bad_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Strategies xmlns="http://www.fixprotocol.org/ATDL-1-1/Core">
  <Strategy name="X" wireValue="X" version="1">
    <Parameter name="p" fixTag="1"/>
  </Strategy>
</Strategies>
"""
    out = tmp_path / "invalid.xml"
    out.write_bytes(bad_xml)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestValidate:
    def test_valid_xml_returns_empty_list(self, tmp_path):
        xml_path = _write_valid_xml(tmp_path)
        errors = validate(xml_path, SCHEMA_PATH)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_invalid_xml_returns_errors(self, tmp_path):
        xml_path = _write_invalid_xml(tmp_path)
        errors = validate(xml_path, SCHEMA_PATH)
        assert len(errors) > 0

    def test_errors_are_strings(self, tmp_path):
        xml_path = _write_invalid_xml(tmp_path)
        errors = validate(xml_path, SCHEMA_PATH)
        assert all(isinstance(e, str) for e in errors)

    def test_missing_xml_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="XML file not found"):
            validate(tmp_path / "nonexistent.xml", SCHEMA_PATH)

    def test_missing_schema_raises(self, tmp_path):
        xml_path = _write_valid_xml(tmp_path)
        with pytest.raises(FileNotFoundError, match="Schema file not found"):
            validate(xml_path, tmp_path / "missing.xsd")
