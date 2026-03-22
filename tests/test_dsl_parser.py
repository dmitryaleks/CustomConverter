"""Tests for source_converter.dsl_parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from source_converter.dsl_parser import (
    DEFAULT_FIELD_MAP,
    FieldCoverage,
    FieldMap,
    parse_dsl,
    parse_dsl_with_coverage,
)

STEALTH_DSL = Path(__file__).parent.parent / "examples" / "dsl" / "stealth_dsl.xml"
IS_DSL = Path(__file__).parent.parent / "examples" / "sourcedsl" / "is_dsl.xml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_xml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test_dsl.xml"
    p.write_text(content, encoding="utf-8")
    return p


_MINIMAL_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<AlgoDef name="TEST">
  <Parameters>
    <Parameter id="MyParam" dataType="string" tag="9001">
      <Description>A test parameter</Description>
    </Parameter>
  </Parameters>
</AlgoDef>
"""

_NAMESPACED_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<AlgoDef xmlns="http://example.com/dsl/1.0" name="NSTEST">
  <Parameters>
    <Parameter id="P1" dataType="string" tag="9001" />
  </Parameters>
</AlgoDef>
"""


# ---------------------------------------------------------------------------
# FieldMap loading
# ---------------------------------------------------------------------------

class TestFieldMapLoading:
    def test_default_loads(self):
        fm = FieldMap()
        assert fm.param_container == "Parameters"

    def test_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            FieldMap(tmp_path / "nonexistent.toml")

    def test_field_expressions_have_required_keys(self):
        fm = FieldMap()
        exprs = fm.field_expressions
        assert "name" in exprs
        assert "type" in exprs
        assert "fix_tag" in exprs


# ---------------------------------------------------------------------------
# Happy path — stealth_dsl.xml
# ---------------------------------------------------------------------------

class TestParseDslHappyPath:
    def test_algo_name(self):
        algo = parse_dsl(STEALTH_DSL)
        assert algo.name == "STEALTH"

    def test_parameter_count(self):
        algo = parse_dsl(STEALTH_DSL)
        assert len(algo.parameters) == 6

    def test_time_type_mapped(self):
        algo = parse_dsl(STEALTH_DSL)
        start = next(p for p in algo.parameters if p.name == "StartTime")
        assert start.type == "UTCTimeOnly_t"

    def test_boolean_type_mapped(self):
        algo = parse_dsl(STEALTH_DSL)
        odd = next(p for p in algo.parameters if p.name == "AllowOddLots")
        assert odd.type == "Boolean_t"

    def test_default_value_time_padded(self):
        # StartTime default "09:30:00" → already full; still "09:30:00"
        algo = parse_dsl(STEALTH_DSL)
        start = next(p for p in algo.parameters if p.name == "StartTime")
        assert start.default_value == "09:30:00"

    def test_percent_default_stripped(self):
        algo = parse_dsl(STEALTH_DSL)
        max_p = next(p for p in algo.parameters if p.name == "MaxPctVolume")
        # "15%" → strip_percent → "15"
        assert max_p.default_value == "15"

    def test_supported_values_extracted(self):
        algo = parse_dsl(STEALTH_DSL)
        urgency = next(p for p in algo.parameters if p.name == "Urgency")
        assert urgency.supported_values == ["Low", "Medium", "High"]

    def test_description_extracted(self):
        algo = parse_dsl(STEALTH_DSL)
        start = next(p for p in algo.parameters if p.name == "StartTime")
        assert "execution window" in start.description

    def test_min_value_parsed(self):
        algo = parse_dsl(IS_DSL)
        risk = next(p for p in algo.parameters if p.name == "RiskAversion")
        assert risk.min_value == "0"

    def test_max_value_parsed(self):
        algo = parse_dsl(IS_DSL)
        risk = next(p for p in algo.parameters if p.name == "RiskAversion")
        assert risk.max_value == "1"

    def test_increment_parsed(self):
        algo = parse_dsl(IS_DSL)
        risk = next(p for p in algo.parameters if p.name == "RiskAversion")
        assert risk.increment == "0.01"

    def test_absent_min_max_increment_is_none(self):
        algo = parse_dsl(IS_DSL)
        # BenchmarkPrice has no minValue/maxValue/increment
        bench = next(p for p in algo.parameters if p.name == "BenchmarkPrice")
        assert bench.min_value is None
        assert bench.max_value is None
        assert bench.increment is None


# ---------------------------------------------------------------------------
# Type mapping
# ---------------------------------------------------------------------------

class TestParseDslTypeMapping:
    def test_unmapped_type_used_as_is(self, tmp_path):
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<AlgoDef name="T">
  <Parameters>
    <Parameter id="P" dataType="String_t" tag="9001" />
  </Parameters>
</AlgoDef>
"""
        path = _write_xml(tmp_path, xml)
        algo = parse_dsl(path)
        # "String_t" is already a FIXATDL type name; map() returns None → use as-is
        assert algo.parameters[0].type == "String_t"

    def test_custom_mapper_used(self, tmp_path):
        from source_converter.type_mapper import TypeMapper
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<AlgoDef name="T">
  <Parameters>
    <Parameter id="P" dataType="time" tag="9001" />
  </Parameters>
</AlgoDef>
"""
        path = _write_xml(tmp_path, xml)
        mapper = TypeMapper()
        algo = parse_dsl(path, type_mapper=mapper)
        assert algo.parameters[0].type == "UTCTimeOnly_t"

    def test_no_mapper_uses_default(self, tmp_path):
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<AlgoDef name="T">
  <Parameters>
    <Parameter id="P" dataType="boolean" tag="9001" />
  </Parameters>
</AlgoDef>
"""
        path = _write_xml(tmp_path, xml)
        algo = parse_dsl(path)
        assert algo.parameters[0].type == "Boolean_t"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestParseDslErrors:
    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_dsl(tmp_path / "missing.xml")

    def test_malformed_xml(self, tmp_path):
        bad = tmp_path / "bad.xml"
        bad.write_text("<unclosed>", encoding="utf-8")
        with pytest.raises(ValueError, match="Malformed XML"):
            parse_dsl(bad)

    def test_missing_required_field(self, tmp_path):
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<AlgoDef name="T">
  <Parameters>
    <Parameter dataType="string" tag="9001" />
  </Parameters>
</AlgoDef>
"""
        path = _write_xml(tmp_path, xml)
        with pytest.raises(ValueError, match="missing required field"):
            parse_dsl(path)

    def test_missing_container(self, tmp_path):
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<AlgoDef name="T">
</AlgoDef>
"""
        path = _write_xml(tmp_path, xml)
        with pytest.raises(ValueError, match="Missing"):
            parse_dsl(path)

    def test_namespace_transparent(self, tmp_path):
        path = _write_xml(tmp_path, _NAMESPACED_XML)
        algo = parse_dsl(path)
        assert algo.name == "NSTEST"
        assert len(algo.parameters) == 1


# ---------------------------------------------------------------------------
# parse_dsl_with_coverage
# ---------------------------------------------------------------------------

class TestParseDslWithCoverage:
    def test_returns_tuple(self):
        result = parse_dsl_with_coverage(STEALTH_DSL)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_mapped_fields_populated(self):
        _, cov = parse_dsl_with_coverage(STEALTH_DSL)
        assert isinstance(cov, FieldCoverage)
        assert len(cov.mapped) > 0
        assert all("dsl_attr" in m and "internal_field" in m and "value" in m
                   for m in cov.mapped)

    def test_missing_optional_in_coverage(self, tmp_path):
        # A parameter with no description → "description" should be missing
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<AlgoDef name="T">
  <Parameters>
    <Parameter id="P" dataType="string" tag="9001" />
  </Parameters>
</AlgoDef>
"""
        path = _write_xml(tmp_path, xml)
        _, cov = parse_dsl_with_coverage(path)
        # default_value and description are optional — both absent here
        assert "description" in cov.missing or "default_value" in cov.missing
