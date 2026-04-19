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

  /* XSD schema model — loaded once in the background. Validation waits on
     xsdReady so the XSD phase always runs when the schemas are reachable.
     If the fetch fails (typical from file:// in Chrome), xsdLoadError
     carries the reason and the phase is skipped with a visible message. */
  var xsdModel = null;
  var xsdLoadError = null;
  var xsdReady = window.AtdlXsdLoader
    ? window.AtdlXsdLoader.load("schemas/")
        .then(function (m) { xsdModel = m; })
        .catch(function (e) { xsdLoadError = e && e.message ? e.message : String(e); })
    : Promise.resolve();

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
      var raw = reader.result;
      /* Wait for the XSD preload to settle so the XSD phase actually
         runs when schemas are reachable. xsdReady resolves whether the
         fetch succeeded or failed — xsdModel / xsdLoadError tell us
         which outcome we got. */
      xsdReady.then(function () {
        var validation = AtdlValidator.validate(raw, { xsdModel: xsdModel });
        validation.xsdLoadError = xsdLoadError;
        try {
          var model = validation.wellFormed ? AtdlParser.parse(raw) : { strategyIdentifierTag: "", strategies: [] };
          renderModel(model, file.name, raw, validation);
        } catch (err) {
          /* Still render the source/validation tab even if rendering fails. */
          renderModel({ strategyIdentifierTag: "", strategies: [] }, file.name, raw, validation);
          showError("Failed to render strategies: " + err.message);
        }
      });
    };
    reader.onerror = function () { showError("Could not read file: " + file.name); };
    reader.readAsText(file);
  }

  /* ---------- Render model ---------- */
  function renderModel(model, filename, rawXml, validation) {
    tabsEl.innerHTML = "";
    panelsEl.innerHTML = "";
    summarySection.hidden = true;
    fixSection.hidden = true;
    loadedStrategies = [];

    var sit = model.strategyIdentifierTag || "(unknown)";
    fileNameEl.textContent = filename + " — strategyIdentifierTag=" + sit;

    var anyStrategies = model.strategies && model.strategies.length > 0;

    (model.strategies || []).forEach(function (strat, idx) {
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

    /* Always append the Source & Validation tab last. */
    var srcIdx = (model.strategies || []).length;
    var srcTab = document.createElement("button");
    srcTab.type = "button";
    srcTab.className = "strategy-tab source-tab" + (!anyStrategies ? " active" : "");
    srcTab.setAttribute("role", "tab");
    srcTab.dataset.idx = srcIdx;
    var badgeParts = [];
    if (validation.errors.length) { badgeParts.push(validation.errors.length + " err"); srcTab.classList.add("has-errors"); }
    if (validation.warnings.length) { badgeParts.push(validation.warnings.length + " warn"); if (!validation.errors.length) srcTab.classList.add("has-warnings"); }
    srcTab.textContent = "Source & Validation" + (badgeParts.length ? " (" + badgeParts.join(", ") + ")" : " \u2713");
    srcTab.addEventListener("click", function () { activateTab(srcIdx); });
    tabsEl.appendChild(srcTab);

    var srcPanel = renderSourcePanel(rawXml, validation, filename, srcIdx);
    srcPanel.classList.toggle("active", !anyStrategies);
    panelsEl.appendChild(srcPanel);

    if (!anyStrategies && validation.errors.length) {
      showError("Document has " + validation.errors.length + " validation error(s). See the Source & Validation tab.");
    }

    shell.hidden = false;
    dropZone.hidden = true;
  }

  function activateTab(idx) {
    tabsEl.querySelectorAll(".strategy-tab").forEach(function (t) {
      t.classList.toggle("active", parseInt(t.dataset.idx, 10) === idx);
    });
    panelsEl.querySelectorAll(".strategy-panel").forEach(function (p) {
      p.classList.toggle("active", parseInt(p.dataset.strategyIdx, 10) === idx);
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

    card.appendChild(buildFixInput(strat, idx));

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

  /* ---------- Source & Validation tab ---------- */
  function renderSourcePanel(rawXml, validation, filename, tabIdx) {
    var panel = document.createElement("div");
    panel.className = "strategy-panel";
    panel.dataset.strategyIdx = String(tabIdx);

    var card = document.createElement("section");
    card.className = "strategy-card";

    var h = document.createElement("h2");
    h.textContent = "Source & Validation";
    card.appendChild(h);

    var meta = document.createElement("p");
    meta.className = "meta";
    var xsdState;
    if (validation.xsdAvailable) xsdState = "XSD phase \u2713 (6 bundled schemas)";
    else if (validation.xsdLoadError) xsdState = "XSD phase skipped — " + validation.xsdLoadError + " (serve the folder over http to enable)";
    else xsdState = "XSD phase: schemas still loading";
    meta.textContent = filename + " — " +
      (validation.wellFormed ? "well-formed XML" : "XML parse error") +
      " \u2022 " + xsdState;
    card.appendChild(meta);

    /* Partition issues by phase so each group can be shown as its own
       section — lets the user tell an XSD-schema finding apart from a
       semantic one at a glance. */
    var phase0 = [], phase1 = [], phase2 = [], phase3 = [];
    validation.errors.forEach(function (e) {
      if (e.phase === 0) phase0.push(e);
      else if (e.phase === 1) phase1.push(e);
      else if (e.phase === 2) phase2.push(e);
      else phase3.push(e);
    });
    var phase3Warn = validation.warnings.filter(function (w) { return (w.phase || 3) === 3; });

    /* Summary strip */
    var sum = document.createElement("div");
    sum.className = "validation-summary";
    sum.appendChild(stat("Strategies", validation.summary.strategies));
    sum.appendChild(stat("Parameters", validation.summary.parameters));
    sum.appendChild(stat("Controls",   validation.summary.controls));
    sum.appendChild(stat("XSD",        validation.xsdAvailable ? phase0.length : "—",
                         validation.xsdAvailable ? (phase0.length ? "err" : "ok") : ""));
    sum.appendChild(stat("Errors",     validation.errors.length,   validation.errors.length ? "err" : "ok"));
    sum.appendChild(stat("Warnings",   validation.warnings.length, validation.warnings.length ? "warn" : "ok"));
    card.appendChild(sum);

    /* Issues grouped by phase. */
    if (validation.errors.length === 0 && validation.warnings.length === 0) {
      var ok = document.createElement("p");
      ok.className = "issue issue-ok";
      ok.style.background = "#f0fdf4";
      ok.style.borderLeftColor = "#059669";
      ok.style.color = "#065f46";
      ok.textContent = "\u2713 No schema, reference, or semantic issues detected.";
      card.appendChild(ok);
    } else {
      appendIssueGroup(card, "XSD Schema (phase 0)",         phase0, []);
      appendIssueGroup(card, "XML shape (phase 1)",          phase1, []);
      appendIssueGroup(card, "Referential (phase 2)",        phase2, []);
      appendIssueGroup(card, "Semantic (phase 3)",           phase3, phase3Warn);
    }

    /* Source actions */
    var actions = document.createElement("div");
    actions.className = "source-actions";
    var copyBtn = document.createElement("button");
    copyBtn.type = "button"; copyBtn.className = "secondary-btn";
    copyBtn.textContent = "Copy source";
    copyBtn.addEventListener("click", function () {
      if (navigator.clipboard) navigator.clipboard.writeText(rawXml);
      copyBtn.textContent = "Copied!";
      setTimeout(function () { copyBtn.textContent = "Copy source"; }, 1800);
    });
    var dlBtn = document.createElement("a");
    dlBtn.className = "ghost-btn";
    dlBtn.textContent = "Download XML";
    dlBtn.href = "data:application/xml;charset=utf-8," + encodeURIComponent(rawXml);
    dlBtn.download = filename || "atdl.xml";
    dlBtn.style.textDecoration = "none";
    actions.appendChild(copyBtn);
    actions.appendChild(dlBtn);
    card.appendChild(actions);

    /* Highlighted XML source — mark each line that has an issue. Errors
       win over warnings when both fall on the same line. */
    var markers = {};
    validation.warnings.forEach(function (w) { if (w.line) markers[w.line] = "warn"; });
    validation.errors.forEach(function (e) { if (e.line) markers[e.line] = "err"; });

    var src = document.createElement("div");
    src.className = "xml-source";
    src.innerHTML = AtdlHighlight.renderWithLineNumbers(rawXml, markers);
    card.appendChild(src);

    panel.appendChild(card);
    return panel;
  }

  function appendIssueGroup(container, title, errors, warnings) {
    if (errors.length === 0 && warnings.length === 0) return;
    var h = document.createElement("h3");
    h.className = "issue-group-title";
    h.textContent = title + " — " + errors.length + " error" + (errors.length === 1 ? "" : "s") +
      (warnings.length ? ", " + warnings.length + " warning" + (warnings.length === 1 ? "" : "s") : "");
    container.appendChild(h);
    var list = document.createElement("ul");
    list.className = "issue-list";
    errors.forEach(function (e) { list.appendChild(issueItem(e, "err")); });
    warnings.forEach(function (w) { list.appendChild(issueItem(w, "warn")); });
    container.appendChild(list);
  }

  function stat(label, value, tone) {
    var w = document.createElement("div");
    w.className = "stat";
    var l = document.createElement("span"); l.className = "stat-label"; l.textContent = label;
    var v = document.createElement("span"); v.className = "stat-value" + (tone ? " " + tone : "");
    v.textContent = String(value);
    w.appendChild(l); w.appendChild(v);
    return w;
  }

  function issueItem(issue, kind) {
    var li = document.createElement("li");
    li.className = "issue " + (kind === "err" ? "issue-err" : "issue-warn");
    var rid = document.createElement("span");
    rid.className = "rule-id";
    rid.textContent = issue.ruleId;
    var msg = document.createElement("span");
    msg.textContent = " " + issue.message + (issue.line ? " (line " + issue.line + ")" : "");
    li.appendChild(rid); li.appendChild(msg);
    if (issue.element) {
      var hint = document.createElement("span");
      hint.className = "element-hint";
      hint.textContent = issue.element;
      li.appendChild(hint);
    }
    if (issue.line) {
      li.classList.add("issue-clickable");
      li.dataset.targetLine = String(issue.line);
      li.title = "Jump to line " + issue.line;
      li.addEventListener("click", function () {
        var card = li.closest(".strategy-card");
        var src = card && card.querySelector(".xml-source");
        if (!src) return;
        var row = src.children[issue.line - 1];
        if (!row) return;
        row.scrollIntoView({ block: "center", behavior: "smooth" });
        row.classList.add("xml-line-flash");
        setTimeout(function () { row.classList.remove("xml-line-flash"); }, 1400);
      });
    }
    return li;
  }

  /* ---------- FIX input: UI + parsing + application ---------- */

  /* Standard header/trailer tags that we ignore when loading a strategy form. */
  var HEADER_TAGS = { 8:1, 9:1, 35:1, 49:1, 56:1, 34:1, 52:1, 43:1, 50:1, 57:1, 115:1, 116:1, 128:1, 129:1, 142:1, 143:1, 122:1, 212:1, 213:1, 347:1, 369:1, 370:1, 10:1 };

  function buildFixInput(strat, idx) {
    var details = document.createElement("details");
    details.className = "fix-input";

    var summary = document.createElement("summary");
    summary.textContent = "Load from FIX message (optional)";
    details.appendChild(summary);

    var body = document.createElement("div");
    body.className = "fix-input-body";

    var hint = document.createElement("div");
    hint.className = "fix-hint";
    hint.innerHTML = "Paste a FIX message. Delimiters accepted: SOH (<code>\\x01</code>), <code>|</code>, or newlines.";
    body.appendChild(hint);

    var ta = document.createElement("textarea");
    ta.id = "fix-input-ta-" + idx;
    ta.placeholder = "8=FIX.4.2|9=...|35=D|...";
    ta.rows = 3;
    body.appendChild(ta);

    var row = document.createElement("div");
    row.className = "fix-actions";
    var loadBtn = document.createElement("button");
    loadBtn.type = "button";
    loadBtn.className = "primary-btn";
    loadBtn.textContent = "Load & Render";
    var clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "ghost-btn";
    clearBtn.textContent = "Clear";
    row.appendChild(loadBtn); row.appendChild(clearBtn);
    body.appendChild(row);

    var warnBox = document.createElement("div");
    warnBox.className = "fix-warnings";
    warnBox.setAttribute("aria-live", "polite");
    body.appendChild(warnBox);

    details.appendChild(body);

    loadBtn.addEventListener("click", function () {
      warnBox.innerHTML = "";
      var text = ta.value || "";
      if (!text.trim()) {
        appendWarn(warnBox, "err", "Message is empty.");
        return;
      }
      var form = document.getElementById("atdl-form-" + idx);
      if (!form) return;
      var result = applyFixMessage(strat, text, form);
      result.messages.forEach(function (m) {
        appendWarn(warnBox, m.level, m.text);
      });
      if (!result.messages.some(function (m) { return m.level === "err"; })) {
        appendWarn(warnBox, "ok", "Loaded " + result.loaded + " parameter" + (result.loaded === 1 ? "" : "s") + " from message.");
      }
    });
    clearBtn.addEventListener("click", function () {
      ta.value = "";
      warnBox.innerHTML = "";
    });

    return details;
  }

  function appendWarn(box, level, text) {
    var div = document.createElement("div");
    div.className = "fix-warn" + (level === "err" ? " fix-err" : level === "ok" ? " fix-ok" : "");
    div.textContent = text;
    box.appendChild(div);
  }

  /* Parse a raw FIX message into ordered [{tag, value}] pairs. */
  function parseFixMessage(text) {
    var parts = text.split(/[\x01|\r\n]+/);
    var pairs = [];
    var errors = [];
    parts.forEach(function (part) {
      if (!part) return;
      var s = part.trim();
      if (!s) return;
      var eq = s.indexOf("=");
      if (eq < 0) {
        errors.push({ level: "warn", text: 'Malformed field "' + s + '" (no =).' });
        return;
      }
      var tag = s.substring(0, eq).trim();
      var val = s.substring(eq + 1);
      if (!/^\d+$/.test(tag)) {
        errors.push({ level: "warn", text: 'Non-numeric tag "' + tag + '".' });
        return;
      }
      pairs.push({ tag: tag, value: val });
    });
    return { pairs: pairs, errors: errors };
  }

  /* Apply parsed FIX fields to the form for a specific strategy. */
  function applyFixMessage(strat, text, form) {
    var parsed = parseFixMessage(text);
    var messages = parsed.errors.slice();
    var loaded = 0;

    /* fixTag → {ctrl, param} lookup. Parameters with a constValue but
       no Control (e.g. routing tags) are registered with ctrl=null so
       incoming values can still be recognised and checked. */
    var byTag = {};
    var ctrls = collectControls(strat.panels);
    ctrls.forEach(function (ctrl) {
      var param = strat.parameterMap[ctrl.parameterRef];
      if (param && param.fixTag) byTag[String(param.fixTag)] = { ctrl: ctrl, param: param };
    });
    strat.parameters.forEach(function (param) {
      if (!param.fixTag) return;
      if (byTag[String(param.fixTag)]) return;
      if (param.constValue == null) return;
      byTag[String(param.fixTag)] = { ctrl: null, param: param };
    });

    var stratIdTag = String(strat.strategyIdentifierTag || "847");

    /* Track duplicates: last wins, but surface a note. */
    var seen = {};

    parsed.pairs.forEach(function (kv) {
      if (HEADER_TAGS[kv.tag]) return; /* silently ignore header/trailer */

      if (kv.tag === stratIdTag) {
        var expected = strat.wireValue || strat.name;
        if (kv.value !== expected) {
          messages.push({ level: "warn", text: 'Tag ' + kv.tag + ' ("' + kv.value + '") does not match active strategy ("' + expected + '").' });
        }
        return;
      }

      var entry = byTag[kv.tag];
      if (!entry) {
        messages.push({ level: "warn", text: 'Unknown FIX tag ' + kv.tag + ' (value="' + kv.value + '") — no matching parameter.' });
        return;
      }
      if (seen[kv.tag]) {
        messages.push({ level: "warn", text: 'Tag ' + kv.tag + ' appeared more than once — last value ("' + kv.value + '") used.' });
      }
      seen[kv.tag] = true;

      /* Constant parameter with no widget — just compare and move on. */
      if (!entry.ctrl) {
        if (entry.param.constValue != null && kv.value !== entry.param.constValue) {
          messages.push({ level: "warn", text: 'Tag ' + kv.tag + ' (' + entry.param.name + ') "' + kv.value + '" differs from declared constValue "' + entry.param.constValue + '".' });
        } else {
          loaded++;
        }
        return;
      }

      /* Range check for numerics */
      if (AtdlParser.isNumericType(entry.param.type) && kv.value !== "") {
        var n = parseFloat(kv.value);
        if (isNaN(n)) {
          messages.push({ level: "err", text: 'Tag ' + kv.tag + ' (' + entry.param.name + ') "' + kv.value + '" is not numeric.' });
          return;
        }
        var lo = entry.ctrl.minValue != null ? entry.ctrl.minValue : entry.param.minValue;
        var hi = entry.ctrl.maxValue != null ? entry.ctrl.maxValue : entry.param.maxValue;
        if (lo != null && n < parseFloat(lo)) messages.push({ level: "warn", text: 'Tag ' + kv.tag + ' (' + entry.param.name + ') ' + n + ' is below minimum ' + lo + '.' });
        if (hi != null && n > parseFloat(hi)) messages.push({ level: "warn", text: 'Tag ' + kv.tag + ' (' + entry.param.name + ') ' + n + ' is above maximum ' + hi + '.' });
      }

      var res = AtdlWidgets.setValue(entry.ctrl, entry.param, kv.value, form);
      if (res.warnings && res.warnings.length) {
        res.warnings.forEach(function (w) {
          messages.push({ level: "warn", text: 'Tag ' + kv.tag + ' (' + entry.param.name + '): ' + w + '.' });
        });
      }
      if (res.ok || res.warnings.length === 0) loaded++;
    });

    /* Re-run state rules against the new values. */
    form.dispatchEvent(new Event("input", { bubbles: true }));

    return { loaded: loaded, messages: messages };
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
    var emitted = {};

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
      emitted[param.name] = true;
    });

    /* Parameters with a constValue but no Control — e.g. constant service
       routing tags — must still be emitted on the wire. */
    strat.parameters.forEach(function (param) {
      if (emitted[param.name]) return;
      if (param.constValue == null) return;
      if (!param.fixTag) return;
      rows.push({ name: param.name, tag: param.fixTag, value: param.constValue });
      fixPairs.push({ tag: param.fixTag, value: param.constValue });
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
