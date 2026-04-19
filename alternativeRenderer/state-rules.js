/* state-rules.js — Evaluate atdl4j Flow StateRule conditions.
   Supports: visible / enabled / value setters driven by val:Edit conditions
   on other parameter values. Mirrors the subset most strategies use. */
(function (global) {
  "use strict";

  /* Compare values per FIXatdl operator semantics. NULL operands → "" string. */
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

  /* Apply state rules to a strategy form. Re-runs whenever any field changes. */
  function attach(strategy, formEl) {
    var allCtrls = collectControls(strategy.panels);

    /* Build a map of paramName → fieldGroup element for show/hide. */
    var groups = {};
    allCtrls.forEach(function (ctrl) {
      var pname = ctrl.parameterRef || ctrl.id;
      var groupEl = formEl.querySelector('[data-field-name="' + cssEscape(pname) + '"]');
      if (groupEl) groups[pname] = { ctrl: ctrl, group: groupEl };
    });

    function readAllValues() {
      var values = {};
      Object.keys(groups).forEach(function (name) {
        var g = groups[name];
        var p = strategy.parameterMap[g.ctrl.parameterRef];
        var v = AtdlWidgets.readValue(g.ctrl, p, formEl);
        if (v !== null) values[name] = v;
      });
      return values;
    }

    function applyAll() {
      var values = readAllValues();
      allCtrls.forEach(function (ctrl) {
        if (!ctrl.stateRules || ctrl.stateRules.length === 0) return;
        var pname = ctrl.parameterRef || ctrl.id;
        var g = groups[pname];
        if (!g) return;
        ctrl.stateRules.forEach(function (rule) {
          var trigger = evalEdit(rule.edit, values);
          if (rule.visible !== null) {
            g.group.classList.toggle("hidden", trigger ? !rule.visible : rule.visible);
          }
          if (rule.enabled !== null) {
            var disable = trigger ? !rule.enabled : rule.enabled;
            g.group.classList.toggle("disabled", disable);
            g.group.querySelectorAll("input, select, textarea").forEach(function (el) {
              el.disabled = disable;
            });
          }
          if (rule.value !== null && trigger) {
            var input = g.group.querySelector("#" + cssEscape(ctrl.id));
            if (input && input.value !== rule.value) {
              input.value = rule.value;
            }
          }
        });
      });
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

  function cssEscape(s) {
    if (typeof CSS !== "undefined" && CSS.escape) return CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_-]/g, function (c) { return "\\" + c; });
  }

  global.AtdlStateRules = { attach: attach, evalEdit: evalEdit };
})(window);
