"""Shared data model for the schema validator."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Namespace constants (used by all modules)
# ---------------------------------------------------------------------------

CORE_NS = "http://www.fixprotocol.org/ATDL-1-1/Core"
VAL_NS = "http://www.fixprotocol.org/ATDL-1-1/Validation"
LAY_NS = "http://www.fixprotocol.org/ATDL-1-1/Layout"
FLOW_NS = "http://www.fixprotocol.org/ATDL-1-1/Flow"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
XSD_NS = "http://www.w3.org/2001/XMLSchema"

# Control xsi:type local names that carry ListItem children
LIST_CONTROL_TYPES = frozenset({
    "DropDownList_t",
    "SingleSelectList_t",
    "MultiSelectList_t",
    "CheckBoxList_t",
    "EditableDropDownList_t",
    "RadioButtonGroup_t",
})

# Parameter xsi:type local names that support minValue/maxValue
NUMERIC_PARAM_TYPES = frozenset({
    "Int_t", "Float_t", "Qty_t", "Price_t",
    "PriceOffset_t", "Amt_t", "Percentage_t",
})

# Parameter xsi:type local names that support minLength/maxLength
STRING_PARAM_TYPES = frozenset({
    "String_t", "MultipleCharValue_t", "MultipleStringValue_t", "Data_t",
})

# Parameter xsi:type local names that carry localMktTz
TIME_PARAM_TYPES = frozenset({
    "UTCTimeStamp_t", "LocalMktTime_t",
})

# Control xsi:type local names that carry increment
SPINNER_CONTROL_TYPES = frozenset({
    "Slider_t", "SingleSpinner_t",
})


# ---------------------------------------------------------------------------
# Validation result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ValidationError:
    phase: int                   # 1, 2, or 3
    rule_id: str                 # e.g. "REF-01", "SEM-03", "XSD"
    message: str
    element: str | None = None   # element tag or XPath context
    line: int | None = None      # source line number


@dataclass
class ValidationResult:
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# Document context dataclasses (built by loader)
# ---------------------------------------------------------------------------

@dataclass
class EnumPairCtx:
    enum_id: str
    wire_value: str
    line: int | None = None


@dataclass
class ParameterCtx:
    name: str
    xsi_type_local: str | None    # e.g. "String_t"
    fix_tag: int | None
    const: bool                   # default False
    use: str | None               # "required" or "optional"
    const_value: str | None
    min_value: str | None
    max_value: str | None
    min_length: str | None
    max_length: str | None
    local_mkt_tz: str | None
    enum_pairs: list[EnumPairCtx] = field(default_factory=list)
    line: int | None = None


@dataclass
class ListItemCtx:
    enum_id: str | None
    ui_rep: str


@dataclass
class ControlCtx:
    ctrl_id: str
    parameter_ref: str | None
    xsi_type_local: str | None    # e.g. "DropDownList_t"
    init_value: str | None
    increment: str | None         # Slider_t, SingleSpinner_t
    inner_increment: str | None   # DoubleSpinner_t
    outer_increment: str | None   # DoubleSpinner_t
    list_items: list[ListItemCtx] = field(default_factory=list)
    state_rule_edit_ref_ids: list[str] = field(default_factory=list)
    line: int | None = None


@dataclass
class EditRefCtx:
    ref_id: str
    in_state_rule: bool = False
    line: int | None = None


@dataclass
class EditCtx:
    edit_id: str | None
    field: str | None
    field2: str | None
    value: str | None
    operator: str | None
    logic_operator: str | None
    has_child_edits: bool
    has_child_edit_refs: bool
    child_edit_ref_ids: list[str] = field(default_factory=list)
    line: int | None = None


@dataclass
class CountryRegionCtx:
    region_name: str
    country_code: str
    line: int | None = None


@dataclass
class StrategyCtx:
    name: str
    parameters: dict[str, ParameterCtx] = field(default_factory=dict)
    all_param_names: list[str] = field(default_factory=list)  # includes duplicates
    all_fix_tags: list[int] = field(default_factory=list)
    edits_by_id: dict[str, EditCtx] = field(default_factory=dict)
    all_edits: list[EditCtx] = field(default_factory=list)
    all_edit_refs: list[EditRefCtx] = field(default_factory=list)
    controls: list[ControlCtx] = field(default_factory=list)
    country_regions: list[CountryRegionCtx] = field(default_factory=list)
    market_codes: list[tuple[str, int | None]] = field(default_factory=list)
    line: int | None = None


@dataclass
class DocumentContext:
    root: Any                                         # lxml _Element
    strategies: dict[str, StrategyCtx] = field(default_factory=dict)
    strategy_list: list[StrategyCtx] = field(default_factory=list)
    global_edits_by_id: dict[str, EditCtx] = field(default_factory=dict)
    all_global_edits: list[EditCtx] = field(default_factory=list)
    strategy_identifier_tag: int | None = None
    valid_timezones: frozenset[str] = field(default_factory=frozenset)
    valid_countries_by_region: dict[str, frozenset[str]] = field(default_factory=dict)
    xml_path: Path = field(default_factory=Path)
