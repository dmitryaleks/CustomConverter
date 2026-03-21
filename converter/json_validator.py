"""Validate a proprietary ATDL JSON algo descriptor file.

Rules
-----
JSON-01  Root must be a JSON object.
JSON-02  Root object must have exactly one key (the algo name).
JSON-03  Algo name must be a non-empty string.
JSON-04  Algo value must be a JSON object containing a "PARAMETERS" key.
JSON-05  "PARAMETERS" must be a JSON array.
JSON-06  "PARAMETERS" array must not be empty.
JSON-07  Each entry in "PARAMETERS" must be a single-key JSON object.
JSON-08  The parameter body (value of the single key) must be a JSON object.
JSON-09  "NAME" field is required in each parameter body.
JSON-10  "TYPE" field is required in each parameter body.
JSON-11  "FIXTAGNUMBER" field is required in each parameter body.
JSON-12  "NAME" must be a non-empty string.
JSON-13  "TYPE" must be a recognised FIXATDL 1.1 parameter type.
JSON-14  "FIXTAGNUMBER" must be a positive integer.
JSON-15  "NAME" values must be unique within the strategy.
JSON-16  "FIXTAGNUMBER" values must be unique within the strategy.
JSON-17  "DESCRIPTION", if present, must be a string.
JSON-18  "SUPPORTED_VALUES", if present, must be a JSON array.
JSON-19  Each item in "SUPPORTED_VALUES" must be a non-empty string.
JSON-20  "NAME" must be a valid FIXATDL identifier: a letter followed by
         letters, digits, or underscores (pattern [A-Za-z][A-Za-z0-9_]*).
JSON-21  "FIXTAGNUMBER" in the standard FIX range (1–4999) produces a
         warning; custom algo parameters should use values ≥ 5000.
JSON-22  "SUPPORTED_VALUES" items must be unique within a parameter.
JSON-23  For "Boolean_t" parameters, "SUPPORTED_VALUES" must be absent or
         contain exactly 2 entries (true-wire and false-wire values).
JSON-24  For "Char_t" and "MultipleCharValue_t" parameters, each
         "SUPPORTED_VALUES" entry must be a single character.
JSON-25  Unrecognised fields in a parameter body produce a warning.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Complete set of recognised FIXATDL 1.1 parameter types
# ---------------------------------------------------------------------------

VALID_TYPES: frozenset[str] = frozenset({
    "Amt_t",
    "Boolean_t",
    "Char_t",
    "Country_t",
    "Currency_t",
    "Data_t",
    "Exchange_t",
    "Float_t",
    "Int_t",
    "Language_t",
    "Length_t",
    "LocalMktTime_t",
    "Month-Year_t",
    "MultipleCharValue_t",
    "MultipleStringValue_t",
    "NumInGroup_t",
    "Numeric_t",
    "Percentage_t",
    "Price_t",
    "PriceOffset_t",
    "Qty_t",
    "SeqNum_t",
    "String_t",
    "TagNum_t",
    "UTCDate_t",
    "UTCTimeOnly_t",
    "UTCTimeStamp_t",
})

# Known fields in a parameter body (all others produce a JSON-25 warning).
_KNOWN_PARAM_FIELDS: frozenset[str] = frozenset({
    "NAME",
    "TYPE",
    "FIXTAGNUMBER",
    "DESCRIPTION",
    "SUPPORTED_VALUES",
})

# Pattern for a valid FIXATDL parameter identifier (JSON-20).
_NAME_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    """A single validation finding."""

    severity: str   # "error" | "warning"
    rule_id: str    # e.g. "JSON-13"
    message: str
    path: str = field(default="")  # JSON path to the offending element


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _err(rule_id: str, message: str, path: str = "") -> ValidationIssue:
    return ValidationIssue(severity="error", rule_id=rule_id,
                           message=message, path=path)


def _warn(rule_id: str, message: str, path: str = "") -> ValidationIssue:
    return ValidationIssue(severity="warning", rule_id=rule_id,
                           message=message, path=path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_data(data: Any) -> list[ValidationIssue]:
    """Validate an already-parsed JSON value.

    Args:
        data: The decoded JSON value (e.g. from ``json.load()``).

    Returns:
        A list of :class:`ValidationIssue` objects.  An empty list means
        the data is valid.
    """
    issues: list[ValidationIssue] = []

    # JSON-01 ----------------------------------------------------------------
    if not isinstance(data, dict):
        issues.append(_err(
            "JSON-01",
            f"Root must be a JSON object; got {type(data).__name__}",
        ))
        return issues  # cannot proceed

    # JSON-02 ----------------------------------------------------------------
    if len(data) == 0:
        issues.append(_err(
            "JSON-02",
            "Root object must have exactly one key (the algo name); got 0 keys",
        ))
        return issues

    if len(data) > 1:
        issues.append(_err(
            "JSON-02",
            f"Root object must have exactly one key (the algo name); "
            f"got {len(data)}: {list(data.keys())}",
        ))
        return issues

    algo_name, algo_body = next(iter(data.items()))

    # JSON-03 ----------------------------------------------------------------
    if not isinstance(algo_name, str) or not algo_name.strip():
        issues.append(_err(
            "JSON-03",
            f"Algo name must be a non-empty string; got {algo_name!r}",
        ))
        return issues

    base = algo_name

    # JSON-04 ----------------------------------------------------------------
    if not isinstance(algo_body, dict):
        issues.append(_err(
            "JSON-04",
            f"Algo '{algo_name}' value must be a JSON object; "
            f"got {type(algo_body).__name__}",
            base,
        ))
        return issues

    if "PARAMETERS" not in algo_body:
        issues.append(_err(
            "JSON-04",
            f"Algo '{algo_name}' must have a 'PARAMETERS' key",
            base,
        ))
        return issues

    params_raw = algo_body["PARAMETERS"]

    # JSON-05 ----------------------------------------------------------------
    if not isinstance(params_raw, list):
        issues.append(_err(
            "JSON-05",
            f"'PARAMETERS' must be a JSON array; got {type(params_raw).__name__}",
            f"{base}.PARAMETERS",
        ))
        return issues

    # JSON-06 ----------------------------------------------------------------
    if len(params_raw) == 0:
        issues.append(_err(
            "JSON-06",
            "'PARAMETERS' array must not be empty",
            f"{base}.PARAMETERS",
        ))
        # Continue — no individual params to check

    seen_names: dict[str, int] = {}   # name  → first-seen index
    seen_tags:  dict[int,  int] = {}  # tag   → first-seen index

    for idx, item in enumerate(params_raw):
        item_path = f"{base}.PARAMETERS[{idx}]"

        # JSON-07 ------------------------------------------------------------
        if not isinstance(item, dict):
            issues.append(_err(
                "JSON-07",
                f"Each PARAMETERS entry must be a JSON object; "
                f"got {type(item).__name__}",
                item_path,
            ))
            continue

        if len(item) != 1:
            issues.append(_err(
                "JSON-07",
                f"Each PARAMETERS entry must have exactly one key; "
                f"got {len(item)}: {list(item.keys())}",
                item_path,
            ))
            continue

        param_key, param_body = next(iter(item.items()))
        param_path = f"{item_path}.{param_key}"

        # JSON-08 ------------------------------------------------------------
        if not isinstance(param_body, dict):
            issues.append(_err(
                "JSON-08",
                f"Parameter body must be a JSON object; "
                f"got {type(param_body).__name__}",
                param_path,
            ))
            continue

        # JSON-09 / JSON-10 / JSON-11 ----------------------------------------
        for req_field, rule_id in (
            ("NAME",        "JSON-09"),
            ("TYPE",        "JSON-10"),
            ("FIXTAGNUMBER","JSON-11"),
        ):
            if req_field not in param_body:
                issues.append(_err(
                    rule_id,
                    f"Required field '{req_field}' is missing",
                    param_path,
                ))

        # JSON-12 — NAME must be a non-empty string --------------------------
        if "NAME" in param_body:
            name_val = param_body["NAME"]
            if not isinstance(name_val, str) or not name_val.strip():
                issues.append(_err(
                    "JSON-12",
                    f"'NAME' must be a non-empty string; got {name_val!r}",
                    f"{param_path}.NAME",
                ))
            else:
                # JSON-15 — NAME uniqueness ----------------------------------
                if name_val in seen_names:
                    issues.append(_err(
                        "JSON-15",
                        f"Duplicate parameter NAME '{name_val}' "
                        f"(first seen at index {seen_names[name_val]})",
                        f"{param_path}.NAME",
                    ))
                else:
                    seen_names[name_val] = idx

                # JSON-20 — NAME must match FIXATDL identifier pattern -------
                if not _NAME_PATTERN.fullmatch(name_val):
                    issues.append(_err(
                        "JSON-20",
                        f"'NAME' must be a valid FIXATDL identifier (letter "
                        f"followed by letters, digits, or underscores); "
                        f"got {name_val!r}",
                        f"{param_path}.NAME",
                    ))

        # JSON-13 — TYPE must be a recognised FIXATDL type -------------------
        if "TYPE" in param_body:
            type_val = param_body["TYPE"]
            if not isinstance(type_val, str):
                issues.append(_err(
                    "JSON-13",
                    f"'TYPE' must be a string; got {type(type_val).__name__}",
                    f"{param_path}.TYPE",
                ))
            elif type_val not in VALID_TYPES:
                issues.append(_err(
                    "JSON-13",
                    f"'TYPE' value '{type_val}' is not a recognised FIXATDL 1.1 "
                    f"parameter type. Valid types: {', '.join(sorted(VALID_TYPES))}",
                    f"{param_path}.TYPE",
                ))

        # JSON-14 — FIXTAGNUMBER must be a positive integer ------------------
        if "FIXTAGNUMBER" in param_body:
            tag_val = param_body["FIXTAGNUMBER"]
            if not isinstance(tag_val, int) or isinstance(tag_val, bool):
                issues.append(_err(
                    "JSON-14",
                    f"'FIXTAGNUMBER' must be an integer; "
                    f"got {type(tag_val).__name__}",
                    f"{param_path}.FIXTAGNUMBER",
                ))
            elif tag_val <= 0:
                issues.append(_err(
                    "JSON-14",
                    f"'FIXTAGNUMBER' must be a positive integer; got {tag_val}",
                    f"{param_path}.FIXTAGNUMBER",
                ))
            else:
                # JSON-16 — FIXTAGNUMBER uniqueness --------------------------
                if tag_val in seen_tags:
                    issues.append(_err(
                        "JSON-16",
                        f"Duplicate FIXTAGNUMBER {tag_val} "
                        f"(first seen at index {seen_tags[tag_val]})",
                        f"{param_path}.FIXTAGNUMBER",
                    ))
                else:
                    seen_tags[tag_val] = idx

                # JSON-21 — warn if tag is in standard FIX range (1–4999) ---
                if tag_val < 5000:
                    issues.append(_warn(
                        "JSON-21",
                        f"'FIXTAGNUMBER' {tag_val} is in the standard FIX tag "
                        f"range (1–4999); custom algo parameters should use "
                        f"values ≥ 5000",
                        f"{param_path}.FIXTAGNUMBER",
                    ))

        # JSON-17 — DESCRIPTION must be a string (if present) ---------------
        if "DESCRIPTION" in param_body:
            desc_val = param_body["DESCRIPTION"]
            if not isinstance(desc_val, str):
                issues.append(_err(
                    "JSON-17",
                    f"'DESCRIPTION' must be a string; "
                    f"got {type(desc_val).__name__}",
                    f"{param_path}.DESCRIPTION",
                ))

        # JSON-18 / JSON-19 / JSON-22 / JSON-23 / JSON-24 — SUPPORTED_VALUES -
        if "SUPPORTED_VALUES" in param_body:
            sv = param_body["SUPPORTED_VALUES"]
            if not isinstance(sv, list):
                issues.append(_err(
                    "JSON-18",
                    f"'SUPPORTED_VALUES' must be a JSON array; "
                    f"got {type(sv).__name__}",
                    f"{param_path}.SUPPORTED_VALUES",
                ))
            else:
                seen_sv: set[str] = set()
                for sv_idx, sv_item in enumerate(sv):
                    sv_path = f"{param_path}.SUPPORTED_VALUES[{sv_idx}]"
                    if not isinstance(sv_item, str):
                        issues.append(_err(
                            "JSON-19",
                            f"Each SUPPORTED_VALUES item must be a string; "
                            f"got {type(sv_item).__name__}",
                            sv_path,
                        ))
                    elif not sv_item:
                        issues.append(_err(
                            "JSON-19",
                            "Each SUPPORTED_VALUES item must be a non-empty string",
                            sv_path,
                        ))
                    else:
                        # JSON-22 — uniqueness within parameter --------------
                        if sv_item in seen_sv:
                            issues.append(_err(
                                "JSON-22",
                                f"Duplicate SUPPORTED_VALUES entry {sv_item!r}",
                                sv_path,
                            ))
                        else:
                            seen_sv.add(sv_item)

                # JSON-23 — Boolean_t must have 0 or 2 SUPPORTED_VALUES ------
                param_type = param_body.get("TYPE")
                if isinstance(param_type, str) and param_type == "Boolean_t":
                    if len(sv) not in (0, 2):
                        issues.append(_err(
                            "JSON-23",
                            f"'Boolean_t' SUPPORTED_VALUES must contain exactly "
                            f"2 entries (true-wire and false-wire values), or be "
                            f"omitted; got {len(sv)}",
                            f"{param_path}.SUPPORTED_VALUES",
                        ))

                # JSON-24 — Char_t / MultipleCharValue_t: single-char values -
                if isinstance(param_type, str) and param_type in (
                    "Char_t", "MultipleCharValue_t"
                ):
                    for sv_idx, sv_item in enumerate(sv):
                        if isinstance(sv_item, str) and sv_item and len(sv_item) != 1:
                            issues.append(_err(
                                "JSON-24",
                                f"Each SUPPORTED_VALUES entry for '{param_type}' "
                                f"must be a single character; got {sv_item!r} "
                                f"(length {len(sv_item)})",
                                f"{param_path}.SUPPORTED_VALUES[{sv_idx}]",
                            ))

        # JSON-25 — warn on unrecognised parameter body fields ---------------
        for extra_key in param_body:
            if extra_key not in _KNOWN_PARAM_FIELDS:
                issues.append(_warn(
                    "JSON-25",
                    f"Unrecognised field '{extra_key}' in parameter body",
                    f"{param_path}.{extra_key}",
                ))

    return issues


def validate_json(path: str | Path) -> list[ValidationIssue]:
    """Load and validate a JSON algo descriptor file.

    Args:
        path: Path to the JSON file.

    Returns:
        A list of :class:`ValidationIssue` objects.  An empty list means
        the file is valid.

    Raises:
        FileNotFoundError: if *path* does not exist.
        ValueError: if the file content is not valid JSON.
    """
    path = Path(path)
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise FileNotFoundError(f"Input file not found: {path}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    return validate_data(data)
