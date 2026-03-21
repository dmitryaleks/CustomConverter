"""Tests for source_converter.transformers."""

from __future__ import annotations

import pytest

from source_converter.transformers import (
    apply,
    normalize_boolean,
    pad_time,
    strip_percent,
)


class TestPadTime:
    def test_hm_padded(self):
        assert pad_time("9:30") == "09:30:00"

    def test_hhmm_padded(self):
        assert pad_time("09:30") == "09:30:00"

    def test_full_unchanged(self):
        assert pad_time("09:30:00") == "09:30:00"

    def test_midnight(self):
        assert pad_time("0:00") == "00:00:00"

    def test_non_time_unchanged(self):
        assert pad_time("not-a-time") == "not-a-time"

    def test_whitespace_stripped(self):
        assert pad_time("  9:30  ") == "09:30:00"


class TestNormalizeBoolean:
    def test_lowercase_true(self):
        assert normalize_boolean("true") == "true"

    def test_title_true(self):
        assert normalize_boolean("True") == "true"

    def test_uppercase_true(self):
        assert normalize_boolean("TRUE") == "true"

    def test_yes_is_true(self):
        assert normalize_boolean("yes") == "true"

    def test_one_is_true(self):
        assert normalize_boolean("1") == "true"

    def test_false_is_false(self):
        assert normalize_boolean("false") == "false"

    def test_zero_is_false(self):
        assert normalize_boolean("0") == "false"

    def test_arbitrary_is_false(self):
        assert normalize_boolean("maybe") == "false"


class TestStripPercent:
    def test_strips_percent(self):
        assert strip_percent("10%") == "10"

    def test_no_percent_unchanged(self):
        assert strip_percent("10") == "10"

    def test_whitespace_stripped(self):
        assert strip_percent("  15%  ") == "15"


class TestApply:
    def test_apply_pad_time(self):
        assert apply("9:30", "pad_time") == "09:30:00"

    def test_apply_normalize_boolean(self):
        assert apply("yes", "normalize_boolean") == "true"

    def test_apply_strip_percent(self):
        assert apply("20%", "strip_percent") == "20"

    def test_apply_unknown_passthrough(self):
        assert apply("hello", "nonexistent_transformer") == "hello"
