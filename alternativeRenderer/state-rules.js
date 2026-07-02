/* state-rules.js — FIXatdl Flow (StateRule) engine.
   Evaluates val:Edit conditions in Control-ID space (per the spec, an Edit
   inside a StateRule references Control IDs and compares against control
   values — enumIDs for list controls, "true"/"false" for checkbox/radio)
   and applies enabled / visible / value effects, including per-ListItem
   rules. Applies to a fixpoint so value-setting rules cascade. */
(function (global) {
  "use strict";

  var MAX_ITERATIONS = 25;

  /* Compare values per FIXatdl operator semantics. NULL operands → "" string
     for EQ/NE; EX/NX test for the presence of a value (null = uninitialized). */
  function evalEdit(edit, currentValues) {
    if (!edit) return true;
    /* Composite Edit: AND/OR/NOT/XOR over child Edits. */
    if (edit.edits && edit.edits.length) {
      var op = (edit.logicOperator || "AND").toUpperCase();
      var results = edit.edits.map(function (sub) { return evalEdit(sub, currentValues); });
      switch (op) {
        case "AND": return results.every(Boolean);
        case "OR":  return results.some(Boolean);
        case "NOT": return !results[0];
        case "XOR": return results.filter(Boolean).length === 1;
        default:    return results.every(Boolean);
      }
    }
    /* Leaf Edit: field [operator] value | field [operator] field2 */
    var lhs = currentValues[edit.field];
    var rhs;
    if (edit.field2) rhs = currentValues[edit.field2];
    else rhs = edit.value;
    return applyOperator(edit.operator || "EQ", lhs, rhs);
  }

  function applyOperator(op, lhs, rhs) {
    var lhsStr = lhs == null ? "" : String(lhs);
    var rhsStr = rhs == null ? "" : String(rhs);
    switch (String(op).toUpperCase()) {
      case "EQ": return lhsStr === rhsStr;
      case "NE": return lhsStr !== rhsStr;
      case "LT": return numericCompare(lhs, rhs) < 0;
      case "LE": return numericCompare(lhs, rhs) <= 0;
      case "GT": return numericCompare(lhs, rhs) > 0;
      case "GE": return numericCompare(lhs, rhs) >= 0;
      case "EX": return lhs != null && lhsStr !== "";
      case "NX": return lhs == null || lhsStr === "";
      default:   return false;
    }
  }

  function numericCompare(a, b) {
    var na = parseFloat(a), nb = parseFloat(b);
    if (!isNaN(na) && !isNaN(nb)) return na - nb;
    return String(a).localeCompare(String(b));
  }

  /* Fold one StateRule into an outcome bucket. enabled/visible follow the
     XSD truth table (XNOR with the edit result); value applies only when
     the condition is true. Later rules override earlier ones per aspect. */
  function applyRuleToOutcome(rule, values, out) {
    var trigger = evalEdit(rule.edit, values);
    if (rule.visible != null) out.visible = trigger ? rule.visible : !rule.visible;
    if (rule.enabled != null) out.enabled = trigger ? rule.enabled : !rule.enabled;
    if (rule.value != null && trigger) out.setValue = rule.value;
    return out;
  }

  /* PURE (DOM-free, unit-testable): compute per-control and per-ListItem
     outcomes from the rule definitions and a Control-ID-keyed value map.
     Returns { outcomes: {ctrlId → {visible?, enabled?, setValue?}},
               listOutcomes: {ctrlId → {enumID → {visible?, enabled?}}} }. */
  function computeOutcomes(allCtrls, values) {
    var outcomes = {};
    var listOutcomes = {};
    allCtrls.forEach(function (ctrl) {
      if (ctrl.stateRules && ctrl.stateRules.length) {
        var out = {};
        ctrl.stateRules.forEach(function (rule) { applyRuleToOutcome(rule, values, out); });
        outcomes[ctrl.id] = out;
      }
      (ctrl.listItems || []).forEach(function (li) {
        if (!li.stateRules || !li.stateRules.length) return;
        var lo = {};
        li.stateRules.forEach(function (rule) { applyRuleToOutcome(rule, values, lo); });
        /* A value effect on a ListItem rule sets the parent control's value. */
        if (lo.setValue !== undefined) {
          outcomes[ctrl.id] = outcomes[ctrl.id] || {};
          outcomes[ctrl.id].setValue = lo.setValue;
          delete lo.setValue;
        }
        listOutcomes[ctrl.id] = listOutcomes[ctrl.id] || {};
        listOutcomes[ctrl.id][li.enumID] = lo;
      });
    });
    return { outcomes: outcomes, listOutcomes: listOutcomes };
  }

  /* ---- DOM adapter ---- */

  function buildState(strategy, formEl) {
    var allCtrls = collectControls(strategy.panels);
    var byId = {};
    allCtrls.forEach(function (ctrl) {
      var groupEl = formEl.querySelector('[data-ctrl-id="' + AtdlWidgets.cssEscape(ctrl.id) + '"]');
      byId[ctrl.id] = { ctrl: ctrl, group: groupEl };
    });
    return { allCtrls: allCtrls, byId: byId };
  }

  function readAllValues(state, formEl) {
    var values = {};
    state.allCtrls.forEach(function (ctrl) {
      values[ctrl.id] = AtdlWidgets.readUiValue(ctrl, formEl);
    });
    /* Lenient mirror: some documents (incorrectly) reference parameter names
       from StateRule Edits. Never clobber a real Control ID. */
    state.allCtrls.forEach(function (ctrl) {
      if (ctrl.parameterRef && !(ctrl.parameterRef in values)) {
        values[ctrl.parameterRef] = values[ctrl.id];
      }
    });
    return values;
  }

  function applyOutcomesToDom(state, computed, formEl) {
    var changed = false;

    Object.keys(computed.outcomes).forEach(function (id) {
      var entry = state.byId[id];
      if (!entry) return;
      var out = computed.outcomes[id];
      var group = entry.group;
      if (group && out.visible !== undefined) {
        var hide = !out.visible;
        if (group.classList.contains("hidden") !== hide) {
          group.classList.toggle("hidden", hide);
          changed = true;
        }
      }
      if (group && out.enabled !== undefined) {
        var disable = !out.enabled;
        if (group.classList.contains("disabled") !== disable) {
          group.classList.toggle("disabled", disable);
          changed = true;
        }
        group.querySelectorAll("input, select, textarea, button").forEach(function (el) {
          el.disabled = disable;
        });
      }
      if (out.setValue !== undefined) {
        if (AtdlWidgets.setUiValue(entry.ctrl, formEl, out.setValue)) changed = true;
      }
    });

    Object.keys(computed.listOutcomes).forEach(function (id) {
      var entry = state.byId[id];
      if (!entry) return;
      var perItem = computed.listOutcomes[id];
      Object.keys(perItem).forEach(function (enumId) {
        if (applyListItemOutcome(entry.ctrl, formEl, enumId, perItem[enumId])) changed = true;
      });
    });

    return changed;
  }

  /* Show/hide/enable a single ListItem (option / radio / checkbox entry).
     When the currently selected item becomes hidden or disabled its
     selection is cleared, which feeds back into the next fixpoint pass. */
  function applyListItemOutcome(ctrl, formEl, enumId, lo) {
    if (lo.visible === undefined && lo.enabled === undefined) return false;
    var changed = false;
    var hide = lo.visible !== undefined ? !lo.visible : null;
    var disable = lo.enabled !== undefined ? !lo.enabled : null;
    var blocked = hide === true || disable === true;

    var box = formEl.querySelector('[data-ctrl-id="' + AtdlWidgets.cssEscape(ctrl.id) + '"]');
    if (box && (box.dataset.role === "checkbox-list" || box.dataset.role === "radio-list")) {
      var inp = box.querySelector('input[data-enum-id="' + AtdlWidgets.cssEscape(enumId) + '"]');
      if (!inp) return false;
      var lbl = inp.closest("label") || inp;
      if (hide !== null && lbl.classList.contains("hidden") !== hide) {
        lbl.classList.toggle("hidden", hide);
        changed = true;
      }
      if (disable !== null && inp.disabled !== disable) {
        inp.disabled = disable;
        lbl.classList.toggle("disabled", disable);
        changed = true;
      }
      if (blocked && inp.checked) {
        inp.checked = false;
        changed = true;
      }
      return changed;
    }

    var el = formEl.querySelector("#" + AtdlWidgets.cssEscape(ctrl.id));
    if (el && el.dataset && el.dataset.editableEnum) {
      /* Editable dropdowns keep their options in a sibling datalist. */
      el = formEl.querySelector("#" + AtdlWidgets.cssEscape(ctrl.id) + "_list");
    }
    if (!el) return false;
    var opt = el.querySelector('option[data-enum-id="' + AtdlWidgets.cssEscape(enumId) + '"]');
    if (!opt) return false;
    if (hide !== null && opt.hidden !== hide) {
      opt.hidden = hide;
      changed = true;
    }
    if (disable !== null && opt.disabled !== disable) {
      opt.disabled = disable;
      changed = true;
    }
    if (blocked && opt.selected) {
      if (el.multiple) opt.selected = false;
      else el.value = "";
      changed = true;
    }
    return changed;
  }

  /* Apply state rules to a strategy form. Re-runs whenever any field
     changes; iterates until no rule changes the DOM (value-setting rules
     can cascade into other rules). */
  function attach(strategy, formEl) {
    var state = buildState(strategy, formEl);

    function applyAll() {
      var iterations = 0;
      var changed = true;
      while (changed && iterations < MAX_ITERATIONS) {
        var values = readAllValues(state, formEl);
        var computed = computeOutcomes(state.allCtrls, values);
        changed = applyOutcomesToDom(state, computed, formEl);
        iterations++;
      }
      if (changed) {
        console.warn("AtdlStateRules: state rules did not converge after " +
                     MAX_ITERATIONS + " passes — check for contradictory value rules.");
      }
    }

    formEl.addEventListener("input", applyAll);
    formEl.addEventListener("change", applyAll);
    applyAll();
  }

  function collectControls(panels) {
    var out = [];
    (panels || []).forEach(function (p) {
      (p.controls || []).forEach(function (c) { out.push(c); });
      out = out.concat(collectControls(p.panels));
    });
    return out;
  }

  global.AtdlStateRules = {
    attach: attach,
    evalEdit: evalEdit,
    computeOutcomes: computeOutcomes
  };
})(window);
