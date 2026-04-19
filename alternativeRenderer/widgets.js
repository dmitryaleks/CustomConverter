/* widgets.js — build a DOM control for an atdl4j control + parameter pair. */
(function (global) {
  "use strict";

  var INT_TYPES = {Int_t:1, Length_t:1, NumInGroup_t:1, SeqNum_t:1, TagNum_t:1};
  var FLOAT_TYPES = {Float_t:1, Qty_t:1, Price_t:1, PriceOffset_t:1, Amt_t:1, Numeric_t:1};
  var MULTI_TYPES = {MultipleStringValue_t:1, MultipleCharValue_t:1};

  /* Resolve the control's effective initial value by precedence:
     control.initValue > parameter.constValue > null */
  function effectiveInitValue(ctrl, param) {
    if (ctrl && ctrl.initValue != null) return ctrl.initValue;
    if (param && param.constValue != null) return param.constValue;
    return null;
  }

  function setRequired(el, param) {
    if (param && param.use === "required") el.required = true;
  }

  function attachFixTag(el, param) {
    if (param && param.fixTag) el.dataset.fixTag = param.fixTag;
  }

  /* --- option list builders --- */
  function listFor(ctrl, param) {
    /* Prefer ListItem (UI rep), fall back to EnumPair (when no Layout). */
    if (ctrl.listItems && ctrl.listItems.length) return ctrl.listItems;
    if (param && param.enumPairs.length) {
      return param.enumPairs.map(function (e) { return { enumID: e.enumID, uiRep: e.enumID }; });
    }
    return [];
  }

  function wireValueFor(enumID, param) {
    if (!param) return enumID;
    for (var i = 0; i < param.enumPairs.length; i++) {
      if (param.enumPairs[i].enumID === enumID) return param.enumPairs[i].wireValue;
    }
    return enumID;
  }

  /* --- builders per Control xsi:type --- */

  function buildTextField(ctrl, param) {
    var el = document.createElement("input");
    el.type = "text";
    el.name = param.name;
    el.id = ctrl.id;
    var iv = effectiveInitValue(ctrl, param);
    if (iv != null) el.value = iv;
    if (param.constValue != null) el.readOnly = true;
    if (param.maxLength) el.maxLength = parseInt(param.maxLength, 10);
    if (param.minLength) el.minLength = parseInt(param.minLength, 10);
    if (param.type === "Currency_t") { el.maxLength = 3; el.pattern = "[A-Za-z]{3}"; }
    if (param.type === "Exchange_t") { el.maxLength = 4; }
    if (param.type === "Char_t") { el.maxLength = 1; }
    setRequired(el, param);
    attachFixTag(el, param);
    return el;
  }

  function buildSpinner(ctrl, param) {
    var el = document.createElement("input");
    el.type = "number";
    el.name = param.name;
    el.id = ctrl.id;
    var min = ctrl.minValue != null ? ctrl.minValue : param.minValue;
    var max = ctrl.maxValue != null ? ctrl.maxValue : param.maxValue;
    if (min != null) el.min = min;
    if (max != null) el.max = max;
    if (ctrl.increment != null) el.step = ctrl.increment;
    else if (param.type === "Percentage_t") el.step = "any";
    else if (FLOAT_TYPES[param.type]) {
      if (param.precision != null) {
        var p = parseInt(param.precision, 10);
        el.step = p > 0 ? "0." + new Array(p).join("0") + "1" : "1";
      } else el.step = "any";
    } else el.step = "1";
    var iv = effectiveInitValue(ctrl, param);
    if (iv != null) el.value = iv;
    if (param.constValue != null) el.readOnly = true;
    setRequired(el, param);
    attachFixTag(el, param);
    return el;
  }

  function buildDropDown(ctrl, param, editable) {
    var items = listFor(ctrl, param);
    if (editable) {
      /* Editable: use input + datalist */
      var wrap = document.createDocumentFragment();
      var input = document.createElement("input");
      input.type = "text";
      input.id = ctrl.id;
      input.name = param.name;
      input.setAttribute("list", ctrl.id + "_list");
      var datalist = document.createElement("datalist");
      datalist.id = ctrl.id + "_list";
      items.forEach(function (li) {
        var opt = document.createElement("option");
        opt.value = li.uiRep;
        datalist.appendChild(opt);
      });
      var iv = effectiveInitValue(ctrl, param);
      if (iv != null) input.value = iv;
      setRequired(input, param);
      attachFixTag(input, param);
      input.dataset.editableEnum = "1";
      input.dataset.enumPairs = JSON.stringify(param.enumPairs || []);
      wrap.appendChild(input);
      wrap.appendChild(datalist);
      return wrap;
    }
    var sel = document.createElement("select");
    sel.id = ctrl.id;
    sel.name = param.name;
    var blank = document.createElement("option");
    blank.value = ""; blank.textContent = "-- select --";
    sel.appendChild(blank);
    var iv2 = effectiveInitValue(ctrl, param);
    items.forEach(function (li) {
      var opt = document.createElement("option");
      var wire = wireValueFor(li.enumID, param);
      opt.value = wire;
      opt.dataset.enumId = li.enumID;
      opt.textContent = li.uiRep;
      if (iv2 != null && li.enumID === iv2) opt.selected = true;
      sel.appendChild(opt);
    });
    setRequired(sel, param);
    attachFixTag(sel, param);
    return sel;
  }

  function buildSelectList(ctrl, param, multi) {
    var items = listFor(ctrl, param);
    var sel = document.createElement("select");
    sel.id = ctrl.id;
    sel.name = param.name;
    if (multi) sel.multiple = true;
    sel.size = Math.min(Math.max(items.length, 3), 8);
    items.forEach(function (li) {
      var opt = document.createElement("option");
      opt.value = wireValueFor(li.enumID, param);
      opt.dataset.enumId = li.enumID;
      opt.textContent = li.uiRep;
      sel.appendChild(opt);
    });
    setRequired(sel, param);
    attachFixTag(sel, param);
    if (multi) sel.dataset.multi = "1";
    return sel;
  }

  function buildCheckBox(ctrl, param) {
    var el = document.createElement("input");
    el.type = "checkbox";
    el.id = ctrl.id;
    el.name = param.name;
    el.dataset.trueValue = ctrl.checkedEnumRef || param.trueWireValue || "Y";
    el.dataset.falseValue = ctrl.uncheckedEnumRef || param.falseWireValue || "N";
    var iv = effectiveInitValue(ctrl, param);
    if (iv && /^(true|y|1|yes)$/i.test(iv)) el.checked = true;
    attachFixTag(el, param);
    return el;
  }

  function buildCheckBoxList(ctrl, param) {
    var items = listFor(ctrl, param);
    var box = document.createElement("div");
    box.className = "option-group" + (ctrl.orientation === "HORIZONTAL" ? " horizontal" : "");
    box.dataset.fixTag = param.fixTag || "";
    box.dataset.role = "checkbox-list";
    box.dataset.name = param.name;
    items.forEach(function (li, idx) {
      var lbl = document.createElement("label");
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = wireValueFor(li.enumID, param);
      cb.dataset.enumId = li.enumID;
      cb.name = param.name + "[]";
      cb.id = ctrl.id + "_" + idx;
      var span = document.createElement("span");
      span.textContent = li.uiRep;
      lbl.appendChild(cb); lbl.appendChild(span);
      box.appendChild(lbl);
    });
    return box;
  }

  function buildRadioButtonList(ctrl, param) {
    var items = listFor(ctrl, param);
    var box = document.createElement("div");
    box.className = "option-group" + (ctrl.orientation === "HORIZONTAL" ? " horizontal" : "");
    box.dataset.fixTag = param.fixTag || "";
    box.dataset.role = "radio-list";
    box.dataset.name = param.name;
    var iv = effectiveInitValue(ctrl, param);
    items.forEach(function (li, idx) {
      var lbl = document.createElement("label");
      var rb = document.createElement("input");
      rb.type = "radio";
      rb.value = wireValueFor(li.enumID, param);
      rb.dataset.enumId = li.enumID;
      rb.name = param.name;
      rb.id = ctrl.id + "_" + idx;
      if (iv != null && li.enumID === iv) rb.checked = true;
      var span = document.createElement("span");
      span.textContent = li.uiRep;
      lbl.appendChild(rb); lbl.appendChild(span);
      box.appendChild(lbl);
    });
    return box;
  }

  function buildSlider(ctrl, param) {
    var el = document.createElement("input");
    el.type = "range";
    el.id = ctrl.id; el.name = param.name;
    var min = ctrl.minValue != null ? ctrl.minValue : (param.minValue != null ? param.minValue : 0);
    var max = ctrl.maxValue != null ? ctrl.maxValue : (param.maxValue != null ? param.maxValue : 100);
    el.min = min; el.max = max;
    if (ctrl.increment) el.step = ctrl.increment;
    var iv = effectiveInitValue(ctrl, param);
    if (iv != null) el.value = iv;
    attachFixTag(el, param);
    /* Visual readout */
    var wrap = document.createDocumentFragment();
    wrap.appendChild(el);
    var out = document.createElement("span");
    out.className = "unit";
    out.textContent = el.value;
    el.addEventListener("input", function () { out.textContent = el.value; });
    wrap.appendChild(out);
    return wrap;
  }

  function buildClock(ctrl, param) {
    var el = document.createElement("input");
    var t = param.type;
    if (t === "UTCTimeOnly_t" || t === "LocalMktTime_t") el.type = "time";
    else if (t === "UTCDate_t" || t === "LocalMktDate_t") el.type = "date";
    else if (t === "UTCTimestamp_t") el.type = "datetime-local";
    else if (t === "MonthYear_t") el.type = "month";
    else el.type = "text";
    if (el.type === "time") el.step = "1";
    el.id = ctrl.id; el.name = param.name;
    var iv = effectiveInitValue(ctrl, param);
    if (iv != null) el.value = iv;
    setRequired(el, param);
    attachFixTag(el, param);
    return el;
  }

  function buildHidden(ctrl, param) {
    var el = document.createElement("input");
    el.type = "hidden";
    el.id = ctrl.id; el.name = param.name;
    var iv = effectiveInitValue(ctrl, param);
    if (iv != null) el.value = iv;
    attachFixTag(el, param);
    return el;
  }

  function buildLabel(ctrl) {
    var span = document.createElement("span");
    span.className = "atdl-label-text";
    span.textContent = ctrl.label || "";
    return span;
  }

  function buildTextArea(ctrl, param) {
    var el = document.createElement("textarea");
    el.id = ctrl.id; el.name = param.name;
    var iv = effectiveInitValue(ctrl, param);
    if (iv != null) el.value = iv;
    setRequired(el, param);
    attachFixTag(el, param);
    return el;
  }

  /* Master factory */
  function build(ctrl, param) {
    var fauxParam = param || {
      name: ctrl.parameterRef || ctrl.id,
      type: "String_t", fixTag: null, use: "optional",
      enumPairs: [], constValue: null,
      trueWireValue: "Y", falseWireValue: "N"
    };
    switch (ctrl.type) {
      case "TextField_t":           return buildTextField(ctrl, fauxParam);
      case "SingleSpinner_t":
      case "DoubleSpinner_t":       return buildSpinner(ctrl, fauxParam);
      case "DropDownList_t":        return buildDropDown(ctrl, fauxParam, false);
      case "EditableDropDownList_t":return buildDropDown(ctrl, fauxParam, true);
      case "SingleSelectList_t":    return buildSelectList(ctrl, fauxParam, false);
      case "MultiSelectList_t":     return buildSelectList(ctrl, fauxParam, true);
      case "CheckBox_t":            return buildCheckBox(ctrl, fauxParam);
      case "CheckBoxList_t":        return buildCheckBoxList(ctrl, fauxParam);
      case "RadioButton_t":         return buildCheckBox(ctrl, fauxParam); /* simple boolean radio */
      case "RadioButtonList_t":     return buildRadioButtonList(ctrl, fauxParam);
      case "Slider_t":              return buildSlider(ctrl, fauxParam);
      case "Clock_t":               return buildClock(ctrl, fauxParam);
      case "HiddenField_t":         return buildHidden(ctrl, fauxParam);
      case "Label_t":               return buildLabel(ctrl);
      case "TextArea_t":            return buildTextArea(ctrl, fauxParam);
      default:                      return buildTextField(ctrl, fauxParam);
    }
  }

  /* Read submitted value(s) from the rendered control. */
  function readValue(ctrl, param, root) {
    var name = param ? param.name : ctrl.parameterRef;
    if (ctrl.type === "CheckBoxList_t") {
      var box = root.querySelector('[data-role="checkbox-list"][data-name="' + cssEscape(name) + '"]');
      if (!box) return null;
      var vals = [];
      box.querySelectorAll('input[type="checkbox"]:checked').forEach(function (c) { vals.push(c.value); });
      return vals.length ? vals.join(" ") : "";
    }
    if (ctrl.type === "RadioButtonList_t") {
      var sel = root.querySelector('input[type="radio"][name="' + cssEscape(name) + '"]:checked');
      return sel ? sel.value : "";
    }
    var el = root.querySelector("#" + cssEscape(ctrl.id));
    if (!el) return null;
    if (el.type === "checkbox") return el.checked ? el.dataset.trueValue : el.dataset.falseValue;
    if (el.tagName === "SELECT" && el.multiple) {
      var arr = [];
      for (var i = 0; i < el.options.length; i++) if (el.options[i].selected) arr.push(el.options[i].value);
      return arr.join(" ");
    }
    if (el.dataset && el.dataset.editableEnum) {
      /* Map uiRep → wireValue if it matches an enum pair, else use raw text. */
      var pairs = JSON.parse(el.dataset.enumPairs || "[]");
      for (var j = 0; j < pairs.length; j++) {
        if (pairs[j].enumID === el.value) return pairs[j].wireValue;
      }
      return el.value;
    }
    return el.value;
  }

  /* Minimal CSS.escape polyfill. */
  function cssEscape(s) {
    if (typeof CSS !== "undefined" && CSS.escape) return CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_-]/g, function (c) { return "\\" + c; });
  }

  global.AtdlWidgets = { build: build, readValue: readValue, cssEscape: cssEscape };
})(window);
