/* app.js — drag&drop loader + renderer orchestration. */
(function () {
  "use strict";

  var dropZone = document.getElementById("drop-zone");
  var fileInput = document.getElementById("file-input");
  var errorBanner = document.getElementById("error-banner");
  var shell = document.getElementById("strategy-shell");
  var fileNameEl = document.getElementById("file-name");
  var resetBtn = document.getElementById("reset-btn");
  var tabsEl = document.getElementById("strategy-tabs");
  var panelsEl = document.getElementById("strategy-panels");
  var summarySection = document.getElementById("summary");
  var summaryBody = document.getElementById("summary-body");
  var fixSection = document.getElementById("fix-message");
  var fixBody = document.getElementById("fix-message-body");
  var copyBtn = document.getElementById("fix-copy-btn");

  var lastRawMsg = "";
  var loadedStrategies = []; /* { strategy, formEl } */

  /* ---------- Drop zone wiring ---------- */
  ["dragenter", "dragover"].forEach(function (ev) {
    dropZone.addEventListener(ev, function (e) {
      e.preventDefault(); e.stopPropagation();
      dropZone.classList.add("is-drag");
    });
  });
  ["dragleave", "dragend"].forEach(function (ev) {
    dropZone.addEventListener(ev, function (e) {
      e.preventDefault(); e.stopPropagation();
      dropZone.classList.remove("is-drag");
    });
  });
  dropZone.addEventListener("drop", function (e) {
    e.preventDefault(); e.stopPropagation();
    dropZone.classList.remove("is-drag");
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  });
  dropZone.addEventListener("click", function () { fileInput.click(); });
  dropZone.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
  });
  fileInput.addEventListener("change", function () {
    if (fileInput.files && fileInput.files[0]) handleFile(fileInput.files[0]);
  });
  resetBtn.addEventListener("click", reset);

  function reset() {
    fileInput.value = "";
    shell.hidden = true;
    summarySection.hidden = true;
    fixSection.hidden = true;
    errorBanner.hidden = true;
    tabsEl.innerHTML = "";
    panelsEl.innerHTML = "";
    dropZone.hidden = false;
    loadedStrategies = [];
    lastRawMsg = "";
  }

  function showError(msg) {
    errorBanner.textContent = msg;
    errorBanner.hidden = false;
  }

  function clearError() {
    errorBanner.hidden = true;
    errorBanner.textContent = "";
  }

  function handleFile(file) {
    clearError();
    var reader = new FileReader();
    reader.onload = function () {
      try {
        var model = AtdlParser.parse(reader.result);
        renderModel(model, file.name);
      } catch (err) {
        showError("Failed to parse " + file.name + ":\n" + err.message);
        shell.hidden = true;
      }
    };
    reader.onerror = function () { showError("Could not read file: " + file.name); };
    reader.readAsText(file);
  }

  /* ---------- Render model ---------- */
  function renderModel(model, filename) {
    tabsEl.innerHTML = "";
    panelsEl.innerHTML = "";
    summarySection.hidden = true;
    fixSection.hidden = true;
    loadedStrategies = [];

    fileNameEl.textContent = filename + " — strategyIdentifierTag=" + model.strategyIdentifierTag;

    if (!model.strategies.length) {
      showError("No <Strategy> elements found in document.");
      return;
    }

    model.strategies.forEach(function (strat, idx) {
      var tab = document.createElement("button");
      tab.type = "button";
      tab.className = "strategy-tab" + (idx === 0 ? " active" : "");
      tab.setAttribute("role", "tab");
      tab.textContent = strat.uiRep || strat.name;
      tab.dataset.idx = idx;
      tab.addEventListener("click", function () { activateTab(idx); });
      tabsEl.appendChild(tab);

      var panel = renderStrategy(strat, idx);
      panel.classList.toggle("active", idx === 0);
      panelsEl.appendChild(panel);
    });

    shell.hidden = false;
    dropZone.hidden = true;
  }

  function activateTab(idx) {
    tabsEl.querySelectorAll(".strategy-tab").forEach(function (t, i) {
      t.classList.toggle("active", i === idx);
    });
    panelsEl.querySelectorAll(".strategy-panel").forEach(function (p, i) {
      p.classList.toggle("active", i === idx);
    });
    summarySection.hidden = true;
    fixSection.hidden = true;
  }

  function renderStrategy(strat, idx) {
    var panel = document.createElement("div");
    panel.className = "strategy-panel";
    panel.dataset.strategyIdx = idx;

    var card = document.createElement("section");
    card.className = "strategy-card";

    var title = document.createElement("h2");
    title.textContent = "Strategy: " + (strat.uiRep || strat.name);
    card.appendChild(title);

    var meta = document.createElement("p");
    meta.className = "meta";
    var metaParts = [];
    if (strat.providerID) metaParts.push("Provider: " + strat.providerID);
    if (strat.version) metaParts.push("Version: " + strat.version);
    if (strat.fixMsgType) metaParts.push("MsgType: " + strat.fixMsgType);
    metaParts.push("StrategyIdentifierTag: " + strat.strategyIdentifierTag);
    meta.textContent = metaParts.join(" \u2022 ");
    card.appendChild(meta);

    var form = document.createElement("form");
    form.className = "atdl-form";
    form.id = "atdl-form-" + idx;
    form.noValidate = true;

    strat.panels.forEach(function (sp) {
      form.appendChild(renderPanel(sp, strat));
    });

    var actions = document.createElement("div");
    actions.className = "actions";
    var submit = document.createElement("button");
    submit.type = "submit"; submit.className = "primary-btn";
    submit.textContent = "Validate & Preview FIX";
    var resetB = document.createElement("button");
    resetB.type = "reset"; resetB.className = "secondary-btn";
    resetB.textContent = "Reset";
    actions.appendChild(submit); actions.appendChild(resetB);
    form.appendChild(actions);

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      handleSubmit(strat, form);
    });
    form.addEventListener("reset", function () {
      summarySection.hidden = true;
      fixSection.hidden = true;
      lastRawMsg = "";
      form.querySelectorAll("[aria-invalid='true']").forEach(function (el) {
        el.removeAttribute("aria-invalid");
      });
      form.querySelectorAll(".field-error").forEach(function (e) { e.textContent = ""; });
    });

    card.appendChild(form);
    panel.appendChild(card);

    loadedStrategies.push({ strategy: strat, form: form });
    /* Attach state rules after the form is in the DOM. */
    setTimeout(function () { AtdlStateRules.attach(strat, form); }, 0);
    return panel;
  }

  /* Render a StrategyPanel — fieldset with optional title and orientation. */
  function renderPanel(sp, strat) {
    var fs = document.createElement("fieldset");
    fs.className = "atdl-panel" + (sp.title || sp.border === "Line" ? "" : " no-border");
    if (sp.collapsible) fs.classList.add("collapsible");
    if (sp.collapsible && sp.collapsed) fs.classList.add("collapsed");

    if (sp.title) {
      var lg = document.createElement("legend");
      lg.textContent = sp.title;
      fs.appendChild(lg);
      if (sp.collapsible) {
        lg.addEventListener("click", function () { fs.classList.toggle("collapsed"); });
      }
    }

    var body = document.createElement("div");
    body.className = "panel-body" + (sp.orientation === "HORIZONTAL" ? " horizontal" : "");

    sp.controls.forEach(function (ctrl) {
      body.appendChild(renderControl(ctrl, strat));
    });
    sp.panels.forEach(function (sub) {
      body.appendChild(renderPanel(sub, strat));
    });

    fs.appendChild(body);
    return fs;
  }

  /* Render a single Control as a labeled field group. */
  function renderControl(ctrl, strat) {
    var param = strat.parameterMap[ctrl.parameterRef] || null;
    var pname = ctrl.parameterRef || ctrl.id;

    /* HiddenField: append directly without group. Wrap in span for layout neutrality. */
    if (ctrl.type === "HiddenField_t") {
      var wrap = document.createElement("span");
      wrap.style.display = "none";
      wrap.dataset.fieldName = pname;
      wrap.appendChild(AtdlWidgets.build(ctrl, param));
      return wrap;
    }

    var group = document.createElement("div");
    group.className = "field-group";
    group.dataset.fieldName = pname;

    var lbl = document.createElement("label");
    lbl.htmlFor = ctrl.id;
    lbl.textContent = ctrl.label || pname;
    group.appendChild(lbl);

    var control = document.createElement("div");
    control.className = "control-wrap";
    control.appendChild(AtdlWidgets.build(ctrl, param));
    /* Percentage suffix */
    if (param && param.type === "Percentage_t") {
      var unit = document.createElement("span");
      unit.className = "unit"; unit.textContent = "%";
      control.appendChild(unit);
    }
    group.appendChild(control);

    /* Description from parameter */
    if (param && param.description) {
      var d = document.createElement("span");
      d.className = "description"; d.textContent = param.description;
      group.appendChild(d);
    }

    var err = document.createElement("span");
    err.className = "field-error";
    err.id = ctrl.id + "-error";
    err.setAttribute("aria-live", "polite");
    group.appendChild(err);

    return group;
  }

  /* ---------- Submission, validation, summary & FIX preview ---------- */
  function collectControls(panels, out) {
    out = out || [];
    panels.forEach(function (p) {
      p.controls.forEach(function (c) { out.push(c); });
      collectControls(p.panels, out);
    });
    return out;
  }

  function handleSubmit(strat, form) {
    var ctrls = collectControls(strat.panels);
    var ok = true;
    var rows = [];
    var fixPairs = [];

    ctrls.forEach(function (ctrl) {
      var param = strat.parameterMap[ctrl.parameterRef];
      if (!param || ctrl.type === "Label_t") return;
      var raw = AtdlWidgets.readValue(ctrl, param, form);
      var err = form.querySelector("#" + AtdlWidgets.cssEscape(ctrl.id) + "-error");
      if (err) err.textContent = "";

      /* Required check */
      if (param.use === "required" && (raw == null || raw === "")) {
        ok = false;
        markInvalid(form, ctrl, "This field is required.");
      } else {
        clearInvalid(form, ctrl);
      }
      /* Range check for numerics */
      if (raw !== "" && raw != null && AtdlParser.isNumericType(param.type)) {
        var n = parseFloat(raw);
        if (isNaN(n)) {
          ok = false; markInvalid(form, ctrl, "Must be a number."); return;
        }
        var lo = ctrl.minValue != null ? ctrl.minValue : param.minValue;
        var hi = ctrl.maxValue != null ? ctrl.maxValue : param.maxValue;
        if (lo != null && n < parseFloat(lo)) { ok = false; markInvalid(form, ctrl, "Below minimum (" + lo + ")."); return; }
        if (hi != null && n > parseFloat(hi)) { ok = false; markInvalid(form, ctrl, "Above maximum (" + hi + ")."); return; }
      }

      rows.push({ name: param.name, tag: param.fixTag || "", value: raw == null ? "" : raw });
      if (param.fixTag && raw != null && raw !== "") {
        fixPairs.push({ tag: param.fixTag, value: raw });
      }
    });

    if (!ok) {
      summarySection.hidden = true;
      fixSection.hidden = true;
      return;
    }

    /* Render summary table */
    summaryBody.innerHTML = "";
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      ["name", "tag", "value"].forEach(function (k) {
        var td = document.createElement("td");
        td.textContent = r[k];
        tr.appendChild(td);
      });
      summaryBody.appendChild(tr);
    });
    summarySection.hidden = false;

    /* Build FIX message */
    lastRawMsg = AtdlFix.build(strat, fixPairs);
    fixBody.textContent = lastRawMsg.replace(/\x01/g, "|\n");
    fixSection.hidden = false;
    summarySection.scrollIntoView({ behavior: "smooth" });
  }

  function markInvalid(form, ctrl, msg) {
    var el = form.querySelector("#" + AtdlWidgets.cssEscape(ctrl.id));
    if (el) el.setAttribute("aria-invalid", "true");
    var err = form.querySelector("#" + AtdlWidgets.cssEscape(ctrl.id) + "-error");
    if (err) err.textContent = msg;
  }
  function clearInvalid(form, ctrl) {
    var el = form.querySelector("#" + AtdlWidgets.cssEscape(ctrl.id));
    if (el) el.removeAttribute("aria-invalid");
  }

  /* ---------- Copy FIX to clipboard ---------- */
  copyBtn.addEventListener("click", function () {
    var text = lastRawMsg.replace(/\x01/g, "|");
    if (!text) return;
    var done = function () {
      copyBtn.textContent = "Copied!";
      setTimeout(function () { copyBtn.textContent = "Copy to Clipboard"; }, 1800);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallbackCopy);
    } else fallbackCopy();
    function fallbackCopy() {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); } catch (e) {}
      document.body.removeChild(ta);
      done();
    }
  });
})();
