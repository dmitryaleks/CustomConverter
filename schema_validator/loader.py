"""Parse an ATDL XML document and build a DocumentContext for validation."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from .models import (
    CORE_NS, VAL_NS, LAY_NS, FLOW_NS, XSI_NS, XSD_NS,
    ControlCtx, CountryRegionCtx, DocumentContext, EditCtx, EditRefCtx,
    EnumPairCtx, ListItemCtx, ParameterCtx, StrategyCtx,
)


def _tag(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}"


def _xsi_type_local(elem: etree._Element) -> str | None:
    """Return the local name of xsi:type, e.g. 'String_t' from 'core:String_t'."""
    full = elem.get(_tag(XSI_NS, "type"), "")
    if not full:
        return None
    return full.split(":")[-1]


def _line(elem: etree._Element) -> int | None:
    try:
        return elem.sourceline
    except AttributeError:
        return None


# ---------------------------------------------------------------------------
# Edit / EditRef helpers
# ---------------------------------------------------------------------------

def _build_edit_ctx(edit_elem: etree._Element) -> EditCtx:
    child_edits = edit_elem.findall(_tag(VAL_NS, "Edit"))
    child_edit_refs = edit_elem.findall(_tag(VAL_NS, "EditRef"))
    return EditCtx(
        edit_id=edit_elem.get("id"),
        field=edit_elem.get("field"),
        field2=edit_elem.get("field2"),
        value=edit_elem.get("value"),
        operator=edit_elem.get("operator"),
        logic_operator=edit_elem.get("logicOperator"),
        has_child_edits=bool(child_edits),
        has_child_edit_refs=bool(child_edit_refs),
        child_edit_ref_ids=[r.get("id", "") for r in child_edit_refs if r.get("id")],
        line=_line(edit_elem),
    )


def _collect_edits_recursive(parent: etree._Element) -> list[EditCtx]:
    """Collect all Edit elements at any depth under *parent*."""
    results: list[EditCtx] = []
    for edit_elem in parent.findall(_tag(VAL_NS, "Edit")):
        results.append(_build_edit_ctx(edit_elem))
        results.extend(_collect_edits_recursive(edit_elem))
    return results


def _collect_edit_refs(
    parent: etree._Element,
    in_state_rule: bool = False,
) -> list[EditRefCtx]:
    """Collect all EditRef elements at any depth under *parent*."""
    results: list[EditRefCtx] = []
    for child in parent:
        ns_local = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""
        child_ns = etree.QName(child.tag).namespace if isinstance(child.tag, str) else ""
        if child_ns == VAL_NS and ns_local == "EditRef":
            ref_id = child.get("id", "")
            if ref_id:
                results.append(EditRefCtx(ref_id=ref_id, in_state_rule=in_state_rule, line=_line(child)))
        elif child_ns == FLOW_NS and ns_local == "StateRule":
            results.extend(_collect_edit_refs(child, in_state_rule=True))
        elif child_ns == VAL_NS and ns_local in ("Edit", "StrategyEdit"):
            results.extend(_collect_edit_refs(child, in_state_rule=in_state_rule))
        elif child_ns == LAY_NS and ns_local in ("Control", "StrategyPanel", "StrategyLayout"):
            results.extend(_collect_edit_refs(child, in_state_rule=in_state_rule))
    return results


# ---------------------------------------------------------------------------
# Parameter helper
# ---------------------------------------------------------------------------

def _build_parameter_ctx(param_elem: etree._Element) -> ParameterCtx:
    fix_tag_str = param_elem.get("fixTag")
    fix_tag: int | None = int(fix_tag_str) if fix_tag_str and fix_tag_str.isdigit() else None

    enum_pairs = [
        EnumPairCtx(
            enum_id=ep.get("enumID", ""),
            wire_value=ep.get("wireValue", ""),
            line=_line(ep),
        )
        for ep in param_elem.findall(_tag(CORE_NS, "EnumPair"))
    ]

    return ParameterCtx(
        name=param_elem.get("name", ""),
        xsi_type_local=_xsi_type_local(param_elem),
        fix_tag=fix_tag,
        const=param_elem.get("const", "false").lower() == "true",
        use=param_elem.get("use"),
        const_value=param_elem.get("constValue"),
        min_value=param_elem.get("minValue"),
        max_value=param_elem.get("maxValue"),
        min_length=param_elem.get("minLength"),
        max_length=param_elem.get("maxLength"),
        local_mkt_tz=param_elem.get("localMktTz"),
        enum_pairs=enum_pairs,
        line=_line(param_elem),
    )


# ---------------------------------------------------------------------------
# Control helper
# ---------------------------------------------------------------------------

def _build_control_ctx(ctrl_elem: etree._Element) -> ControlCtx:
    list_items = [
        ListItemCtx(
            enum_id=li.get("enumID"),
            ui_rep=li.get("uiRep", ""),
        )
        for li in ctrl_elem.findall(_tag(LAY_NS, "ListItem"))
    ]

    # Collect EditRef ids from StateRule children (REF-04)
    state_rule_edit_ref_ids: list[str] = []
    for sr in ctrl_elem.findall(_tag(FLOW_NS, "StateRule")):
        for er in sr.findall(_tag(VAL_NS, "EditRef")):
            ref_id = er.get("id")
            if ref_id:
                state_rule_edit_ref_ids.append(ref_id)
        for nested_edit in sr.findall(_tag(VAL_NS, "Edit")):
            for er in nested_edit.findall(f".//{_tag(VAL_NS, 'EditRef')}"):
                ref_id = er.get("id")
                if ref_id:
                    state_rule_edit_ref_ids.append(ref_id)

    return ControlCtx(
        ctrl_id=ctrl_elem.get("ID", ""),
        parameter_ref=ctrl_elem.get("parameterRef"),
        xsi_type_local=_xsi_type_local(ctrl_elem),
        init_value=ctrl_elem.get("initValue"),
        increment=ctrl_elem.get("increment"),
        inner_increment=ctrl_elem.get("innerIncrement"),
        outer_increment=ctrl_elem.get("outerIncrement"),
        list_items=list_items,
        state_rule_edit_ref_ids=state_rule_edit_ref_ids,
        line=_line(ctrl_elem),
    )


# ---------------------------------------------------------------------------
# Strategy helper
# ---------------------------------------------------------------------------

def _build_strategy_ctx(strat_elem: etree._Element) -> StrategyCtx:
    ctx = StrategyCtx(name=strat_elem.get("name", ""), line=_line(strat_elem))

    # Parameters (direct + inside RepeatingGroup)
    for param_elem in strat_elem.findall(_tag(CORE_NS, "Parameter")):
        p = _build_parameter_ctx(param_elem)
        ctx.all_param_names.append(p.name)
        ctx.parameters[p.name] = p
        if p.fix_tag is not None:
            ctx.all_fix_tags.append(p.fix_tag)

    for rg in strat_elem.findall(_tag(CORE_NS, "RepeatingGroup")):
        for param_elem in rg.findall(_tag(CORE_NS, "Parameter")):
            p = _build_parameter_ctx(param_elem)
            ctx.all_param_names.append(p.name)
            ctx.parameters[p.name] = p
            if p.fix_tag is not None:
                ctx.all_fix_tags.append(p.fix_tag)

    # Strategy-level Edit elements
    for edit_elem in strat_elem.findall(_tag(VAL_NS, "Edit")):
        edit_ctx = _build_edit_ctx(edit_elem)
        ctx.all_edits.append(edit_ctx)
        if edit_ctx.edit_id:
            ctx.edits_by_id[edit_ctx.edit_id] = edit_ctx
        # Recurse into nested edits
        for nested in _collect_edits_recursive(edit_elem):
            ctx.all_edits.append(nested)
            if nested.edit_id:
                ctx.edits_by_id[nested.edit_id] = nested

    # StrategyEdit elements (collect their nested edits and edit refs)
    for se in strat_elem.findall(_tag(VAL_NS, "StrategyEdit")):
        for nested in _collect_edits_recursive(se):
            ctx.all_edits.append(nested)
            if nested.edit_id:
                ctx.edits_by_id[nested.edit_id] = nested

    # All EditRef ids in this strategy (for REF-03/04 checks)
    ctx.all_edit_refs = _collect_edit_refs(strat_elem)

    # Controls (via StrategyLayout)
    layout = strat_elem.find(_tag(LAY_NS, "StrategyLayout"))
    if layout is not None:
        for ctrl_elem in layout.findall(f".//{_tag(LAY_NS, 'Control')}"):
            ctx.controls.append(_build_control_ctx(ctrl_elem))

    # Geographic scope
    regions_elem = strat_elem.find(_tag(CORE_NS, "Regions"))
    if regions_elem is not None:
        for region_elem in regions_elem.findall(_tag(CORE_NS, "Region")):
            region_name = region_elem.get("name", "")
            for country_elem in region_elem.findall(_tag(CORE_NS, "Country")):
                code = country_elem.get("CountryCode", "")
                ctx.country_regions.append(
                    CountryRegionCtx(region_name=region_name, country_code=code, line=_line(country_elem))
                )

    markets_elem = strat_elem.find(_tag(CORE_NS, "Markets"))
    if markets_elem is not None:
        for market_elem in markets_elem.findall(_tag(CORE_NS, "Market")):
            mic = market_elem.get("MICCode", "")
            ctx.market_codes.append((mic, _line(market_elem)))

    return ctx


# ---------------------------------------------------------------------------
# Timezone and region loaders
# ---------------------------------------------------------------------------

def _load_timezones(tz_xsd_path: Path) -> frozenset[str]:
    """Extract LocalMktTz_t enumeration values from atdl-timezones-1-1.xsd."""
    if not tz_xsd_path.exists():
        return frozenset()
    xs = {"xs": XSD_NS}
    doc = etree.parse(str(tz_xsd_path))
    simple_type = doc.find(
        f".//{{{XSD_NS}}}simpleType[@name='LocalMktTz_t']"
    )
    if simple_type is None:
        return frozenset()
    return frozenset(
        e.get("value", "").strip()
        for e in simple_type.findall(f".//{{{XSD_NS}}}enumeration")
    )


def _load_countries_by_region(regions_xsd_path: Path) -> dict[str, frozenset[str]]:
    """Extract country code enumerations per region from atdl-regions-1-1.xsd."""
    if not regions_xsd_path.exists():
        return {}
    doc = etree.parse(str(regions_xsd_path))
    result: dict[str, frozenset[str]] = {}
    for region_name in ("TheAmericas", "EuropeMiddleEastAfrica", "AsiaPacificJapan"):
        elem = doc.find(f".//{{{XSD_NS}}}element[@name='{region_name}']")
        if elem is not None:
            enums = elem.findall(f".//{{{XSD_NS}}}enumeration")
            result[region_name] = frozenset(e.get("value", "").strip() for e in enums)
    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def load(xml_path: str | Path, schemas_dir: str | Path) -> DocumentContext:
    """Parse *xml_path* and return a fully indexed :class:`DocumentContext`.

    Args:
        xml_path: Path to the ATDL XML document.
        schemas_dir: Directory containing the ATDL XSD files.

    Returns:
        A :class:`DocumentContext` ready for Phase 2 and Phase 3 checks.
    """
    xml_path = Path(xml_path)
    schemas_dir = Path(schemas_dir)

    valid_timezones = _load_timezones(schemas_dir / "atdl-timezones-1-1.xsd")
    valid_countries_by_region = _load_countries_by_region(schemas_dir / "atdl-regions-1-1.xsd")

    doc = etree.parse(str(xml_path))
    root = doc.getroot()

    ctx = DocumentContext(
        root=root,
        valid_timezones=valid_timezones,
        valid_countries_by_region=valid_countries_by_region,
        xml_path=xml_path,
    )

    # strategyIdentifierTag
    sit = root.get("strategyIdentifierTag")
    if sit and sit.isdigit():
        ctx.strategy_identifier_tag = int(sit)

    # Global Edit elements at Strategies level
    for edit_elem in root.findall(_tag(VAL_NS, "Edit")):
        edit_ctx = _build_edit_ctx(edit_elem)
        ctx.all_global_edits.append(edit_ctx)
        if edit_ctx.edit_id:
            ctx.global_edits_by_id[edit_ctx.edit_id] = edit_ctx
        for nested in _collect_edits_recursive(edit_elem):
            ctx.all_global_edits.append(nested)
            if nested.edit_id:
                ctx.global_edits_by_id[nested.edit_id] = nested

    # Strategy elements
    for strat_elem in root.findall(_tag(CORE_NS, "Strategy")):
        strat_ctx = _build_strategy_ctx(strat_elem)
        ctx.strategies[strat_ctx.name] = strat_ctx
        ctx.strategy_list.append(strat_ctx)

    return ctx
