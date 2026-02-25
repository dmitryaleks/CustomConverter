"""Tests for Phase 3 — semantic and business rule checks."""

from pathlib import Path

import pytest

from schema_validator.runner import validate

SCHEMA = Path(__file__).parent.parent / "schemas" / "atdl-core-1-1.xsd"
VALID_FULL = Path(__file__).parent / "fixtures" / "valid_full.xml"

CORE_NS = "http://www.fixprotocol.org/ATDL-1-1/Core"
VAL_NS = "http://www.fixprotocol.org/ATDL-1-1/Validation"
LAY_NS = "http://www.fixprotocol.org/ATDL-1-1/Layout"

_NS_DECLS = (
    f'xmlns="{CORE_NS}" '
    f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    f'xmlns:core="{CORE_NS}" '
    f'xmlns:val="{VAL_NS}" '
    f'xmlns:lay="{LAY_NS}"'
)


def _doc(body: str, sit: int = 847) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<Strategies {_NS_DECLS} strategyIdentifierTag="{sit}">\n'
        f'{body}\n'
        f'</Strategies>'
    )


def _strat(name: str = "TestAlgo", params: str = "", extras: str = "") -> str:
    return (
        f'<Strategy name="{name}" wireValue="{name}" version="1">\n'
        f'{params}\n{extras}\n'
        f'</Strategy>'
    )


def _param(name: str = "MyParam", fix_tag: int = 5001,
           xsi_type: str = "String_t", extra: str = "") -> str:
    return f'<Parameter name="{name}" xsi:type="core:{xsi_type}" fixTag="{fix_tag}" {extra}/>'


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "doc.xml"
    p.write_text(content, encoding="utf-8")
    return p


def _rule_ids(result) -> set[str]:
    return {e.rule_id for e in result.errors}


def _warn_ids(result) -> set[str]:
    return {w.rule_id for w in result.warnings}


class TestPhase3ValidDocument:
    def test_valid_full_fixture_passes(self):
        result = validate(VALID_FULL, SCHEMA, phases=(3,))
        assert result.valid, result.errors


class TestSEM01:
    def test_duplicate_wire_value(self, tmp_path):
        param = (
            '<Parameter name="Side" xsi:type="core:String_t" fixTag="54">'
            '  <EnumPair enumID="Buy" wireValue="1"/>'
            '  <EnumPair enumID="Sell" wireValue="1"/>'
            '</Parameter>'
        )
        result = validate(_write(tmp_path, _doc(_strat(params=param))), SCHEMA, phases=(3,))
        assert "SEM-01" in _rule_ids(result)

    def test_unique_wire_values_pass(self, tmp_path):
        param = (
            '<Parameter name="Side" xsi:type="core:String_t" fixTag="54">'
            '  <EnumPair enumID="Buy" wireValue="1"/>'
            '  <EnumPair enumID="Sell" wireValue="2"/>'
            '</Parameter>'
        )
        result = validate(_write(tmp_path, _doc(_strat(params=param))), SCHEMA, phases=(3,))
        assert "SEM-01" not in _rule_ids(result)


class TestSEM02:
    def test_duplicate_enum_id(self, tmp_path):
        param = (
            '<Parameter name="Side" xsi:type="core:String_t" fixTag="54">'
            '  <EnumPair enumID="Buy" wireValue="1"/>'
            '  <EnumPair enumID="Buy" wireValue="2"/>'
            '</Parameter>'
        )
        result = validate(_write(tmp_path, _doc(_strat(params=param))), SCHEMA, phases=(3,))
        assert "SEM-02" in _rule_ids(result)


class TestSEM03:
    def test_const_true_and_required(self, tmp_path):
        param = _param(extra='const="true" use="required"')
        result = validate(_write(tmp_path, _doc(_strat(params=param))), SCHEMA, phases=(3,))
        assert "SEM-03" in _rule_ids(result)

    def test_const_true_optional_is_ok(self, tmp_path):
        param = _param(extra='const="true" constValue="X" use="optional"')
        result = validate(_write(tmp_path, _doc(_strat(params=param))), SCHEMA, phases=(3,))
        assert "SEM-03" not in _rule_ids(result)


class TestSEM04:
    def test_const_true_without_const_value_warns(self, tmp_path):
        param = _param(extra='const="true"')
        result = validate(_write(tmp_path, _doc(_strat(params=param))), SCHEMA, phases=(3,))
        assert "SEM-04" in _warn_ids(result)

    def test_const_true_with_const_value_no_warning(self, tmp_path):
        param = _param(extra='const="true" constValue="X"')
        result = validate(_write(tmp_path, _doc(_strat(params=param))), SCHEMA, phases=(3,))
        assert "SEM-04" not in _warn_ids(result)


class TestSEM05:
    def test_duplicate_strategy_names(self, tmp_path):
        xml = _doc(
            _strat("AlgoA", _param()) + "\n" +
            _strat("AlgoA", _param("P2", 5002))
        )
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(3,))
        assert "SEM-05" in _rule_ids(result)

    def test_unique_strategy_names_pass(self, tmp_path):
        xml = _doc(
            _strat("AlgoA", _param()) + "\n" +
            _strat("AlgoB", _param("P2", 5002))
        )
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(3,))
        assert "SEM-05" not in _rule_ids(result)


class TestSEM06:
    def test_duplicate_parameter_names(self, tmp_path):
        params = _param("Same", 5001) + "\n" + _param("Same", 5002)
        result = validate(_write(tmp_path, _doc(_strat(params=params))), SCHEMA, phases=(3,))
        assert "SEM-06" in _rule_ids(result)


class TestSEM07:
    def test_invalid_timezone(self, tmp_path):
        param = _param("T", 5001, "UTCTimeStamp_t", extra='localMktTz="Not/ATimezone"')
        result = validate(_write(tmp_path, _doc(_strat(params=param))), SCHEMA, phases=(3,))
        assert "SEM-07" in _rule_ids(result)

    def test_valid_timezone_passes(self, tmp_path):
        param = _param("T", 5001, "UTCTimeStamp_t", extra='localMktTz="America/New_York"')
        result = validate(_write(tmp_path, _doc(_strat(params=param))), SCHEMA, phases=(3,))
        assert "SEM-07" not in _rule_ids(result)


class TestSEM08:
    def test_country_not_in_region(self, tmp_path):
        strat = (
            '<Strategy name="A" wireValue="A" version="1">'
            '  <Regions>'
            '    <Region name="TheAmericas" inclusion="Include">'
            '      <Country CountryCode="DE" inclusion="Include"/>'
            '    </Region>'
            '  </Regions>'
            '  ' + _param() +
            '</Strategy>'
        )
        result = validate(_write(tmp_path, _doc(strat)), SCHEMA, phases=(3,))
        assert "SEM-08" in _rule_ids(result)

    def test_valid_country_in_region_passes(self, tmp_path):
        strat = (
            '<Strategy name="A" wireValue="A" version="1">'
            '  <Regions>'
            '    <Region name="TheAmericas" inclusion="Include">'
            '      <Country CountryCode="US" inclusion="Include"/>'
            '    </Region>'
            '  </Regions>'
            '  ' + _param() +
            '</Strategy>'
        )
        result = validate(_write(tmp_path, _doc(strat)), SCHEMA, phases=(3,))
        assert "SEM-08" not in _rule_ids(result)


class TestSEM09:
    def test_invalid_mic_code(self, tmp_path):
        strat = (
            '<Strategy name="A" wireValue="A" version="1">'
            '  <Markets>'
            '    <Market MICCode="bad!" inclusion="Include"/>'
            '  </Markets>'
            '  ' + _param() +
            '</Strategy>'
        )
        result = validate(_write(tmp_path, _doc(strat)), SCHEMA, phases=(3,))
        assert "SEM-09" in _rule_ids(result)

    def test_valid_mic_passes(self, tmp_path):
        strat = (
            '<Strategy name="A" wireValue="A" version="1">'
            '  <Markets>'
            '    <Market MICCode="XNAS" inclusion="Include"/>'
            '  </Markets>'
            '  ' + _param() +
            '</Strategy>'
        )
        result = validate(_write(tmp_path, _doc(strat)), SCHEMA, phases=(3,))
        assert "SEM-09" not in _rule_ids(result)


class TestSEM10:
    def test_logic_operator_without_children(self, tmp_path):
        extras = '<val:Edit id="e1" logicOperator="AND"/>'
        result = validate(_write(tmp_path, _doc(_strat(params=_param(), extras=extras))), SCHEMA, phases=(3,))
        assert "SEM-10" in _rule_ids(result)

    def test_operator_with_children(self, tmp_path):
        extras = (
            '<val:Edit id="e1" field="MyParam" operator="EX">'
            '  <val:Edit field="MyParam" operator="NX"/>'
            '</val:Edit>'
        )
        result = validate(_write(tmp_path, _doc(_strat(params=_param(), extras=extras))), SCHEMA, phases=(3,))
        assert "SEM-10" in _rule_ids(result)

    def test_valid_logic_operator_with_children_passes(self, tmp_path):
        extras = (
            '<val:Edit id="parent" logicOperator="AND">'
            '  <val:Edit field="MyParam" operator="EX"/>'
            '</val:Edit>'
        )
        result = validate(_write(tmp_path, _doc(_strat(params=_param(), extras=extras))), SCHEMA, phases=(3,))
        assert "SEM-10" not in _rule_ids(result)


class TestSEM11:
    def test_field2_and_value_both_present(self, tmp_path):
        params = _param("P1", 5001) + "\n" + _param("P2", 5002)
        extras = '<val:Edit field="P1" field2="P2" value="X" operator="EQ"/>'
        result = validate(_write(tmp_path, _doc(_strat(params=params, extras=extras))), SCHEMA, phases=(3,))
        assert "SEM-11" in _rule_ids(result)

    def test_field_and_value_passes(self, tmp_path):
        extras = '<val:Edit field="MyParam" value="X" operator="EQ"/>'
        result = validate(_write(tmp_path, _doc(_strat(params=_param(), extras=extras))), SCHEMA, phases=(3,))
        assert "SEM-11" not in _rule_ids(result)


class TestSEM12:
    def test_operator_and_logic_operator_both_present(self, tmp_path):
        extras = '<val:Edit field="MyParam" operator="EX" logicOperator="AND"/>'
        result = validate(_write(tmp_path, _doc(_strat(params=_param(), extras=extras))), SCHEMA, phases=(3,))
        assert "SEM-12" in _rule_ids(result)


class TestSEM13:
    def test_min_value_greater_than_max_value(self, tmp_path):
        param = _param("Q", 38, "Qty_t", extra='minValue="100" maxValue="10"')
        result = validate(_write(tmp_path, _doc(_strat(params=param))), SCHEMA, phases=(3,))
        assert "SEM-13" in _rule_ids(result)

    def test_min_equals_max_passes(self, tmp_path):
        param = _param("Q", 38, "Qty_t", extra='minValue="10" maxValue="10"')
        result = validate(_write(tmp_path, _doc(_strat(params=param))), SCHEMA, phases=(3,))
        assert "SEM-13" not in _rule_ids(result)

    def test_valid_min_max_passes(self, tmp_path):
        param = _param("Q", 38, "Qty_t", extra='minValue="1" maxValue="1000"')
        result = validate(_write(tmp_path, _doc(_strat(params=param))), SCHEMA, phases=(3,))
        assert "SEM-13" not in _rule_ids(result)


class TestSEM14:
    def test_min_length_greater_than_max_length(self, tmp_path):
        param = _param("N", 5001, "String_t", extra='minLength="100" maxLength="10"')
        result = validate(_write(tmp_path, _doc(_strat(params=param))), SCHEMA, phases=(3,))
        assert "SEM-14" in _rule_ids(result)

    def test_valid_lengths_pass(self, tmp_path):
        param = _param("N", 5001, "String_t", extra='minLength="0" maxLength="100"')
        result = validate(_write(tmp_path, _doc(_strat(params=param))), SCHEMA, phases=(3,))
        assert "SEM-14" not in _rule_ids(result)


class TestSEM15:
    def test_zero_increment_fails(self, tmp_path):
        xml = _doc(
            '<Strategy name="A" wireValue="A" version="1">'
            + _param() +
            '<lay:StrategyLayout>'
            '<lay:StrategyPanel orientation="VERTICAL">'
            '<lay:Control xsi:type="lay:SingleSpinner_t" ID="s1"'
            '             parameterRef="MyParam" label="X" increment="0"/>'
            '</lay:StrategyPanel>'
            '</lay:StrategyLayout>'
            '</Strategy>'
        )
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(3,))
        assert "SEM-15" in _rule_ids(result)

    def test_negative_increment_fails(self, tmp_path):
        xml = _doc(
            '<Strategy name="A" wireValue="A" version="1">'
            + _param() +
            '<lay:StrategyLayout>'
            '<lay:StrategyPanel orientation="VERTICAL">'
            '<lay:Control xsi:type="lay:SingleSpinner_t" ID="s1"'
            '             parameterRef="MyParam" label="X" increment="-1"/>'
            '</lay:StrategyPanel>'
            '</lay:StrategyLayout>'
            '</Strategy>'
        )
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(3,))
        assert "SEM-15" in _rule_ids(result)

    def test_positive_increment_passes(self, tmp_path):
        xml = _doc(
            '<Strategy name="A" wireValue="A" version="1">'
            + _param() +
            '<lay:StrategyLayout>'
            '<lay:StrategyPanel orientation="VERTICAL">'
            '<lay:Control xsi:type="lay:SingleSpinner_t" ID="s1"'
            '             parameterRef="MyParam" label="X" increment="0.5"/>'
            '</lay:StrategyPanel>'
            '</lay:StrategyLayout>'
            '</Strategy>'
        )
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(3,))
        assert "SEM-15" not in _rule_ids(result)


class TestSEM16:
    def test_strategy_identifier_tag_collides_with_fix_tag(self, tmp_path):
        # strategyIdentifierTag=5001, Parameter fixTag=5001 → collision
        xml = _doc(_strat(params=_param("P", 5001)), sit=5001)
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(3,))
        assert "SEM-16" in _rule_ids(result)

    def test_no_collision_passes(self, tmp_path):
        xml = _doc(_strat(params=_param("P", 5001)), sit=847)
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(3,))
        assert "SEM-16" not in _rule_ids(result)
