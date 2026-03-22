"""Tests for converter.builder."""

from pathlib import Path

import pytest
from lxml import etree

from converter.builder import (
    CORE_NS,
    LAY_NS,
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


# ---------------------------------------------------------------------------
# StrategyLayout generation
# ---------------------------------------------------------------------------

def _lqname(local):
    return f"{{{LAY_NS}}}{local}"


def _make_param(name="p", type_="String_t", tag=5001, sv=None, default=None,
                min_value=None, max_value=None, increment=None):
    return ParameterDef(
        name=name,
        description="",
        type=type_,
        fix_tag=tag,
        supported_values=sv if sv is not None else [],
        default_value=default,
        min_value=min_value,
        max_value=max_value,
        increment=increment,
    )


def _get_strategy(root):
    return root.find(_qname("Strategy"))


class TestStrategyLayout:
    # --- Backward compatibility ------------------------------------------------

    def test_no_layout_when_no_defaults(self):
        algo = AlgoDef("A", [_make_param(default=None)])
        root = build_fixatdl(algo)
        assert _get_strategy(root).find(_lqname("StrategyLayout")) is None

    # --- StrategyLayout structure ---------------------------------------------

    def test_layout_present_when_any_default(self):
        algo = AlgoDef("A", [_make_param(default="X")])
        root = build_fixatdl(algo)
        assert _get_strategy(root).find(_lqname("StrategyLayout")) is not None

    def test_layout_has_one_strategy_panel(self):
        algo = AlgoDef("A", [_make_param(default="X")])
        root = build_fixatdl(algo)
        layout = _get_strategy(root).find(_lqname("StrategyLayout"))
        assert len(layout.findall(_lqname("StrategyPanel"))) == 1

    def test_all_params_get_control_even_without_default(self):
        algo = AlgoDef("A", [
            _make_param(name="p1", tag=5001, default="X"),
            _make_param(name="p2", tag=5002, default=None),
        ])
        root = build_fixatdl(algo)
        panel = _get_strategy(root).find(f".//{_lqname('StrategyPanel')}")
        assert len(panel.findall(_lqname("Control"))) == 2

    def test_layout_comes_after_parameters(self):
        algo = AlgoDef("A", [_make_param(default="v")])
        root = build_fixatdl(algo)
        strat = _get_strategy(root)
        children = list(strat)
        param_idx = next(i for i, c in enumerate(children)
                         if c.tag == _qname("Parameter"))
        layout_idx = next(i for i, c in enumerate(children)
                          if c.tag == _lqname("StrategyLayout"))
        assert layout_idx > param_idx

    # --- Control attributes ---------------------------------------------------

    def test_control_id_equals_param_name(self):
        algo = AlgoDef("A", [_make_param(name="MyP", default="v")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        assert ctrl.get("ID") == "MyP"

    def test_control_parameter_ref_equals_param_name(self):
        algo = AlgoDef("A", [_make_param(name="MyP", default="v")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        assert ctrl.get("parameterRef") == "MyP"

    def test_control_without_default_has_no_init_value(self):
        algo = AlgoDef("A", [
            _make_param(name="p1", tag=5001, default="X"),
            _make_param(name="p2", tag=5002, default=None),
        ])
        root = build_fixatdl(algo)
        panel = _get_strategy(root).find(f".//{_lqname('StrategyPanel')}")
        p2_ctrl = next(c for c in panel.findall(_lqname("Control"))
                       if c.get("ID") == "p2")
        assert p2_ctrl.get("initValue") is None

    # --- Control type mapping -------------------------------------------------

    def test_string_t_no_sv_maps_to_text_field(self):
        algo = AlgoDef("A", [_make_param(type_="String_t", sv=[], default="hi")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        assert ctrl.get(f"{{{XSI_NS}}}type") == "lay:TextField_t"

    def test_supported_values_maps_to_dropdown(self):
        algo = AlgoDef("A", [_make_param(type_="String_t", sv=["A", "B"], default="A")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        assert ctrl.get(f"{{{XSI_NS}}}type") == "lay:DropDownList_t"

    def test_boolean_t_maps_to_checkbox(self):
        algo = AlgoDef("A", [_make_param(type_="Boolean_t", default="true")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        assert ctrl.get(f"{{{XSI_NS}}}type") == "lay:CheckBox_t"

    def test_int_t_maps_to_single_spinner(self):
        algo = AlgoDef("A", [_make_param(type_="Int_t", default="5")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        assert ctrl.get(f"{{{XSI_NS}}}type") == "lay:SingleSpinner_t"

    def test_float_t_maps_to_single_spinner(self):
        algo = AlgoDef("A", [_make_param(type_="Float_t", default="1.5")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        assert ctrl.get(f"{{{XSI_NS}}}type") == "lay:SingleSpinner_t"

    def test_utctimeonly_t_maps_to_clock(self):
        algo = AlgoDef("A", [_make_param(type_="UTCTimeOnly_t", default="09:30:00")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        assert ctrl.get(f"{{{XSI_NS}}}type") == "lay:Clock_t"

    # --- initValue correctness ------------------------------------------------

    def test_text_field_init_value_is_raw_string(self):
        algo = AlgoDef("A", [_make_param(type_="String_t", default="hello")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        assert ctrl.get("initValue") == "hello"

    def test_dropdown_init_value_is_enum_id_for_numeric_wire(self):
        # wireValue "1" → enumID "e_1" via _sanitize_enum_id
        algo = AlgoDef("A", [_make_param(type_="String_t", sv=["1", "2"], default="1")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        assert ctrl.get("initValue") == "e_1"

    def test_dropdown_init_value_letter_wire_value_unchanged(self):
        algo = AlgoDef("A", [_make_param(type_="String_t", sv=["MKT", "LMT"], default="MKT")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        assert ctrl.get("initValue") == "MKT"

    def test_checkbox_init_value_is_raw_string(self):
        algo = AlgoDef("A", [_make_param(type_="Boolean_t", default="true")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        assert ctrl.get("initValue") == "true"

    # --- DropDownList ListItem children ---------------------------------------

    def test_dropdown_has_correct_list_item_count(self):
        algo = AlgoDef("A", [_make_param(type_="String_t", sv=["A", "B"], default="A")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        assert len(ctrl.findall(_lqname("ListItem"))) == 2

    def test_dropdown_list_item_attributes(self):
        algo = AlgoDef("A", [_make_param(type_="String_t", sv=["MKT", "LMT"], default="MKT")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        items = ctrl.findall(_lqname("ListItem"))
        assert items[0].get("enumID") == "MKT"
        assert items[0].get("uiRep") == "MKT"
        assert items[1].get("enumID") == "LMT"
        assert items[1].get("uiRep") == "LMT"


# ---------------------------------------------------------------------------
# Build: minValue / maxValue on Parameter elements
# ---------------------------------------------------------------------------

def _get_param_elem(root):
    return _get_strategy(root).find(_qname("Parameter"))


class TestMinMaxOnParameter:
    def test_min_value_on_parameter(self):
        algo = AlgoDef("A", [_make_param(type_="Float_t", min_value="0", max_value="1", default="0.5")])
        root = build_fixatdl(algo)
        assert _get_param_elem(root).get("minValue") == "0"

    def test_max_value_on_parameter(self):
        algo = AlgoDef("A", [_make_param(type_="Float_t", min_value="0", max_value="1", default="0.5")])
        root = build_fixatdl(algo)
        assert _get_param_elem(root).get("maxValue") == "1"

    def test_no_min_max_when_absent(self):
        algo = AlgoDef("A", [_make_param(type_="Float_t", default="0.5")])
        root = build_fixatdl(algo)
        param = _get_param_elem(root)
        assert param.get("minValue") is None
        assert param.get("maxValue") is None

    def test_min_max_not_on_non_minmax_type(self):
        # Length_t is in _SPINNER_TYPES but NOT in _MINMAX_TYPES
        algo = AlgoDef("A", [_make_param(type_="Length_t", min_value="1", max_value="10", default="5")])
        root = build_fixatdl(algo)
        param = _get_param_elem(root)
        assert param.get("minValue") is None
        assert param.get("maxValue") is None


class TestIncrementOnSpinner:
    def test_increment_on_spinner_control(self):
        algo = AlgoDef("A", [_make_param(type_="Float_t", increment="0.01", default="0.5")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        assert ctrl.get("increment") == "0.01"

    def test_no_increment_on_non_spinner(self):
        algo = AlgoDef("A", [_make_param(type_="Boolean_t", increment="1", default="true")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        assert ctrl.get("increment") is None

    def test_layout_generated_for_increment_only(self):
        # increment set but no default_value — layout must still be generated
        algo = AlgoDef("A", [_make_param(type_="Float_t", increment="5")])
        root = build_fixatdl(algo)
        assert _get_strategy(root).find(f".//{_lqname('StrategyLayout')}") is not None

    def test_increment_not_on_non_spinner_type(self):
        # Boolean_t with increment — no increment on control
        algo = AlgoDef("A", [_make_param(type_="Boolean_t", increment="1", default="false")])
        root = build_fixatdl(algo)
        ctrl = _get_strategy(root).find(f".//{_lqname('Control')}")
        assert ctrl.get("increment") is None
