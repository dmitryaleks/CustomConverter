"""Tests for Phase 2 — referential integrity checks."""

from pathlib import Path

import pytest

from schema_validator.runner import validate

SCHEMA = Path(__file__).parent.parent / "schemas" / "atdl-core-1-1.xsd"
VALID_FULL = Path(__file__).parent / "fixtures" / "valid_full.xml"

CORE_NS = "http://www.fixprotocol.org/ATDL-1-1/Core"
VAL_NS = "http://www.fixprotocol.org/ATDL-1-1/Validation"
LAY_NS = "http://www.fixprotocol.org/ATDL-1-1/Layout"
FLOW_NS = "http://www.fixprotocol.org/ATDL-1-1/Flow"

_NS_DECLS = (
    f'xmlns="{CORE_NS}" '
    f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    f'xmlns:core="{CORE_NS}" '
    f'xmlns:val="{VAL_NS}" '
    f'xmlns:lay="{LAY_NS}" '
    f'xmlns:flow="{FLOW_NS}"'
)


def _doc(body: str) -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<Strategies {_NS_DECLS} strategyIdentifierTag="847">\n'
        f'{body}\n'
        f'</Strategies>'
    )


def _strat(params: str = "", extras: str = "", layout: str = "") -> str:
    lay_block = f"<lay:StrategyLayout>{layout}</lay:StrategyLayout>" if layout else ""
    return (
        f'<Strategy name="TestAlgo" wireValue="TestAlgo" version="1">\n'
        f'{params}\n{extras}\n{lay_block}\n'
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


class TestPhase2ValidDocument:
    def test_valid_full_fixture_passes(self):
        result = validate(VALID_FULL, SCHEMA, phases=(2,))
        assert result.valid, result.errors


class TestREF01:
    def test_bad_parameter_ref(self, tmp_path):
        xml = _doc(_strat(
            params=_param("RealParam"),
            layout=(
                '<lay:StrategyPanel orientation="VERTICAL">'
                '<lay:Control xsi:type="lay:TextField_t" ID="c1"'
                '             parameterRef="NonExistent" label="X"/>'
                '</lay:StrategyPanel>'
            ),
        ))
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(2,))
        assert not result.valid
        assert "REF-01" in _rule_ids(result)

    def test_valid_parameter_ref_passes(self, tmp_path):
        xml = _doc(_strat(
            params=_param("MyParam"),
            layout=(
                '<lay:StrategyPanel orientation="VERTICAL">'
                '<lay:Control xsi:type="lay:TextField_t" ID="c1"'
                '             parameterRef="MyParam" label="X"/>'
                '</lay:StrategyPanel>'
            ),
        ))
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(2,))
        assert "REF-01" not in _rule_ids(result)

    def test_no_parameter_ref_is_allowed(self, tmp_path):
        xml = _doc(_strat(
            params=_param("MyParam"),
            layout=(
                '<lay:StrategyPanel orientation="VERTICAL">'
                '<lay:Control xsi:type="lay:Label_t" ID="lbl1" label="Info"/>'
                '</lay:StrategyPanel>'
            ),
        ))
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(2,))
        assert "REF-01" not in _rule_ids(result)


class TestREF02:
    def test_duplicate_parameter_ref(self, tmp_path):
        xml = _doc(_strat(
            params=_param("MyParam"),
            layout=(
                '<lay:StrategyPanel orientation="VERTICAL">'
                '<lay:Control xsi:type="lay:TextField_t" ID="c1"'
                '             parameterRef="MyParam" label="A"/>'
                '<lay:Control xsi:type="lay:TextField_t" ID="c2"'
                '             parameterRef="MyParam" label="B"/>'
                '</lay:StrategyPanel>'
            ),
        ))
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(2,))
        assert "REF-02" in _rule_ids(result)

    def test_unique_parameter_refs_pass(self, tmp_path):
        xml = _doc(_strat(
            params=(
                _param("P1", 5001) + "\n" + _param("P2", 5002)
            ),
            layout=(
                '<lay:StrategyPanel orientation="VERTICAL">'
                '<lay:Control xsi:type="lay:TextField_t" ID="c1"'
                '             parameterRef="P1" label="A"/>'
                '<lay:Control xsi:type="lay:TextField_t" ID="c2"'
                '             parameterRef="P2" label="B"/>'
                '</lay:StrategyPanel>'
            ),
        ))
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(2,))
        assert "REF-02" not in _rule_ids(result)


class TestREF03:
    def test_unresolved_edit_ref_in_strategy_edit(self, tmp_path):
        xml = _doc(_strat(
            params=_param(),
            extras=(
                '<val:StrategyEdit errorMessage="test">'
                '  <val:EditRef id="NoSuchEdit"/>'
                '</val:StrategyEdit>'
            ),
        ))
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(2,))
        assert "REF-03" in _rule_ids(result)

    def test_resolved_edit_ref_passes(self, tmp_path):
        xml = _doc(_strat(
            params=_param(),
            extras=(
                '<val:Edit id="MyEdit" field="MyParam" operator="EX"/>'
                '<val:StrategyEdit errorMessage="test">'
                '  <val:EditRef id="MyEdit"/>'
                '</val:StrategyEdit>'
            ),
        ))
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(2,))
        assert "REF-03" not in _rule_ids(result)

    def test_global_edit_resolved_in_strategy(self, tmp_path):
        xml = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<Strategies {_NS_DECLS} strategyIdentifierTag="847">\n'
            f'  <val:Edit id="GlobalEdit" field="MyParam" operator="EX"/>\n'
            f'  <Strategy name="A" wireValue="A" version="1">\n'
            f'    {_param()}\n'
            f'    <val:StrategyEdit errorMessage="t">'
            f'      <val:EditRef id="GlobalEdit"/>'
            f'    </val:StrategyEdit>\n'
            f'  </Strategy>\n'
            f'</Strategies>'
        )
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(2,))
        assert "REF-03" not in _rule_ids(result)


class TestREF04:
    def test_unresolved_edit_ref_in_state_rule(self, tmp_path):
        xml = _doc(_strat(
            params=_param("MyParam"),
            layout=(
                '<lay:StrategyPanel orientation="VERTICAL">'
                '<lay:Control xsi:type="lay:TextField_t" ID="c1"'
                '             parameterRef="MyParam" label="X">'
                '  <flow:StateRule enabled="true">'
                '    <val:EditRef id="NoSuchEdit"/>'
                '  </flow:StateRule>'
                '</lay:Control>'
                '</lay:StrategyPanel>'
            ),
        ))
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(2,))
        assert "REF-04" in _rule_ids(result)


class TestREF05:
    def test_edit_field_not_in_strategy(self, tmp_path):
        xml = _doc(_strat(
            params=_param("RealParam"),
            extras='<val:Edit id="e1" field="FakeParam" operator="EX"/>',
        ))
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(2,))
        assert "REF-05" in _rule_ids(result)

    def test_edit_field2_not_in_strategy(self, tmp_path):
        xml = _doc(_strat(
            params=_param("RealParam"),
            extras='<val:Edit id="e1" field="RealParam" field2="FakeParam" operator="EQ"/>',
        ))
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(2,))
        assert "REF-05" in _rule_ids(result)

    def test_valid_edit_field_passes(self, tmp_path):
        xml = _doc(_strat(
            params=_param("MyParam"),
            extras='<val:Edit id="e1" field="MyParam" operator="EX"/>',
        ))
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(2,))
        assert "REF-05" not in _rule_ids(result)


class TestREF06:
    def _list_item_xml(self, enum_id: str, uiRep: str = "X") -> str:
        return f'<lay:ListItem enumID="{enum_id}" uiRep="{uiRep}"/>'

    def test_list_item_enum_id_not_in_parameter(self, tmp_path):
        param = (
            '<Parameter name="Side" xsi:type="core:String_t" fixTag="54">'
            '  <EnumPair enumID="Buy" wireValue="1"/>'
            '</Parameter>'
        )
        xml = _doc(_strat(
            params=param,
            layout=(
                '<lay:StrategyPanel orientation="VERTICAL">'
                '<lay:Control xsi:type="lay:DropDownList_t" ID="c1"'
                '             parameterRef="Side" label="Side">'
                '  <lay:ListItem enumID="Buy" uiRep="Buy"/>'
                '  <lay:ListItem enumID="UnknownID" uiRep="???"/>'
                '</lay:Control>'
                '</lay:StrategyPanel>'
            ),
        ))
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(2,))
        assert "REF-06" in _rule_ids(result)

    def test_matching_list_items_pass(self, tmp_path):
        param = (
            '<Parameter name="Side" xsi:type="core:String_t" fixTag="54">'
            '  <EnumPair enumID="Buy" wireValue="1"/>'
            '  <EnumPair enumID="Sell" wireValue="2"/>'
            '</Parameter>'
        )
        xml = _doc(_strat(
            params=param,
            layout=(
                '<lay:StrategyPanel orientation="VERTICAL">'
                '<lay:Control xsi:type="lay:DropDownList_t" ID="c1"'
                '             parameterRef="Side" label="Side">'
                '  <lay:ListItem enumID="Buy" uiRep="Buy"/>'
                '  <lay:ListItem enumID="Sell" uiRep="Sell"/>'
                '</lay:Control>'
                '</lay:StrategyPanel>'
            ),
        ))
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(2,))
        assert "REF-06" not in _rule_ids(result)


class TestREF07:
    def test_init_value_not_in_list_items(self, tmp_path):
        param = (
            '<Parameter name="Side" xsi:type="core:String_t" fixTag="54">'
            '  <EnumPair enumID="Buy" wireValue="1"/>'
            '</Parameter>'
        )
        xml = _doc(_strat(
            params=param,
            layout=(
                '<lay:StrategyPanel orientation="VERTICAL">'
                '<lay:Control xsi:type="lay:DropDownList_t" ID="c1"'
                '             parameterRef="Side" label="Side"'
                '             initValue="Sell">'
                '  <lay:ListItem enumID="Buy" uiRep="Buy"/>'
                '</lay:Control>'
                '</lay:StrategyPanel>'
            ),
        ))
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(2,))
        assert "REF-07" in _rule_ids(result)

    def test_valid_init_value_passes(self, tmp_path):
        param = (
            '<Parameter name="Side" xsi:type="core:String_t" fixTag="54">'
            '  <EnumPair enumID="Buy" wireValue="1"/>'
            '</Parameter>'
        )
        xml = _doc(_strat(
            params=param,
            layout=(
                '<lay:StrategyPanel orientation="VERTICAL">'
                '<lay:Control xsi:type="lay:DropDownList_t" ID="c1"'
                '             parameterRef="Side" label="Side"'
                '             initValue="Buy">'
                '  <lay:ListItem enumID="Buy" uiRep="Buy"/>'
                '</lay:Control>'
                '</lay:StrategyPanel>'
            ),
        ))
        result = validate(_write(tmp_path, xml), SCHEMA, phases=(2,))
        assert "REF-07" not in _rule_ids(result)
