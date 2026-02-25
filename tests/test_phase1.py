"""Tests for Phase 1 — XSD structural validation."""

import json
import tempfile
from pathlib import Path

import pytest

from schema_validator.runner import validate

SCHEMA = Path(__file__).parent.parent / "schemas" / "atdl-core-1-1.xsd"
VALID_FULL = Path(__file__).parent / "fixtures" / "valid_full.xml"

CORE_NS = "http://www.fixprotocol.org/ATDL-1-1/Core"
CORE = f'xmlns="{CORE_NS}"'
XSI = 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
CORE_PFX = f'xmlns:core="{CORE_NS}"'


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "doc.xml"
    p.write_text(content, encoding="utf-8")
    return p


def _minimal_valid(*, sit: str = "847", extra_strat_attrs: str = "",
                   extra_param_attrs: str = "") -> str:
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<Strategies {CORE} {XSI} {CORE_PFX} strategyIdentifierTag="{sit}">
  <Strategy name="Algo" wireValue="Algo" version="1" {extra_strat_attrs}>
    <Parameter name="p1" xsi:type="core:String_t" fixTag="5001" {extra_param_attrs}/>
  </Strategy>
</Strategies>"""


class TestPhase1ValidDocument:
    def test_valid_full_fixture_passes(self):
        result = validate(VALID_FULL, SCHEMA, phases=(1,))
        assert result.valid, result.errors

    def test_minimal_valid_passes(self, tmp_path):
        path = _write(tmp_path, _minimal_valid())
        result = validate(path, SCHEMA, phases=(1,))
        assert result.valid, result.errors

    def test_errors_are_phase1(self, tmp_path):
        bad = _write(tmp_path, """\
<?xml version="1.0" encoding="UTF-8"?>
<Strategies xmlns="http://www.fixprotocol.org/ATDL-1-1/Core">
  <Strategy name="A" wireValue="A" version="1"/>
</Strategies>""")
        result = validate(bad, SCHEMA, phases=(1,))
        assert all(e.phase == 1 for e in result.errors)
        assert all(e.rule_id == "XSD" for e in result.errors)


class TestPhase1MissingRequired:
    def test_missing_strategy_identifier_tag(self, tmp_path):
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<Strategies xmlns="http://www.fixprotocol.org/ATDL-1-1/Core"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xmlns:core="http://www.fixprotocol.org/ATDL-1-1/Core">
  <Strategy name="Algo" wireValue="Algo" version="1">
    <Parameter name="p1" xsi:type="core:String_t" fixTag="5001"/>
  </Strategy>
</Strategies>"""
        path = _write(tmp_path, xml)
        result = validate(path, SCHEMA, phases=(1,))
        assert not result.valid

    def test_missing_strategy_wire_value(self, tmp_path):
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<Strategies xmlns="http://www.fixprotocol.org/ATDL-1-1/Core"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xmlns:core="http://www.fixprotocol.org/ATDL-1-1/Core"
            strategyIdentifierTag="847">
  <Strategy name="Algo" version="1">
    <Parameter name="p1" xsi:type="core:String_t" fixTag="5001"/>
  </Strategy>
</Strategies>"""
        path = _write(tmp_path, xml)
        result = validate(path, SCHEMA, phases=(1,))
        assert not result.valid

    def test_missing_strategy_version(self, tmp_path):
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<Strategies xmlns="http://www.fixprotocol.org/ATDL-1-1/Core"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xmlns:core="http://www.fixprotocol.org/ATDL-1-1/Core"
            strategyIdentifierTag="847">
  <Strategy name="Algo" wireValue="Algo">
    <Parameter name="p1" xsi:type="core:String_t" fixTag="5001"/>
  </Strategy>
</Strategies>"""
        path = _write(tmp_path, xml)
        result = validate(path, SCHEMA, phases=(1,))
        assert not result.valid

    def test_invalid_enum_pair_enum_id_starts_with_digit(self, tmp_path):
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<Strategies xmlns="http://www.fixprotocol.org/ATDL-1-1/Core"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xmlns:core="http://www.fixprotocol.org/ATDL-1-1/Core"
            strategyIdentifierTag="847">
  <Strategy name="Algo" wireValue="Algo" version="1">
    <Parameter name="p1" xsi:type="core:String_t" fixTag="5001">
      <EnumPair enumID="1_Bad" wireValue="x"/>
    </Parameter>
  </Strategy>
</Strategies>"""
        path = _write(tmp_path, xml)
        result = validate(path, SCHEMA, phases=(1,))
        assert not result.valid

    def test_phase1_short_circuits_later_phases(self, tmp_path):
        # Document with missing strategyIdentifierTag should produce only Phase 1 errors
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<Strategies xmlns="http://www.fixprotocol.org/ATDL-1-1/Core"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xmlns:core="http://www.fixprotocol.org/ATDL-1-1/Core">
  <Strategy name="Algo" wireValue="Algo" version="1">
    <Parameter name="p1" xsi:type="core:String_t" fixTag="5001"/>
  </Strategy>
</Strategies>"""
        path = _write(tmp_path, xml)
        result = validate(path, SCHEMA, phases=(1, 2, 3))
        assert all(e.phase == 1 for e in result.errors)
