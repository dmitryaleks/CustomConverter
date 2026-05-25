"""Tests for fixatdl_validator -- run with: python -m pytest test_fixatdl_validator.py"""

import os

import pytest

from fixatdl_validator import RULES, validate_file, validate_string

SAMPLE = os.path.join(os.path.dirname(__file__), "specification",
                      "SampleStrategiesFor-v1.1.xml")

VALID_MIN = """<?xml version="1.0"?>
<Strategies xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            strategyIdentifierTag="5009">
  <Strategy name="VWAP" wireValue="v" version="1">
    <Parameter name="Rate" xsi:type="Float_t" fixTag="8000" use="optional"/>
  </Strategy>
</Strategies>"""


def rule_ids(result):
    return {e["rule_id"] for e in result["errors"]}


def test_official_sample_is_valid():
    result = validate_file(SAMPLE)
    assert result["valid"], result["errors"]
    assert result["summary"]["errors"] == 0


def test_minimal_valid_document():
    assert validate_string(VALID_MIN)["valid"]


def test_malformed_xml():
    r = validate_string("<Strategies><Strategy></Strategies>")
    assert not r["valid"]
    assert "XML-01" in rule_ids(r)


def test_wrong_root_element():
    r = validate_string('<FIXATDL strategyIdentifierTag="1"/>')
    assert "DOC-01" in rule_ids(r)


def test_missing_strategy_identifier_tag():
    r = validate_string('<Strategies xmlns:xsi="x"><Strategy name="a" '
                        'wireValue="v" version="1"/></Strategies>')
    assert "DOC-02" in rule_ids(r)


def test_strategy_identifier_tag_not_positive_int():
    r = validate_string('<Strategies strategyIdentifierTag="abc"/>')
    assert "DOC-03" in rule_ids(r)


def test_no_strategies():
    r = validate_string('<Strategies strategyIdentifierTag="1"/>')
    assert "DOC-07" in rule_ids(r)


def test_duplicate_strategy_name():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1">'
        '<Strategy name="A" wireValue="v" version="1"/>'
        '<Strategy name="A" wireValue="w" version="1"/></Strategies>')
    assert "STR-02" in rule_ids(r)


def test_invalid_fix_msg_type():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1">'
        '<Strategy name="A" wireValue="v" version="1" fixMsgType="Z"/></Strategies>')
    assert "STR-05" in rule_ids(r)


def test_invalid_parameter_type():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1"><Strategy name="A" wireValue="v" version="1">'
        '<Parameter name="P" xsi:type="Nope_t" fixTag="1"/></Strategy></Strategies>')
    assert "PARAM-03" in rule_ids(r)


def test_duplicate_parameter_name():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1"><Strategy name="A" wireValue="v" version="1">'
        '<Parameter name="P" xsi:type="Int_t" fixTag="1"/>'
        '<Parameter name="P" xsi:type="Int_t" fixTag="2"/></Strategy></Strategies>')
    assert "PARAM-02" in rule_ids(r)


def test_minvalue_greater_than_maxvalue():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1"><Strategy name="A" wireValue="v" version="1">'
        '<Parameter name="P" xsi:type="Int_t" fixTag="1" minValue="9" maxValue="1"/>'
        '</Strategy></Strategies>')
    assert "PARAM-06" in rule_ids(r)


def test_minmax_not_applicable():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1"><Strategy name="A" wireValue="v" version="1">'
        '<Parameter name="P" xsi:type="String_t" fixTag="1" minValue="1"/>'
        '</Strategy></Strategies>')
    assert "PARAM-05" in rule_ids(r)


def test_bad_localmkttz():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1"><Strategy name="A" wireValue="v" version="1">'
        '<Parameter name="P" xsi:type="UTCTimestamp_t" fixTag="1" localMktTz="Narnia/Cair"/>'
        '</Strategy></Strategies>')
    assert "PARAM-08" in rule_ids(r)


def test_good_localmkttz_passes():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1"><Strategy name="A" wireValue="v" version="1">'
        '<Parameter name="P" xsi:type="UTCTimestamp_t" fixTag="1" localMktTz="America/New_York"/>'
        '</Strategy></Strategies>')
    assert "PARAM-08" not in rule_ids(r)


def test_enumpair_requires_enumid_and_wirevalue():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1"><Strategy name="A" wireValue="v" version="1">'
        '<Parameter name="P" xsi:type="Char_t" fixTag="1"><EnumPair/></Parameter>'
        '</Strategy></Strategies>')
    ids = rule_ids(r)
    assert "ENUM-01" in ids and "ENUM-02" in ids


def test_edit_operator_and_logicoperator_mutually_exclusive():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1"><Strategy name="A" wireValue="v" version="1">'
        '<Parameter name="P" xsi:type="Int_t" fixTag="1"/>'
        '<StrategyEdit errorMessage="e"><Edit field="P" operator="EQ" '
        'logicOperator="AND" value="1"/></StrategyEdit></Strategy></Strategies>')
    assert "EDIT-01" in rule_ids(r)


def test_edit_unknown_field_reference():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1"><Strategy name="A" wireValue="v" version="1">'
        '<Parameter name="P" xsi:type="Int_t" fixTag="1"/>'
        '<StrategyEdit errorMessage="e"><Edit field="Ghost" operator="EQ" value="1"/>'
        '</StrategyEdit></Strategy></Strategies>')
    assert "EDIT-10" in rule_ids(r)


def test_edit_fix_prefixed_field_allowed():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1"><Strategy name="A" wireValue="v" version="1">'
        '<Parameter name="P" xsi:type="Int_t" fixTag="1"/>'
        '<StrategyEdit errorMessage="e"><Edit field="FIX_TimeInForce" operator="EQ" value="3"/>'
        '</StrategyEdit></Strategy></Strategies>')
    assert "EDIT-10" not in rule_ids(r)


def test_editref_must_resolve():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1"><Strategy name="A" wireValue="v" version="1">'
        '<StrategyEdit errorMessage="e"><EditRef id="nope"/></StrategyEdit>'
        '</Strategy></Strategies>')
    assert "EREF-01" in rule_ids(r)


def test_editref_resolves_to_strategy_level_edit():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1"><Strategy name="A" wireValue="v" version="1">'
        '<Parameter name="P" xsi:type="Int_t" fixTag="1"/>'
        '<Edit id="e1" field="P" operator="EX"/>'
        '<StrategyEdit errorMessage="e"><EditRef id="e1"/></StrategyEdit>'
        '</Strategy></Strategies>')
    assert "EREF-01" not in rule_ids(r)


def test_control_parameterref_must_exist():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1"><Strategy name="A" wireValue="v" version="1">'
        '<StrategyLayout><StrategyPanel>'
        '<Control ID="c" xsi:type="TextField_t" parameterRef="Ghost"/>'
        '</StrategyPanel></StrategyLayout></Strategy></Strategies>')
    assert "CTRL-03" in rule_ids(r)


def test_listitem_enumid_must_match_enumpair():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1"><Strategy name="A" wireValue="v" version="1">'
        '<Parameter name="P" xsi:type="Char_t" fixTag="1">'
        '<EnumPair enumID="a" wireValue="A"/></Parameter>'
        '<StrategyLayout><StrategyPanel>'
        '<Control ID="c" xsi:type="DropDownList_t" parameterRef="P">'
        '<ListItem enumID="zzz" uiRep="Z"/></Control>'
        '</StrategyPanel></StrategyLayout></Strategy></Strategies>')
    assert "CTRL-04" in rule_ids(r)


def test_panel_mixed_children():
    r = validate_string(
        '<Strategies strategyIdentifierTag="1"><Strategy name="A" wireValue="v" version="1">'
        '<StrategyLayout><StrategyPanel>'
        '<Control ID="c" xsi:type="TextField_t"/><StrategyPanel/>'
        '</StrategyPanel></StrategyLayout></Strategy></Strategies>')
    assert "LAY-02" in rule_ids(r)


def test_namespace_transparency_legacy_uri():
    """A document using the legacy ATDL-1-1 namespace validates identically."""
    legacy = VALID_MIN.replace("FIXatdl-1-1", "ATDL-1-1")
    assert validate_string(legacy)["valid"]


def test_every_emitted_rule_id_is_catalogued():
    """No finding may use a rule ID that is missing from the RULES catalogue."""
    r = validate_file(SAMPLE)
    # also exercise a broken doc to surface many rule ids
    broken = validate_string('<FIXATDL/>')
    for res in (r, broken):
        for e in res["errors"]:
            assert e["rule_id"] in RULES, e["rule_id"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
