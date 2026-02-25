"""Tests for converter.builder."""

from pathlib import Path

import pytest
from lxml import etree

from converter.builder import (
    CORE_NS,
    XSI_NS,
    _sanitize_enum_id,
    build_fixatdl,
    write_fixatdl,
)
from converter.parser import AlgoDef, ParameterDef


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_algo(params=None):
    if params is None:
        params = [
            ParameterDef(
                name="myParam1",
                description="My first parameter",
                type="String_t",
                fix_tag=5001,
                supported_values=["A", "B", "C"],
            )
        ]
    return AlgoDef(name="MyAlgo", parameters=params)


def _qname(local):
    return f"{{{CORE_NS}}}{local}"


# ---------------------------------------------------------------------------
# _sanitize_enum_id
# ---------------------------------------------------------------------------

class TestSanitizeEnumId:
    def test_valid_letter_value(self):
        assert _sanitize_enum_id("A") == "A"

    def test_valid_word(self):
        assert _sanitize_enum_id("BuyOrder") == "BuyOrder"

    def test_numeric_value_gets_prefix(self):
        result = _sanitize_enum_id("1")
        assert result[0].isalpha(), "Must start with a letter"

    def test_special_chars_replaced(self):
        result = _sanitize_enum_id("hello world")
        assert " " not in result

    def test_empty_string_gets_prefix(self):
        result = _sanitize_enum_id("")
        assert result[0].isalpha()


# ---------------------------------------------------------------------------
# build_fixatdl — structure
# ---------------------------------------------------------------------------

class TestBuildFixatdlStructure:
    def test_root_element_tag(self):
        root = build_fixatdl(_make_algo())
        assert root.tag == _qname("Strategies")

    def test_strategy_identifier_tag_attribute(self):
        root = build_fixatdl(_make_algo(), strategy_identifier_tag=847)
        assert root.get("strategyIdentifierTag") == "847"

    def test_strategy_element_exists(self):
        root = build_fixatdl(_make_algo())
        strategies = root.findall(_qname("Strategy"))
        assert len(strategies) == 1

    def test_strategy_name(self):
        root = build_fixatdl(_make_algo())
        strat = root.find(_qname("Strategy"))
        assert strat.get("name") == "MyAlgo"

    def test_strategy_ui_rep_equals_name(self):
        root = build_fixatdl(_make_algo())
        strat = root.find(_qname("Strategy"))
        assert strat.get("uiRep") == strat.get("name")

    def test_strategy_wire_value_equals_name(self):
        root = build_fixatdl(_make_algo())
        strat = root.find(_qname("Strategy"))
        assert strat.get("wireValue") == strat.get("name")

    def test_strategy_fix_msg_type(self):
        root = build_fixatdl(_make_algo())
        strat = root.find(_qname("Strategy"))
        assert strat.get("fixMsgType") == "D"

    def test_strategy_provider_id_default(self):
        root = build_fixatdl(_make_algo())
        strat = root.find(_qname("Strategy"))
        assert strat.get("providerID") == "CustomProvider"

    def test_strategy_provider_id_custom(self):
        root = build_fixatdl(_make_algo(), provider_id="ACME")
        strat = root.find(_qname("Strategy"))
        assert strat.get("providerID") == "ACME"

    def test_strategy_version_default(self):
        root = build_fixatdl(_make_algo())
        strat = root.find(_qname("Strategy"))
        assert strat.get("version") == "1"

    def test_strategy_version_custom(self):
        root = build_fixatdl(_make_algo(), strategy_version="2")
        strat = root.find(_qname("Strategy"))
        assert strat.get("version") == "2"


# ---------------------------------------------------------------------------
# build_fixatdl — Parameter element
# ---------------------------------------------------------------------------

class TestBuildFixatdlParameter:
    def _get_param(self, root):
        strat = root.find(_qname("Strategy"))
        return strat.find(_qname("Parameter"))

    def test_parameter_name(self):
        root = build_fixatdl(_make_algo())
        param = self._get_param(root)
        assert param.get("name") == "myParam1"

    def test_parameter_xsi_type(self):
        root = build_fixatdl(_make_algo())
        param = self._get_param(root)
        xsi_type = param.get(f"{{{XSI_NS}}}type")
        assert xsi_type == "core:String_t"

    def test_parameter_fix_tag(self):
        root = build_fixatdl(_make_algo())
        param = self._get_param(root)
        assert param.get("fixTag") == "5001"

    def test_parameter_mutable_on_cxl_rpl(self):
        root = build_fixatdl(_make_algo())
        param = self._get_param(root)
        assert param.get("mutableOnCxlRpl") == "true"

    def test_enum_pairs_count(self):
        root = build_fixatdl(_make_algo())
        param = self._get_param(root)
        pairs = param.findall(_qname("EnumPair"))
        assert len(pairs) == 3

    def test_enum_pair_attributes(self):
        root = build_fixatdl(_make_algo())
        param = self._get_param(root)
        pairs = param.findall(_qname("EnumPair"))
        assert pairs[0].get("enumID") == "A"
        assert pairs[0].get("wireValue") == "A"

    def test_no_enum_pairs_when_empty(self):
        algo = _make_algo(params=[
            ParameterDef(name="p", description="", type="Int_t",
                         fix_tag=1, supported_values=[])
        ])
        root = build_fixatdl(algo)
        param = root.find(_qname("Strategy")).find(_qname("Parameter"))
        assert param.findall(_qname("EnumPair")) == []

    def test_description_comment_present(self):
        root = build_fixatdl(_make_algo())
        strat = root.find(_qname("Strategy"))
        comments = [c for c in strat if isinstance(c, etree._Comment)]
        assert any("myParam1" in c.text and "My first parameter" in c.text
                   for c in comments)

    def test_no_comment_when_no_description(self):
        algo = _make_algo(params=[
            ParameterDef(name="p", description="", type="Int_t",
                         fix_tag=1, supported_values=[])
        ])
        root = build_fixatdl(algo)
        strat = root.find(_qname("Strategy"))
        comments = [c for c in strat if isinstance(c, etree._Comment)]
        assert comments == []

    def test_multiple_parameters(self):
        algo = AlgoDef(
            name="Multi",
            parameters=[
                ParameterDef("p1", "", "Int_t", 1, []),
                ParameterDef("p2", "", "String_t", 2, []),
            ],
        )
        root = build_fixatdl(algo)
        strat = root.find(_qname("Strategy"))
        params = strat.findall(_qname("Parameter"))
        assert len(params) == 2


# ---------------------------------------------------------------------------
# write_fixatdl
# ---------------------------------------------------------------------------

class TestWriteFixatdl:
    def test_file_is_created(self, tmp_path):
        root = build_fixatdl(_make_algo())
        out = tmp_path / "out.xml"
        write_fixatdl(root, out)
        assert out.exists()

    def test_file_starts_with_xml_declaration(self, tmp_path):
        root = build_fixatdl(_make_algo())
        out = tmp_path / "out.xml"
        write_fixatdl(root, out)
        content = out.read_bytes()
        assert content.startswith(b"<?xml")

    def test_output_is_parseable(self, tmp_path):
        root = build_fixatdl(_make_algo())
        out = tmp_path / "out.xml"
        write_fixatdl(root, out)
        parsed = etree.parse(str(out))
        assert parsed is not None

    def test_creates_parent_dirs(self, tmp_path):
        root = build_fixatdl(_make_algo())
        out = tmp_path / "sub" / "dir" / "out.xml"
        write_fixatdl(root, out)
        assert out.exists()
