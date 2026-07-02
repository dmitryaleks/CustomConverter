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

  /* checkedEnumRef / uncheckedEnumRef are enumIDs — resolve to the wire
     value through the parameter's EnumPairs. Falls back to treating the
     attribute as a literal wire value (lenient), then to the Boolean_t
     true/false wire values. */
  function enumRefWireValue(enumRef, param, fallback) {
    if (enumRef == null) return fallback;
    if (param) {
      for (var i = 0; i < param.enumPairs.length; i++) {
        if (param.enumPairs[i].enumID === enumRef) return param.enumPairs[i].wireValue;
      }
    }
    return enumRef;
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

  function buildSpinner(ctrl, param, stepOverride) {
    var el = document.createElement("input");
    el.type = "number";
    el.name = param.name;
    el.id = ctrl.id;
    var min = ctrl.minValue != null ? ctrl.minValue : param.minValue;
    var max = ctrl.maxValue != null ? ctrl.maxValue : param.maxValue;
    if (min != null) el.min = min;
    if (max != null) el.max = max;
    var step = stepOverride != null ? stepOverride : ctrl.increment;
    if (step != null) el.step = step;
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

  /* DoubleSpinner_t: inner increment maps to the native step; the outer
     increment gets a pair of nudge buttons. Tick/LotSize increment
     policies cannot be honored without market data — noted in the title. */
  function buildDoubleSpinner(ctrl, param) {
    var inner = ctrl.innerIncrement != null ? ctrl.innerIncrement : ctrl.increment;
    var el = buildSpinner(ctrl, param, inner);
    var policies = [];
    if (ctrl.innerIncrementPolicy) policies.push("innerIncrementPolicy=" + ctrl.innerIncrementPolicy);
    if (ctrl.outerIncrementPolicy) policies.push("outerIncrementPolicy=" + ctrl.outerIncrementPolicy);
    if (policies.length) el.title = policies.join(", ") + " (market data unavailable — literal increments used)";
    if (ctrl.outerIncrement == null) return el;

    var outer = parseFloat(ctrl.outerIncrement);
    if (isNaN(outer)) return el;
    var wrap = document.createDocumentFragment();
    wrap.appendChild(makeOuterStep(el, -outer));
    wrap.appendChild(el);
    wrap.appendChild(makeOuterStep(el, outer));
    return wrap;
  }

  function makeOuterStep(input, delta) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "outer-step";
    btn.textContent = (delta > 0 ? "+" : "−") + Math.abs(delta);
    btn.title = "Adjust by outer increment (" + Math.abs(delta) + ")";
    btn.addEventListener("click", function () {
      var cur = parseFloat(input.value);
      if (isNaN(cur)) cur = 0;
      var next = Number((cur + delta).toFixed(10));
      if (input.min !== "" && next < parseFloat(input.min)) next = parseFloat(input.min);
      if (input.max !== "" && next > parseFloat(input.max)) next = parseFloat(input.max);
      input.value = next;
      /* Notify the state-rule engine like a manual edit would. */
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    return btn;
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
      /* Typed text matches the displayed uiRep; keep the uiRep→enumID→wire
         triples on the input so read/write can translate. */
      var enumMap = items.map(function (li) {
        return { uiRep: li.uiRep, enumID: li.enumID, wire: wireValueFor(li.enumID, param) };
      });
      items.forEach(function (li) {
        var opt = document.createElement("option");
        opt.value = li.uiRep;
        opt.dataset.enumId = li.enumID;
        datalist.appendChild(opt);
      });
      var iv = effectiveInitValue(ctrl, param);
      if (iv != null) {
        /* initValue is an enumID — display its uiRep when it matches. */
        var initItem = enumMap.filter(function (m) { return m.enumID === iv; })[0];
        input.value = initItem ? initItem.uiRep : iv;
      }
      setRequired(input, param);
      attachFixTag(input, param);
      input.dataset.editableEnum = "1";
      input.dataset.enumMap = JSON.stringify(enumMap);
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
    el.dataset.trueValue = enumRefWireValue(ctrl.checkedEnumRef, param, param.trueWireValue || "Y");
    el.dataset.falseValue = enumRefWireValue(ctrl.uncheckedEnumRef, param, param.falseWireValue || "N");
    var iv = effectiveInitValue(ctrl, param);
    if (iv && /^(true|y|1|yes)$/i.test(iv)) el.checked = true;
    attachFixTag(el, param);
    return el;
  }

  /* RadioButton_t: a native radio so buttons sharing a radioGroup are
     mutually exclusive across parameters. */
  function buildRadioButton(ctrl, param) {
    var el = buildCheckBox(ctrl, param);
    el.type = "radio";
    if (ctrl.radioGroup) el.name = "radiogroup__" + ctrl.radioGroup;
    return el;
  }

  function buildCheckBoxList(ctrl, param) {
    var items = listFor(ctrl, param);
    var box = document.createElement("div");
    box.className = "option-group" + (ctrl.orientation === "HORIZONTAL" ? " horizontal" : "");
    box.dataset.fixTag = param.fixTag || "";
    box.dataset.role = "checkbox-list";
    box.dataset.name = param.name;
    box.dataset.ctrlId = ctrl.id;
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
    box.dataset.ctrlId = ctrl.id;
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
    var items = ctrl.listItems && ctrl.listItems.length ? ctrl.listItems : null;
    var iv = effectiveInitValue(ctrl, param);
    if (items) {
      /* Per the spec a Slider_t selects among discrete ListItems; the range
         input walks item indices and the mapping recovers enumID/wire. */
      el.min = 0; el.max = items.length - 1; el.step = 1;
      el.dataset.sliderItems = JSON.stringify(items.map(function (li) {
        return { enumID: li.enumID, uiRep: li.uiRep, wire: wireValueFor(li.enumID, param) };
      }));
      var initIdx = -1;
      items.forEach(function (li, idx) { if (iv != null && li.enumID === iv) initIdx = idx; });
      if (initIdx >= 0) el.value = initIdx;
      else { el.value = 0; el.dataset.uninitialized = "1"; }
    } else {
      var min = ctrl.minValue != null ? ctrl.minValue : (param.minValue != null ? param.minValue : 0);
      var max = ctrl.maxValue != null ? ctrl.maxValue : (param.maxValue != null ? param.maxValue : 100);
      el.min = min; el.max = max;
      if (ctrl.increment) el.step = ctrl.increment;
      if (iv != null) el.value = iv;
      else el.dataset.uninitialized = "1";
    }
    attachFixTag(el, param);
    /* Visual readout */
    var wrap = document.createDocumentFragment();
    wrap.appendChild(el);
    var out = document.createElement("span");
    out.className = "unit";
    out.textContent = sliderDisplay(el);
    el.addEventListener("input", function () {
      /* A range input always holds a number, so "no value yet" is tracked
         via this flag; the first user interaction initializes the control. */
      delete el.dataset.uninitialized;
      out.textContent = sliderDisplay(el);
    });
    /* Programmatic writes (state rules, FIX load) refresh the readout
       without touching the uninitialized flag. */
    el.addEventListener("slider-refresh", function () {
      out.textContent = sliderDisplay(el);
    });
    wrap.appendChild(out);
    return wrap;
  }

  function sliderDisplay(el) {
    if (el.dataset.uninitialized === "1") return "—";
    var items = sliderItems(el);
    if (!items) return el.value;
    var li = items[parseInt(el.value, 10)];
    return li ? li.uiRep : el.value;
  }

  function sliderItems(el) {
    if (!el.dataset || !el.dataset.sliderItems) return null;
    try { return JSON.parse(el.dataset.sliderItems); } catch (e) { return null; }
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
    if (iv != null) el.value = clockInitValue(ctrl, el.type, iv);
    setRequired(el, param);
    attachFixTag(el, param);
    return el;
  }

  /* initValueMode=1: use the current time when initValue has already past.
     Comparison is done on ISO-shaped strings in browser-local time — real
     localMktTz timezone math is out of scope. */
  function clockInitValue(ctrl, inputType, iv) {
    if (String(ctrl.initValueMode) !== "1") return iv;
    var now = new Date();
    function pad(n) { return (n < 10 ? "0" : "") + n; }
    var cur;
    if (inputType === "time") cur = pad(now.getHours()) + ":" + pad(now.getMinutes()) + ":" + pad(now.getSeconds());
    else if (inputType === "date") cur = now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate());
    else if (inputType === "datetime-local") {
      cur = now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate()) +
            "T" + pad(now.getHours()) + ":" + pad(now.getMinutes());
    } else return iv;
    /* ISO-shaped strings compare correctly as plain strings. */
    return iv < cur ? cur : iv;
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
    /* Per the spec, initValue takes precedence over label when both are set. */
    span.textContent = ctrl.initValue != null ? ctrl.initValue : (ctrl.label || "");
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
      case "SingleSpinner_t":       return buildSpinner(ctrl, fauxParam);
      case "DoubleSpinner_t":       return buildDoubleSpinner(ctrl, fauxParam);
      case "DropDownList_t":        return buildDropDown(ctrl, fauxParam, false);
      case "EditableDropDownList_t":return buildDropDown(ctrl, fauxParam, true);
      case "SingleSelectList_t":    return buildSelectList(ctrl, fauxParam, false);
      case "MultiSelectList_t":     return buildSelectList(ctrl, fauxParam, true);
      case "CheckBox_t":            return buildCheckBox(ctrl, fauxParam);
      case "CheckBoxList_t":        return buildCheckBoxList(ctrl, fauxParam);
      case "RadioButton_t":         return buildRadioButton(ctrl, fauxParam);
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
    if (el.type === "checkbox" || el.type === "radio") {
      return el.checked ? el.dataset.trueValue : el.dataset.falseValue;
    }
    if (el.tagName === "SELECT" && el.multiple) {
      var arr = [];
      for (var i = 0; i < el.options.length; i++) if (el.options[i].selected) arr.push(el.options[i].value);
      return arr.join(" ");
    }
    if (el.dataset && el.dataset.editableEnum) {
      /* Map typed uiRep → wireValue if it matches a list item, else raw text. */
      var map = editableEnumMap(el);
      for (var j = 0; j < map.length; j++) {
        if (map[j].uiRep === el.value) return map[j].wire;
      }
      return el.value;
    }
    if (el.type === "range") {
      /* Uninitialized sliders contribute no value → FIX tag omitted. */
      if (el.dataset.uninitialized === "1") return null;
      var items = sliderItems(el);
      if (items) {
        var li = items[parseInt(el.value, 10)];
        return li ? li.wire : el.value;
      }
      return el.value;
    }
    return el.value;
  }

  function editableEnumMap(el) {
    try { return JSON.parse(el.dataset.enumMap || "[]"); } catch (e) { return []; }
  }

  /* Write a wire value from a FIX field into the rendered control.
     Returns { ok, warnings:[] } where warnings describe values that could
     not be matched against an enum / list. */
  function setValue(ctrl, param, wireValue, root) {
    var name = param ? param.name : ctrl.parameterRef;
    var warnings = [];

    if (ctrl.type === "Label_t") {
      return { ok: true, warnings: [] };
    }

    if (ctrl.type === "CheckBoxList_t") {
      var box = root.querySelector('[data-role="checkbox-list"][data-name="' + cssEscape(name) + '"]');
      if (!box) return { ok: false, warnings: ["Control not found"] };
      var wanted = splitMulti(wireValue);
      var available = {};
      box.querySelectorAll('input[type="checkbox"]').forEach(function (c) { available[c.value] = c; });
      box.querySelectorAll('input[type="checkbox"]').forEach(function (c) { c.checked = false; });
      wanted.forEach(function (w) {
        if (available[w]) available[w].checked = true;
        else warnings.push('Value "' + w + '" not in allowed set');
      });
      return { ok: warnings.length === 0, warnings: warnings };
    }

    if (ctrl.type === "RadioButtonList_t") {
      var radios = root.querySelectorAll('input[type="radio"][name="' + cssEscape(name) + '"]');
      var matched = false;
      radios.forEach(function (r) {
        r.checked = r.value === wireValue;
        if (r.checked) matched = true;
      });
      if (!matched) warnings.push('Value "' + wireValue + '" not in allowed set');
      return { ok: matched, warnings: warnings };
    }

    var el = root.querySelector("#" + cssEscape(ctrl.id));
    if (!el) return { ok: false, warnings: ["Control not found"] };

    if (el.type === "checkbox" || el.type === "radio") {
      var tv = el.dataset.trueValue, fv = el.dataset.falseValue;
      if (wireValue === tv) { el.checked = true; return { ok: true, warnings: [] }; }
      if (wireValue === fv) { el.checked = false; return { ok: true, warnings: [] }; }
      el.checked = false;
      warnings.push('Value "' + wireValue + '" is not "' + tv + '" or "' + fv + '"');
      return { ok: false, warnings: warnings };
    }

    if (el.type === "range") {
      var items = sliderItems(el);
      delete el.dataset.uninitialized;
      if (items) {
        for (var si = 0; si < items.length; si++) {
          if (items[si].wire === wireValue) {
            el.value = si;
            el.dispatchEvent(new Event("slider-refresh", { bubbles: false }));
            return { ok: true, warnings: [] };
          }
        }
        warnings.push('Value "' + wireValue + '" not in allowed set');
        return { ok: false, warnings: warnings };
      }
      el.value = wireValue;
      el.dispatchEvent(new Event("slider-refresh", { bubbles: false }));
      return { ok: true, warnings: [] };
    }

    if (el.tagName === "SELECT") {
      if (el.multiple) {
        var parts = splitMulti(wireValue);
        var avail = {};
        for (var i = 0; i < el.options.length; i++) avail[el.options[i].value] = el.options[i];
        for (var j = 0; j < el.options.length; j++) el.options[j].selected = false;
        parts.forEach(function (p) {
          if (avail[p]) avail[p].selected = true;
          else warnings.push('Value "' + p + '" not in allowed set');
        });
        return { ok: warnings.length === 0, warnings: warnings };
      }
      for (var k = 0; k < el.options.length; k++) {
        if (el.options[k].value === wireValue) { el.value = wireValue; return { ok: true, warnings: [] }; }
      }
      el.value = "";
      warnings.push('Value "' + wireValue + '" not in allowed set');
      return { ok: false, warnings: warnings };
    }

    if (el.dataset && el.dataset.editableEnum) {
      var map = editableEnumMap(el);
      for (var m = 0; m < map.length; m++) {
        if (map[m].wire === wireValue) { el.value = map[m].uiRep; return { ok: true, warnings: [] }; }
      }
      el.value = wireValue; /* accept free text */
      return { ok: true, warnings: [] };
    }

    /* Plain text / number / time input — just assign. */
    el.value = wireValue;
    return { ok: true, warnings: [] };
  }

  function splitMulti(v) {
    if (v == null) return [];
    return String(v).split(/\s+/).filter(function (s) { return s.length > 0; });
  }

  /* ---- UI-value space (StateRule evaluation) ----
     Per the FIXatdl spec, Edit conditions inside a flow:StateRule compare
     against the CONTROL's value, not the parameter's wire value: enumIDs
     for list controls, "true"/"false" for checkbox/radio, raw display text
     otherwise. null means the control is uninitialized (has no value). */

  function optionGroupBox(ctrl, root) {
    return root.querySelector('[data-ctrl-id="' + cssEscape(ctrl.id) + '"]');
  }

  function readUiValue(ctrl, root) {
    if (ctrl.type === "CheckBoxList_t") {
      var box = optionGroupBox(ctrl, root);
      if (!box) return null;
      var ids = [];
      box.querySelectorAll('input[type="checkbox"]:checked').forEach(function (c) {
        ids.push(c.dataset.enumId);
      });
      return ids.length ? ids.join(" ") : null;
    }
    if (ctrl.type === "RadioButtonList_t") {
      var rbox = optionGroupBox(ctrl, root);
      var sel = rbox && rbox.querySelector('input[type="radio"]:checked');
      return sel ? sel.dataset.enumId : null;
    }
    var el = root.querySelector("#" + cssEscape(ctrl.id));
    if (!el) return null;
    if (el.type === "checkbox" || el.type === "radio") return el.checked ? "true" : "false";
    if (el.tagName === "SELECT") {
      if (el.multiple) {
        var mids = [];
        for (var i = 0; i < el.options.length; i++) {
          if (el.options[i].selected) mids.push(el.options[i].dataset.enumId || el.options[i].value);
        }
        return mids.length ? mids.join(" ") : null;
      }
      var opt = el.options[el.selectedIndex];
      if (!opt || opt.value === "") return null; /* blank placeholder */
      return opt.dataset.enumId || opt.value;
    }
    if (el.dataset && el.dataset.editableEnum) {
      var map = editableEnumMap(el);
      for (var j = 0; j < map.length; j++) {
        if (map[j].uiRep === el.value) return map[j].enumID;
      }
      return el.value === "" ? null : el.value;
    }
    if (el.type === "range") {
      if (el.dataset.uninitialized === "1") return null;
      var items = sliderItems(el);
      if (items) {
        var li = items[parseInt(el.value, 10)];
        return li ? li.enumID : null;
      }
      return el.value;
    }
    return el.value === "" ? null : el.value;
  }

  /* Apply a StateRule @value to a control. token is an enumID for list
     controls, "true"/"false" for checkbox/radio, "{NULL}" to clear the
     control to an uninitialized state, or literal display text otherwise.
     Returns true when the DOM actually changed (fixpoint detection). */
  function setUiValue(ctrl, root, token) {
    var isNull = token === "{NULL}";

    if (ctrl.type === "CheckBox_t" || ctrl.type === "RadioButton_t") {
      if (isNull) {
        /* Per the spec these controls are always initialized. */
        console.warn("FIXatdl: StateRule value=\"{NULL}\" ignored on " + ctrl.type + " '" + ctrl.id + "'.");
        return false;
      }
      var cb = root.querySelector("#" + cssEscape(ctrl.id));
      if (!cb) return false;
      var want = /^(true|y|1|yes)$/i.test(token);
      if (cb.checked === want) return false;
      cb.checked = want;
      return true;
    }

    if (ctrl.type === "CheckBoxList_t" || ctrl.type === "RadioButtonList_t") {
      var box = optionGroupBox(ctrl, root);
      if (!box) return false;
      var wanted = {};
      if (!isNull) splitMulti(token).forEach(function (id) { wanted[id] = true; });
      var changed = false;
      box.querySelectorAll("input").forEach(function (inp) {
        var w = !isNull && !!wanted[inp.dataset.enumId];
        if (inp.checked !== w) { inp.checked = w; changed = true; }
      });
      return changed;
    }

    var el = root.querySelector("#" + cssEscape(ctrl.id));
    if (!el) return false;

    if (el.tagName === "SELECT") {
      if (el.multiple) {
        var mwanted = {};
        if (!isNull) splitMulti(token).forEach(function (id) { mwanted[id] = true; });
        var mchanged = false;
        for (var i = 0; i < el.options.length; i++) {
          var mo = el.options[i];
          var mw = !isNull && !!mwanted[mo.dataset.enumId || mo.value];
          if (mo.selected !== mw) { mo.selected = mw; mchanged = true; }
        }
        return mchanged;
      }
      if (isNull) {
        if (el.value === "") return false;
        el.value = "";
        return true;
      }
      for (var k = 0; k < el.options.length; k++) {
        var so = el.options[k];
        if (so.dataset.enumId === token || so.value === token) {
          if (so.selected) return false;
          el.value = so.value;
          return true;
        }
      }
      console.warn("FIXatdl: StateRule value '" + token + "' matches no ListItem of control '" + ctrl.id + "'.");
      return false;
    }

    if (el.dataset && el.dataset.editableEnum) {
      var next = "";
      if (!isNull) {
        var map = editableEnumMap(el);
        next = token;
        for (var m = 0; m < map.length; m++) {
          if (map[m].enumID === token) { next = map[m].uiRep; break; }
        }
      }
      if (el.value === next) return false;
      el.value = next;
      return true;
    }

    if (el.type === "range") {
      var wasUninit = el.dataset.uninitialized === "1";
      if (isNull) {
        if (wasUninit) return false;
        el.dataset.uninitialized = "1";
        el.dispatchEvent(new Event("slider-refresh", { bubbles: false }));
        return true; /* readUiValue now reports null — re-evaluate rules */
      }
      delete el.dataset.uninitialized;
      var rchanged = wasUninit;
      var items = sliderItems(el);
      if (items) {
        for (var s = 0; s < items.length; s++) {
          if (items[s].enumID === token) {
            if (el.value !== String(s)) { el.value = s; rchanged = true; }
            break;
          }
        }
      } else if (el.value !== token) {
        el.value = token;
        rchanged = true;
      }
      if (rchanged) el.dispatchEvent(new Event("slider-refresh", { bubbles: false }));
      return rchanged;
    }

    var nextVal = isNull ? "" : token;
    if (el.value === nextVal) return false;
    el.value = nextVal;
    return true;
  }

  /* Minimal CSS.escape polyfill. */
  function cssEscape(s) {
    if (typeof CSS !== "undefined" && CSS.escape) return CSS.escape(s);
    return String(s).replace(/[^a-zA-Z0-9_-]/g, function (c) { return "\\" + c; });
  }

  global.AtdlWidgets = {
    build: build,
    readValue: readValue,
    setValue: setValue,
    readUiValue: readUiValue,
    setUiValue: setUiValue,
    cssEscape: cssEscape
  };
})(window);
