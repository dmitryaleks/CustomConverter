"""Tests for converter.renderer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from lxml import etree

from converter.builder import CORE_NS, XSI_NS
from converter.renderer import render_html, write_html

_PARAM_TAG = f"{{{CORE_NS}}}Parameter"
_STRATEGY_TAG = f"{{{CORE_NS}}}Strategy"
_ENUM_PAIR_TAG = f"{{{CORE_NS}}}EnumPair"
_NSMAP = {None: CORE_NS, "xsi": XSI_NS, "core": CORE_NS}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_root(strategies: list[dict]) -> etree._Element:
    """Build a minimal <Strategies> element tree for testing.

    Each strategy dict may contain:
      name, providerID, version
      params: list of param dicts with keys:
        name, xsi_type, fix_tag, enum_values, description,
        constValue, use (optional)
    """
    root = etree.Element(f"{{{CORE_NS}}}Strategies", nsmap=_NSMAP)
    root.set("strategyIdentifierTag", "847")
    _DESC_TAG = f"{{{CORE_NS}}}Description"
    for s in strategies:
        strat = etree.SubElement(root, _STRATEGY_TAG)
        strat.set("name", s.get("name", "TestAlgo"))
        strat.set("providerID", s.get("providerID", "TestProvider"))
        strat.set("version", s.get("version", "1"))
        for p in s.get("params", []):
            elem = etree.SubElement(strat, _PARAM_TAG)
            elem.set("name", p["name"])
            elem.set(f"{{{XSI_NS}}}type", p.get("xsi_type", "core:String_t"))
            elem.set("fixTag", str(p.get("fix_tag", 5001)))
            if "constValue" in p:
                elem.set("constValue", p["constValue"])
            if "use" in p:
                elem.set("use", p["use"])
            # Add Description as child element (mirrors builder.py behaviour)
            if p.get("description"):
                desc_elem = etree.SubElement(elem, _DESC_TAG)
                desc_elem.text = p["description"]
            for ev in p.get("enum_values", []):
                ep = etree.SubElement(elem, _ENUM_PAIR_TAG)
                ep.set("enumID", ev)
                ep.set("wireValue", ev)
    return root


# ---------------------------------------------------------------------------
# render_html tests
# ---------------------------------------------------------------------------

class TestRenderHtml:
    def test_render_returns_html_doctype(self):
        root = _make_root([{"name": "MyAlgo", "params": []}])
        out = render_html(root)
        assert out.startswith("<!DOCTYPE html>")

    def test_strategy_name_in_title_and_h1(self):
        root = _make_root([{"name": "SpecialAlgo", "params": []}])
        out = render_html(root)
        # Title element contains the strategy name
        assert "<title>" in out
        title_start = out.index("<title>") + len("<title>")
        title_end = out.index("</title>")
        assert "SpecialAlgo" in out[title_start:title_end]
        # h1 element contains the strategy name
        assert "SpecialAlgo" in out
        h1_start = out.index("<h1>")
        h1_end = out.index("</h1>")
        assert "SpecialAlgo" in out[h1_start:h1_end]

    def test_string_param_renders_text_input(self):
        root = _make_root([{
            "name": "Algo",
            "params": [{"name": "myStr", "xsi_type": "core:String_t", "fix_tag": 5001}],
        }])
        out = render_html(root)
        assert 'type="text"' in out
        assert 'name="myStr"' in out

    def test_int_param_renders_number_input(self):
        root = _make_root([{
            "name": "Algo",
            "params": [{"name": "myInt", "xsi_type": "core:Int_t", "fix_tag": 5002}],
        }])
        out = render_html(root)
        assert 'type="number"' in out
        assert 'step="1"' in out
        assert 'name="myInt"' in out

    def test_enum_pairs_render_select(self):
        root = _make_root([{
            "name": "Algo",
            "params": [{
                "name": "myEnum",
                "xsi_type": "core:String_t",
                "fix_tag": 5003,
                "enum_values": ["A", "B", "C"],
            }],
        }])
        out = render_html(root)
        assert "<select" in out
        assert 'value="A"' in out
        assert 'value="B"' in out
        assert 'value="C"' in out

    def test_boolean_param_renders_checkbox(self):
        root = _make_root([{
            "name": "Algo",
            "params": [{"name": "myBool", "xsi_type": "core:Boolean_t", "fix_tag": 5004}],
        }])
        out = render_html(root)
        assert 'type="checkbox"' in out
        assert 'name="myBool"' in out

    def test_const_value_renders_readonly(self):
        root = _make_root([{
            "name": "Algo",
            "params": [{
                "name": "myConst",
                "xsi_type": "core:String_t",
                "fix_tag": 5005,
                "constValue": "FIXED",
            }],
        }])
        out = render_html(root)
        assert "readonly" in out
        assert 'value="FIXED"' in out

    def test_description_in_html(self):
        root = _make_root([{
            "name": "Algo",
            "params": [{
                "name": "myParam",
                "xsi_type": "core:String_t",
                "fix_tag": 5006,
                "description": "A helpful description",
            }],
        }])
        out = render_html(root)
        assert "A helpful description" in out
        assert 'class="description"' in out

    def test_write_html_creates_file(self, tmp_path: Path):
        root = _make_root([{"name": "Algo", "params": []}])
        out_path = tmp_path / "test.html"
        write_html(root, out_path)
        assert out_path.exists()
        content = out_path.read_text(encoding="utf-8")
        assert content.startswith("<!DOCTYPE html>")
        assert "Algo" in content

    def test_strategy_name_carried_on_fix_tag_5010(self):
        root = _make_root([{"name": "MyStrategy", "params": []}])
        out = render_html(root)
        assert 'data-fix-tag="5010"' in out
        assert 'value="MyStrategy"' in out
        assert 'name="StrategyName"' in out

    def test_fix_message_section_present(self):
        root = _make_root([{"name": "Algo", "params": []}])
        out = render_html(root)
        assert "Raw FIX 4.2 Message" in out
        assert 'id="fix-message"' in out
        assert 'id="fix-message-body"' in out
        assert 'id="fix-copy-btn"' in out

    def test_fix_tag_in_data_attribute_and_summary_header(self):
        root = _make_root([{
            "name": "Algo",
            "params": [{"name": "myParam", "xsi_type": "core:String_t", "fix_tag": 5099}],
        }])
        out = render_html(root)
        assert 'data-fix-tag="5099"' in out
        assert "FIX Tag Number" in out

    def test_custom_title_overrides_default(self):
        root = _make_root([{"name": "MyAlgo", "params": []}])
        out = render_html(root, title="Custom Title")
        title_start = out.index("<title>") + len("<title>")
        title_end = out.index("</title>")
        assert "Custom Title" in out[title_start:title_end]

    def test_float_param_renders_number_input_with_step_any(self):
        root = _make_root([{
            "name": "Algo",
            "params": [{"name": "myFloat", "xsi_type": "core:Float_t", "fix_tag": 5007}],
        }])
        out = render_html(root)
        assert 'type="number"' in out
        assert 'step="any"' in out
        assert 'name="myFloat"' in out

    def test_no_strategies_produces_valid_html(self):
        root = etree.Element(f"{{{CORE_NS}}}Strategies", nsmap=_NSMAP)
        root.set("strategyIdentifierTag", "847")
        out = render_html(root)
        assert out.startswith("<!DOCTYPE html>")
        assert "<title>ATDL Preview</title>" in out

    def test_multiple_enum_pairs_all_appear_as_options(self):
        values = ["BUY", "SELL", "SHORT"]
        root = _make_root([{
            "name": "Algo",
            "params": [{
                "name": "side",
                "xsi_type": "core:String_t",
                "fix_tag": 54,
                "enum_values": values,
            }],
        }])
        out = render_html(root)
        for v in values:
            assert f'value="{v}"' in out


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

class TestCliHtmlFlag:
    def test_cli_html_flag_writes_file(self, tmp_path: Path):
        from main import main

        json_data = {
            "TestAlgo": {
                "PARAMETERS": [
                    {
                        "P1": {
                            "NAME": "param1",
                            "DESCRIPTION": "Test parameter",
                            "TYPE": "String_t",
                            "FIXTAGNUMBER": 5001,
                        }
                    }
                ]
            }
        }
        input_json = tmp_path / "input.json"
        output_xml = tmp_path / "output.xml"
        output_html = tmp_path / "output.html"
        input_json.write_text(json.dumps(json_data), encoding="utf-8")

        result = main([
            str(input_json),
            str(output_xml),
            "--html", str(output_html),
        ])

        assert result == 0
        assert output_html.exists()
        content = output_html.read_text(encoding="utf-8")
        assert content.startswith("<!DOCTYPE html>")
        assert "TestAlgo" in content
        assert "param1" in content


# ---------------------------------------------------------------------------
# increment → HTML step attribute
# ---------------------------------------------------------------------------

class TestIncrementStep:
    """Verify that increment on a SingleSpinner_t Control becomes step= in HTML."""

    def _build_html(self, type_: str, increment: str | None = None,
                    default: str | None = None) -> str:
        from converter.builder import build_fixatdl
        from converter.parser import AlgoDef, ParameterDef
        param = ParameterDef(
            name="myParam", description="", type=type_, fix_tag=5001,
            supported_values=[], default_value=default, increment=increment,
        )
        root = build_fixatdl(AlgoDef("A", [param]))
        return render_html(root)

    def test_int_uses_increment_as_step(self):
        out = self._build_html("Int_t", increment="5", default="10")
        assert 'step="5"' in out

    def test_int_default_step_is_1(self):
        out = self._build_html("Int_t", default="10")
        assert 'step="1"' in out

    def test_float_increment_overrides_any_step(self):
        out = self._build_html("Float_t", increment="0.01", default="0.5")
        assert 'step="0.01"' in out

    def test_no_increment_float_step_is_any(self):
        out = self._build_html("Float_t", default="0.5")
        assert 'step="any"' in out

    def test_percentage_increment_sets_step(self):
        out = self._build_html("Percentage_t", increment="0.5", default="10")
        assert 'step="0.5"' in out

    def test_percentage_no_increment_step_is_any(self):
        out = self._build_html("Percentage_t", default="10")
        assert 'step="any"' in out
