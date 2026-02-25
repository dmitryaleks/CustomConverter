"""Phase 2 — referential integrity checks."""

from __future__ import annotations

from .models import (
    LIST_CONTROL_TYPES,
    DocumentContext,
    StrategyCtx,
    ValidationError,
)


def _err(rule: str, msg: str, element: str | None = None, line: int | None = None) -> ValidationError:
    return ValidationError(phase=2, rule_id=rule, message=msg, element=element, line=line)


def _all_edit_ids(ctx: DocumentContext, strat: StrategyCtx) -> frozenset[str]:
    """Return all Edit ids reachable from within *strat* (global + strategy-level)."""
    return frozenset(ctx.global_edits_by_id) | frozenset(strat.edits_by_id)


def run(ctx: DocumentContext) -> list[ValidationError]:
    """Run all referential integrity checks and return any errors found."""
    errors: list[ValidationError] = []

    for strat in ctx.strategy_list:
        reachable_edit_ids = _all_edit_ids(ctx, strat)

        # --- REF-01 / REF-02 (Control parameterRef) ---
        seen_param_refs: dict[str, int] = {}  # parameterRef → first occurrence line

        for ctrl in strat.controls:
            if ctrl.parameter_ref:
                # REF-01: parameterRef must name a real parameter
                if ctrl.parameter_ref not in strat.parameters:
                    errors.append(_err(
                        "REF-01",
                        f"Strategy '{strat.name}': Control '{ctrl.ctrl_id}' references "
                        f"unknown parameter '{ctrl.parameter_ref}'",
                        element=f"Strategy[@name='{strat.name}']/Control[@ID='{ctrl.ctrl_id}']",
                        line=ctrl.line,
                    ))
                # REF-02: each parameter referenced by at most one control
                if ctrl.parameter_ref in seen_param_refs:
                    errors.append(_err(
                        "REF-02",
                        f"Strategy '{strat.name}': parameter '{ctrl.parameter_ref}' is "
                        f"referenced by more than one Control",
                        element=f"Strategy[@name='{strat.name}']/Control[@ID='{ctrl.ctrl_id}']",
                        line=ctrl.line,
                    ))
                else:
                    seen_param_refs[ctrl.parameter_ref] = ctrl.line or 0

        # --- REF-03 / REF-04 (EditRef resolution) ---
        for edit_ref in strat.all_edit_refs:
            if edit_ref.ref_id not in reachable_edit_ids:
                rule = "REF-04" if edit_ref.in_state_rule else "REF-03"
                context = "StateRule" if edit_ref.in_state_rule else "Edit/StrategyEdit"
                errors.append(_err(
                    rule,
                    f"Strategy '{strat.name}': EditRef id='{edit_ref.ref_id}' in {context} "
                    f"does not resolve to any declared Edit",
                    element=f"Strategy[@name='{strat.name}']",
                    line=edit_ref.line,
                ))

        # --- REF-05 (Edit field references a parameter) ---
        for edit in strat.all_edits:
            for attr_name, field_val in (("field", edit.field), ("field2", edit.field2)):
                if field_val and field_val not in strat.parameters:
                    errors.append(_err(
                        "REF-05",
                        f"Strategy '{strat.name}': Edit references unknown parameter "
                        f"'{field_val}' via @{attr_name}",
                        element=f"Strategy[@name='{strat.name}']/Edit",
                        line=edit.line,
                    ))

        # --- REF-06 / REF-07 (list control items) ---
        for ctrl in strat.controls:
            if ctrl.xsi_type_local not in LIST_CONTROL_TYPES:
                continue

            param = strat.parameters.get(ctrl.parameter_ref or "")
            param_enum_ids = (
                frozenset(ep.enum_id for ep in param.enum_pairs) if param else frozenset()
            )
            list_item_enum_ids = frozenset(
                li.enum_id for li in ctrl.list_items if li.enum_id
            )

            # REF-06: ListItem enumIDs must match EnumPair enumIDs on the referenced parameter
            if param is not None:
                for li in ctrl.list_items:
                    if li.enum_id and li.enum_id not in param_enum_ids:
                        errors.append(_err(
                            "REF-06",
                            f"Strategy '{strat.name}': Control '{ctrl.ctrl_id}' has "
                            f"ListItem enumID='{li.enum_id}' not found in parameter "
                            f"'{ctrl.parameter_ref}' EnumPairs",
                            element=f"Strategy[@name='{strat.name}']/Control[@ID='{ctrl.ctrl_id}']",
                            line=ctrl.line,
                        ))

            # REF-07: initValue for list controls must be a valid ListItem enumID
            if ctrl.init_value:
                # MultiSelectList allows space-delimited values
                candidate_ids = (
                    ctrl.init_value.split()
                    if ctrl.xsi_type_local == "MultiSelectList_t"
                    else [ctrl.init_value]
                )
                for cid in candidate_ids:
                    if cid not in list_item_enum_ids:
                        errors.append(_err(
                            "REF-07",
                            f"Strategy '{strat.name}': Control '{ctrl.ctrl_id}' initValue "
                            f"'{cid}' is not a valid ListItem enumID",
                            element=f"Strategy[@name='{strat.name}']/Control[@ID='{ctrl.ctrl_id}']",
                            line=ctrl.line,
                        ))

    return errors
