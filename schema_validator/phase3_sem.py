"""Phase 3 — semantic and business rule checks."""

from __future__ import annotations

from .models import (
    NUMERIC_PARAM_TYPES,
    SPINNER_CONTROL_TYPES,
    STRING_PARAM_TYPES,
    TIME_PARAM_TYPES,
    DocumentContext,
    StrategyCtx,
    ValidationError,
)


def _err(rule: str, msg: str, element: str | None = None, line: int | None = None) -> ValidationError:
    return ValidationError(phase=3, rule_id=rule, message=msg, element=element, line=line)


def _warn(rule: str, msg: str, element: str | None = None, line: int | None = None) -> ValidationError:
    return ValidationError(phase=3, rule_id=rule, message=msg, element=element, line=line)


def _try_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def run(ctx: DocumentContext) -> tuple[list[ValidationError], list[ValidationError]]:
    """Run all semantic checks.

    Returns:
        (errors, warnings) — both are lists of :class:`ValidationError`.
    """
    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []

    # --- SEM-05: unique Strategy names ---
    seen_names: set[str] = set()
    for strat in ctx.strategy_list:
        if strat.name in seen_names:
            errors.append(_err(
                "SEM-05",
                f"Duplicate Strategy name '{strat.name}'",
                element="Strategies/Strategy",
                line=strat.line,
            ))
        seen_names.add(strat.name)

    # --- SEM-16: strategyIdentifierTag must not collide with Parameter fixTags ---
    if ctx.strategy_identifier_tag is not None:
        sit = ctx.strategy_identifier_tag
        for strat in ctx.strategy_list:
            if sit in strat.all_fix_tags:
                errors.append(_err(
                    "SEM-16",
                    f"Strategies@strategyIdentifierTag={sit} collides with a "
                    f"Parameter@fixTag in strategy '{strat.name}'",
                    element="Strategies",
                ))

    # --- Per-strategy checks ---
    for strat in ctx.strategy_list:
        _check_strategy(strat, ctx, errors, warnings)

    return errors, warnings


def _check_strategy(
    strat: StrategyCtx,
    ctx: DocumentContext,
    errors: list[ValidationError],
    warnings: list[ValidationError],
) -> None:
    sname = strat.name

    # --- SEM-06: unique Parameter names within strategy ---
    seen_params: set[str] = set()
    for pname in strat.all_param_names:
        if pname in seen_params:
            errors.append(_err(
                "SEM-06",
                f"Strategy '{sname}': duplicate Parameter name '{pname}'",
                element=f"Strategy[@name='{sname}']/Parameter",
            ))
        seen_params.add(pname)

    # --- Per-parameter checks ---
    for param in strat.parameters.values():
        pref = f"Strategy '{sname}', Parameter '{param.name}'"
        pelem = f"Strategy[@name='{sname}']/Parameter[@name='{param.name}']"

        # SEM-01: unique wireValues within a Parameter
        wire_values = [ep.wire_value for ep in param.enum_pairs]
        seen_wv: set[str] = set()
        for wv in wire_values:
            if wv in seen_wv:
                errors.append(_err(
                    "SEM-01",
                    f"{pref}: duplicate EnumPair wireValue '{wv}'",
                    element=pelem,
                    line=param.line,
                ))
            seen_wv.add(wv)

        # SEM-02: unique enumIDs within a Parameter
        enum_ids = [ep.enum_id for ep in param.enum_pairs]
        seen_eid: set[str] = set()
        for eid in enum_ids:
            if eid in seen_eid:
                errors.append(_err(
                    "SEM-02",
                    f"{pref}: duplicate EnumPair enumID '{eid}'",
                    element=pelem,
                    line=param.line,
                ))
            seen_eid.add(eid)

        # SEM-03: const="true" and use="required" are contradictory
        if param.const and param.use == "required":
            errors.append(_err(
                "SEM-03",
                f"{pref}: const='true' and use='required' are contradictory",
                element=pelem,
                line=param.line,
            ))

        # SEM-04: const="true" without constValue (warning)
        if param.const and param.const_value is None:
            warnings.append(_warn(
                "SEM-04",
                f"{pref}: const='true' but no constValue attribute supplied",
                element=pelem,
                line=param.line,
            ))

        # SEM-07: localMktTz must be a valid IANA timezone
        # Strip trailing spaces when comparing: the XSD enum values carry a
        # trailing space (a known quirk), so both sides are normalised.
        if param.local_mkt_tz and ctx.valid_timezones:
            if param.local_mkt_tz.strip() not in ctx.valid_timezones:
                errors.append(_err(
                    "SEM-07",
                    f"{pref}: localMktTz='{param.local_mkt_tz}' is not a valid "
                    f"IANA timezone",
                    element=pelem,
                    line=param.line,
                ))

        # SEM-13: minValue <= maxValue for numeric types
        if param.xsi_type_local in NUMERIC_PARAM_TYPES:
            min_v = _try_float(param.min_value)
            max_v = _try_float(param.max_value)
            if min_v is not None and max_v is not None and min_v > max_v:
                errors.append(_err(
                    "SEM-13",
                    f"{pref}: minValue ({param.min_value}) > maxValue ({param.max_value})",
                    element=pelem,
                    line=param.line,
                ))

        # SEM-14: minLength <= maxLength for string types
        if param.xsi_type_local in STRING_PARAM_TYPES:
            try:
                min_l = int(param.min_length) if param.min_length is not None else None
                max_l = int(param.max_length) if param.max_length is not None else None
            except ValueError:
                min_l = max_l = None
            if min_l is not None and max_l is not None and min_l > max_l:
                errors.append(_err(
                    "SEM-14",
                    f"{pref}: minLength ({param.min_length}) > maxLength ({param.max_length})",
                    element=pelem,
                    line=param.line,
                ))

    # --- Geographic scope checks ---

    # SEM-08: Country codes must be valid for their declared region
    for cr in strat.country_regions:
        region_codes = ctx.valid_countries_by_region.get(cr.region_name)
        if region_codes and cr.country_code not in region_codes:
            errors.append(_err(
                "SEM-08",
                f"Strategy '{sname}': Country code '{cr.country_code}' is not valid "
                f"for region '{cr.region_name}'",
                element=f"Strategy[@name='{sname}']/Regions/Region[@name='{cr.region_name}']/Country",
                line=cr.line,
            ))

    # SEM-09: Market MICCode must be 4 uppercase alphanumeric chars
    import re
    _mic_pattern = re.compile(r"^[A-Z0-9]{4}$")
    for mic, mic_line in strat.market_codes:
        if not _mic_pattern.match(mic):
            errors.append(_err(
                "SEM-09",
                f"Strategy '{sname}': Market MICCode '{mic}' is invalid "
                f"(must match [A-Z0-9]{{4}})",
                element=f"Strategy[@name='{sname}']/Markets/Market",
                line=mic_line,
            ))

    # --- Edit checks (SEM-10, SEM-11, SEM-12) ---
    all_edits = ctx.all_global_edits + strat.all_edits
    for edit in all_edits:
        eref = f"Strategy '{sname}'" if edit in strat.all_edits else "Strategies (global)"

        # SEM-10: logicOperator requires children; operator forbids children
        if edit.logic_operator is not None:
            if not edit.has_child_edits and not edit.has_child_edit_refs:
                errors.append(_err(
                    "SEM-10",
                    f"{eref}: Edit with logicOperator='{edit.logic_operator}' has no "
                    f"child Edit or EditRef elements",
                    element="Edit",
                    line=edit.line,
                ))
        if edit.operator is not None:
            if edit.has_child_edits or edit.has_child_edit_refs:
                errors.append(_err(
                    "SEM-10",
                    f"{eref}: Edit with operator='{edit.operator}' must not have "
                    f"child Edit or EditRef elements",
                    element="Edit",
                    line=edit.line,
                ))

        # SEM-11: field2 and value are mutually exclusive
        if edit.field2 is not None and edit.value is not None:
            errors.append(_err(
                "SEM-11",
                f"{eref}: Edit has both @field2 and @value, which are mutually exclusive",
                element="Edit",
                line=edit.line,
            ))

        # SEM-12: operator and logicOperator are mutually exclusive
        if edit.operator is not None and edit.logic_operator is not None:
            errors.append(_err(
                "SEM-12",
                f"{eref}: Edit has both @operator and @logicOperator, which are "
                f"mutually exclusive",
                element="Edit",
                line=edit.line,
            ))

    # --- Control checks (SEM-15) ---
    for ctrl in strat.controls:
        if ctrl.xsi_type_local not in SPINNER_CONTROL_TYPES:
            continue
        cref = f"Strategy '{sname}', Control '{ctrl.ctrl_id}'"
        for attr_name, inc_val in (
            ("increment", ctrl.increment),
            ("innerIncrement", ctrl.inner_increment),
            ("outerIncrement", ctrl.outer_increment),
        ):
            f_inc = _try_float(inc_val)
            if f_inc is not None and f_inc <= 0:
                errors.append(_err(
                    "SEM-15",
                    f"{cref}: @{attr_name}={inc_val} must be positive",
                    element=f"Strategy[@name='{sname}']/Control[@ID='{ctrl.ctrl_id}']",
                    line=ctrl.line,
                ))
