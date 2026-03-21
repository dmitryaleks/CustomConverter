"""Tests for source_converter.type_mapper.TypeMapper."""

from __future__ import annotations

import pytest
from pathlib import Path

from source_converter.type_mapper import TypeMapper, DEFAULT_TYPE_MAP
from converter.json_validator import VALID_TYPES


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fresh() -> TypeMapper:
    """Return a TypeMapper loaded from the default config."""
    return TypeMapper()


# ─────────────────────────────────────────────────────────────────────────────
# Known mappings
# ─────────────────────────────────────────────────────────────────────────────

class TestKnownMappings:
    def test_price(self):
        assert _fresh().map("price") == "Price_t"

    def test_double(self):
        assert _fresh().map("double") == "Float_t"

    def test_float(self):
        assert _fresh().map("float") == "Float_t"

    def test_integer(self):
        assert _fresh().map("integer") == "Int_t"

    def test_int(self):
        assert _fresh().map("int") == "Int_t"

    def test_string(self):
        assert _fresh().map("string") == "String_t"

    def test_boolean(self):
        assert _fresh().map("boolean") == "Boolean_t"

    def test_bool(self):
        assert _fresh().map("bool") == "Boolean_t"

    def test_date(self):
        assert _fresh().map("date") == "UTCDate_t"

    def test_datetime(self):
        assert _fresh().map("datetime") == "UTCTimeStamp_t"

    def test_time(self):
        assert _fresh().map("time") == "UTCTimeOnly_t"

    def test_qty(self):
        assert _fresh().map("qty") == "Qty_t"

    def test_quantity(self):
        assert _fresh().map("quantity") == "Qty_t"

    def test_char(self):
        assert _fresh().map("char") == "Char_t"

    def test_percent(self):
        assert _fresh().map("percent") == "Percentage_t"


# ─────────────────────────────────────────────────────────────────────────────
# Case-insensitive lookup
# ─────────────────────────────────────────────────────────────────────────────

class TestCaseInsensitive:
    def test_uppercase(self):
        assert _fresh().map("PRICE") == "Price_t"

    def test_mixed_case(self):
        assert _fresh().map("PrIcE") == "Price_t"

    def test_title_case(self):
        assert _fresh().map("Integer") == "Int_t"

    def test_all_caps_string(self):
        assert _fresh().map("STRING") == "String_t"


# ─────────────────────────────────────────────────────────────────────────────
# Unknown / unmapped types
# ─────────────────────────────────────────────────────────────────────────────

class TestUnknownTypes:
    def test_unknown_returns_none(self):
        assert _fresh().map("Widget") is None

    def test_empty_string_returns_none(self):
        assert _fresh().map("") is None

    def test_fixatdl_type_used_directly_is_unmapped(self):
        # "Price_t" is not a *source* alias — it's the target type
        m = _fresh()
        result = m.map("Price_t")
        # Price_t is not a key in type_map.toml, so returns None
        assert result is None

    def test_partial_match_returns_none(self):
        assert _fresh().map("pric") is None


# ─────────────────────────────────────────────────────────────────────────────
# Coverage report
# ─────────────────────────────────────────────────────────────────────────────

class TestCoverageReport:
    def test_initial_report_empty(self):
        m = _fresh()
        report = m.coverage_report()
        assert report["mapped"] == []
        assert report["unmapped"] == []
        assert report["total_lookups"] == 0

    def test_mapped_entry_appears(self):
        m = _fresh()
        m.map("price")
        report = m.coverage_report()
        assert any(e["source"] == "price" and e["fixatdl"] == "Price_t"
                   for e in report["mapped"])

    def test_unmapped_entry_appears(self):
        m = _fresh()
        m.map("Widget")
        report = m.coverage_report()
        assert "Widget" in report["unmapped"]

    def test_total_lookups_counted(self):
        m = _fresh()
        m.map("price")
        m.map("Widget")
        m.map("int")
        assert m.coverage_report()["total_lookups"] == 3

    def test_multiple_mapped_types(self):
        m = _fresh()
        for src in ("price", "double", "string"):
            m.map(src)
        report = m.coverage_report()
        sources = [e["source"] for e in report["mapped"]]
        assert "price" in sources
        assert "double" in sources
        assert "string" in sources

    def test_repeated_unmapped_all_recorded(self):
        m = _fresh()
        m.map("foo")
        m.map("foo")
        report = m.coverage_report()
        assert report["unmapped"].count("foo") == 2
        assert report["total_lookups"] == 2

    def test_mixed_mapped_and_unmapped(self):
        m = _fresh()
        m.map("int")
        m.map("exotic_type")
        report = m.coverage_report()
        assert any(e["source"] == "int" for e in report["mapped"])
        assert "exotic_type" in report["unmapped"]


# ─────────────────────────────────────────────────────────────────────────────
# Config loading
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigLoading:
    def test_missing_config_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            TypeMapper(config_path=tmp_path / "nonexistent.toml")

    def test_custom_config_path_accepted(self, tmp_path):
        config = tmp_path / "custom.toml"
        config.write_text('[types]\nfoo = "String_t"\n', encoding="utf-8")
        m = TypeMapper(config_path=config)
        assert m.map("foo") == "String_t"

    def test_custom_config_other_keys_unknown(self, tmp_path):
        config = tmp_path / "custom.toml"
        config.write_text('[types]\nfoo = "String_t"\n', encoding="utf-8")
        m = TypeMapper(config_path=config)
        assert m.map("price") is None  # not in this custom config

    def test_empty_types_table(self, tmp_path):
        config = tmp_path / "empty.toml"
        config.write_text("[types]\n", encoding="utf-8")
        m = TypeMapper(config_path=config)
        assert m.map("price") is None
        assert m.coverage_report()["total_lookups"] == 1

    def test_default_config_path_constant(self):
        assert DEFAULT_TYPE_MAP.exists()


# ─────────────────────────────────────────────────────────────────────────────
# Cross-check: all default type_map.toml values are in VALID_TYPES
# ─────────────────────────────────────────────────────────────────────────────

class TestTypeMapValidity:
    def test_all_default_entries_are_valid_fixatdl_types(self):
        """Every value in type_map.toml must be a member of VALID_TYPES."""
        m = TypeMapper()
        for source_key, fixatdl_type in m.all_entries.items():
            assert fixatdl_type in VALID_TYPES, (
                f"type_map.toml entry '{source_key}' maps to '{fixatdl_type}' "
                f"which is NOT in VALID_TYPES"
            )
