"""Render a FIXATDL 1.1 <Strategies> element tree to a self-contained HTML page."""

from __future__ import annotations

import html
from pathlib import Path

from lxml import etree

CORE_NS = "http://www.fixprotocol.org/ATDL-1-1/Core"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

_STRATEGY_TAG = f"{{{CORE_NS}}}Strategy"
_PARAM_TAG = f"{{{CORE_NS}}}Parameter"
_ENUM_PAIR_TAG = f"{{{CORE_NS}}}EnumPair"

_INT_TYPES = {"Int_t", "SeqNum_t", "Length_t", "NumInGroup_t", "TagNum_t"}
_FLOAT_TYPES = {"Float_t", "Qty_t", "Price_t", "PriceOffset_t", "Amt_t", "Numeric_t"}
_MULTI_TYPES = {"MultipleCharValue_t", "MultipleStringValue_t"}

_CSS = """\
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: system-ui, sans-serif;
  background: #f5f5f5;
  color: #333;
  padding: 1.5rem;
}
h1 { font-size: 1.6rem; margin-bottom: 0.25rem; color: #1a1a2e; }
.meta { color: #666; font-size: 0.875rem; margin-bottom: 1.5rem; }
.strategy-section {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,.12);
  margin-bottom: 2rem;
  padding: 1.5rem;
}
fieldset { border: none; padding: 0; }
legend { font-size: 1.1rem; font-weight: 600; color: #1a1a2e; margin-bottom: 1rem; }
.field-group {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 0.3rem 1rem;
  align-items: start;
  margin-bottom: 1rem;
}
label { font-weight: 500; padding-top: 0.4rem; word-break: break-word; }
.control-wrap { display: flex; align-items: center; gap: 0.4rem; }
input, select, textarea {
  width: 100%;
  padding: 0.4rem 0.6rem;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-size: 0.9rem;
}
input[readonly] { background: #f0f0f0; color: #666; cursor: not-allowed; }
input[type=checkbox] { width: auto; flex-shrink: 0; }
textarea { resize: vertical; min-height: 5rem; }
.unit { color: #666; font-size: 0.85rem; white-space: nowrap; }
.description {
  color: #888;
  font-size: 0.8rem;
  grid-column: 2;
  margin-top: -0.1rem;
}
.field-error {
  color: #c0392b;
  font-size: 0.8rem;
  grid-column: 2;
  min-height: 1em;
}
input:required, select:required, textarea:required {
  border-left: 3px solid #e67e22;
}
input[aria-invalid=true],
select[aria-invalid=true],
textarea[aria-invalid=true] {
  border-color: #c0392b;
  outline: 2px solid #f5b7b1;
}
.actions { display: flex; gap: 1rem; margin-top: 1.5rem; }
button {
  padding: 0.5rem 1.2rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
}
button[type=submit] { background: #2980b9; color: #fff; }
button[type=submit]:hover { background: #1f6395; }
button[type=reset] { background: #eee; color: #333; }
button[type=reset]:hover { background: #ddd; }
#summary {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,.12);
  padding: 1.5rem;
  margin-top: 1.5rem;
}
#summary h2 { font-size: 1.2rem; margin-bottom: 1rem; color: #1a1a2e; }
#summary table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
#summary th, #summary td {
  text-align: left;
  padding: 0.4rem 0.6rem;
  border-bottom: 1px solid #eee;
}
#summary th { font-weight: 600; background: #f8f8f8; }
#fix-message {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,.12);
  padding: 1.5rem;
  margin-top: 1.5rem;
}
#fix-message h2 { font-size: 1.2rem; margin-bottom: 0.5rem; color: #1a1a2e; }
.fix-meta { color: #888; font-size: 0.8rem; margin-bottom: 1rem; }
.fix-meta code {
  background: #f0f0f0;
  padding: 0.1em 0.3em;
  border-radius: 3px;
  font-family: monospace;
}
.fix-pre {
  background: #1a1a2e;
  color: #a8ff78;
  font-family: 'Cascadia Code', 'Fira Mono', 'Consolas', monospace;
  font-size: 0.82rem;
  padding: 1rem 1.2rem;
  border-radius: 6px;
  overflow-x: auto;
  white-space: pre;
  line-height: 1.7;
  margin-bottom: 1rem;
}
#fix-copy-btn { background: #27ae60; color: #fff; }
#fix-copy-btn:hover { background: #1e8449; }
@media (max-width: 600px) {
  .field-group { grid-template-columns: 1fr; }
  .description, .field-error { grid-column: 1; }
}
"""

_JS = """\
(function () {
  /* ---- helpers ---- */
  function pad2(n) { return n < 10 ? '0' + n : String(n); }

  function buildFixMsg(form) {
    var SOH = '\\x01';
    /* collect filled parameter fields */
    var paramFields = [];
    form.querySelectorAll('[data-fix-tag]').forEach(function (ctrl) {
      var tag = ctrl.dataset.fixTag;
      if (!tag) return;
      var val;
      if (ctrl.type === 'checkbox') {
        val = ctrl.checked
          ? (ctrl.dataset.trueValue || 'Y')
          : (ctrl.dataset.falseValue || 'N');
      } else {
        val = ctrl.value;
      }
      if (val !== '') paramFields.push(tag + '=' + val);
    });
    /* standard header body fields (after BeginString / BodyLength) */
    var now = new Date();
    var sendingTime = String(now.getFullYear())
      + pad2(now.getMonth() + 1) + pad2(now.getDate())
      + '-' + pad2(now.getHours()) + ':' + pad2(now.getMinutes())
      + ':' + pad2(now.getSeconds());
    var senderCompID = form.dataset.providerId || 'PROVIDER';
    var bodyFields = [
      '35=D',
      '49=' + senderCompID,
      '56=BROKER',
      '34=1',
      '52=' + sendingTime
    ].concat(paramFields);
    /* body length = byte count of body string with SOH delimiters */
    var bodyStr = bodyFields.join(SOH) + SOH;
    var header = '8=FIX.4.2' + SOH + '9=' + bodyStr.length + SOH;
    var raw = header + bodyStr;
    /* checksum = sum of all ASCII values mod 256, zero-padded to 3 digits */
    var cs = 0;
    for (var i = 0; i < raw.length; i++) cs += raw.charCodeAt(i);
    raw += '10=' + ('00' + (cs % 256)).slice(-3) + SOH;
    return raw;
  }

  /* ---- shared state ---- */
  var _lastRawMsg = '';

  /* ---- form handlers ---- */
  document.querySelectorAll('form.atdl-form').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      /* validation */
      var controls = form.querySelectorAll(
        'input:not([readonly]), select, textarea'
      );
      var valid = true;
      controls.forEach(function (ctrl) {
        var errEl = document.getElementById(ctrl.id + '-error');
        var isEmpty = ctrl.type === 'checkbox' ? false : !ctrl.value.trim();
        if (ctrl.required && isEmpty) {
          ctrl.setAttribute('aria-invalid', 'true');
          if (errEl) errEl.textContent = 'This field is required.';
          valid = false;
        } else {
          ctrl.removeAttribute('aria-invalid');
          if (errEl) errEl.textContent = '';
        }
      });
      if (!valid) return;
      /* summary table */
      var summary = document.getElementById('summary');
      var tbody = document.getElementById('summary-body');
      tbody.innerHTML = '';
      controls.forEach(function (ctrl) {
        if (!ctrl.name) return;
        var val;
        if (ctrl.type === 'checkbox') {
          val = ctrl.checked
            ? (ctrl.dataset.trueValue || 'true')
            : (ctrl.dataset.falseValue || 'false');
        } else {
          val = ctrl.value;
        }
        var tr = document.createElement('tr');
        var tdName = document.createElement('td');
        var tdTag = document.createElement('td');
        var tdVal = document.createElement('td');
        tdName.textContent = ctrl.name;
        tdTag.textContent = ctrl.dataset.fixTag || '';
        tdVal.textContent = val;
        tr.appendChild(tdName);
        tr.appendChild(tdTag);
        tr.appendChild(tdVal);
        tbody.appendChild(tr);
      });
      summary.hidden = false;
      /* FIX message */
      _lastRawMsg = buildFixMsg(form);
      var fixSection = document.getElementById('fix-message');
      document.getElementById('fix-message-body').textContent =
        _lastRawMsg.replace(/\\x01/g, '|\\n');
      fixSection.hidden = false;
      summary.scrollIntoView({ behavior: 'smooth' });
    });

    form.addEventListener('reset', function () {
      document.getElementById('summary').hidden = true;
      document.getElementById('fix-message').hidden = true;
      _lastRawMsg = '';
      form.querySelectorAll('input, select, textarea').forEach(function (ctrl) {
        ctrl.removeAttribute('aria-invalid');
        var errEl = document.getElementById(ctrl.id + '-error');
        if (errEl) errEl.textContent = '';
      });
    });
  });

  /* ---- copy button ---- */
  var copyBtn = document.getElementById('fix-copy-btn');
  if (copyBtn) {
    copyBtn.addEventListener('click', function () {
      var text = _lastRawMsg.replace(/\\x01/g, '|');
      if (!text) return;
      navigator.clipboard.writeText(text).then(function () {
        copyBtn.textContent = 'Copied!';
        setTimeout(function () { copyBtn.textContent = 'Copy to Clipboard'; }, 2000);
      }).catch(function () {
        /* execCommand fallback for non-HTTPS contexts */
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.cssText = 'position:fixed;opacity:0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        copyBtn.textContent = 'Copied!';
        setTimeout(function () { copyBtn.textContent = 'Copy to Clipboard'; }, 2000);
      });
    });
  }
})();
"""


def _bare_type(xsi_type: str) -> str:
    """Strip the 'core:' prefix from an xsi:type value."""
    return xsi_type[5:] if xsi_type.startswith("core:") else xsi_type


def _get_enum_pairs(param_elem: etree._Element) -> list[tuple[str, str]]:
    """Return list of (enumID, wireValue) tuples from EnumPair children."""
    pairs = []
    for child in param_elem:
        if child.tag == _ENUM_PAIR_TAG:
            pairs.append((child.get("enumID", ""), child.get("wireValue", "")))
    return pairs


def _get_description(param_elem: etree._Element) -> str:
    """Extract description text from the XML comment immediately preceding param_elem.

    builder.py writes comments in the form ``<!-- name: description -->``.
    Returns the text after the first colon, stripped of whitespace.
    """
    prev = param_elem.getprevious()
    if prev is not None and callable(prev.tag):  # comment or PI node
        text = prev.text or ""
        colon_idx = text.find(":")
        if colon_idx != -1:
            return text[colon_idx + 1:].strip()
        return text.strip()
    return ""


def _build_control(
    name: str,
    xsi_type: str,
    enum_pairs: list[tuple[str, str]],
    param_elem: etree._Element,
) -> str:
    """Return an HTML control string for the given parameter element."""
    bare = _bare_type(xsi_type)
    esc_name = html.escape(name, quote=True)
    const_value = param_elem.get("constValue")
    required = param_elem.get("use", "") == "required"
    req_attr = " required" if required else ""

    # constValue → readonly text input regardless of type
    if const_value is not None:
        esc_val = html.escape(const_value, quote=True)
        return (
            f'<input type="text" id="{esc_name}" name="{esc_name}"'
            f' value="{esc_val}" readonly>'
        )

    # Any type with EnumPair children → <select>
    if enum_pairs:
        multiple_attr = " multiple" if bare in _MULTI_TYPES else ""
        options = ['<option value="">-- select --</option>']
        for enum_id, wire_val in enum_pairs:
            esc_id = html.escape(enum_id, quote=True)
            esc_wv = html.escape(wire_val, quote=True)
            esc_wv_text = html.escape(wire_val)
            options.append(
                f'<option value="{esc_wv}" data-enum-id="{esc_id}">'
                f"{esc_wv_text}</option>"
            )
        opts_html = "\n            ".join(options)
        return (
            f'<select id="{esc_name}" name="{esc_name}"'
            f"{multiple_attr}{req_attr}>\n"
            f"            {opts_html}\n"
            f"          </select>"
        )

    # --- Type-based mapping ---

    if bare == "String_t":
        max_len = param_elem.get("maxLength", "")
        min_len = param_elem.get("minLength", "")
        extra = f' maxlength="{html.escape(max_len, quote=True)}"' if max_len else ""
        extra += f' minlength="{html.escape(min_len, quote=True)}"' if min_len else ""
        return (
            f'<input type="text" id="{esc_name}" name="{esc_name}"{extra}{req_attr}>'
        )

    if bare in _INT_TYPES:
        min_val = param_elem.get("minValue", "")
        max_val = param_elem.get("maxValue", "")
        extra = f' min="{html.escape(min_val, quote=True)}"' if min_val else ""
        extra += f' max="{html.escape(max_val, quote=True)}"' if max_val else ""
        return (
            f'<input type="number" step="1" id="{esc_name}"'
            f' name="{esc_name}"{extra}{req_attr}>'
        )

    if bare in _FLOAT_TYPES:
        min_val = param_elem.get("minValue", "")
        max_val = param_elem.get("maxValue", "")
        precision = param_elem.get("precision", "")
        if precision:
            try:
                p = int(precision)
                step = f"0.{'0' * (p - 1)}1" if p > 0 else "1"
            except ValueError:
                step = "any"
        else:
            step = "any"
        extra = f' min="{html.escape(min_val, quote=True)}"' if min_val else ""
        extra += f' max="{html.escape(max_val, quote=True)}"' if max_val else ""
        return (
            f'<input type="number" step="{step}" id="{esc_name}"'
            f' name="{esc_name}"{extra}{req_attr}>'
        )

    if bare == "Percentage_t":
        multiply = param_elem.get("multiplyBy100", "false").lower() == "true"
        max_v = "1" if multiply else "100"
        suffix = '<span class="unit">%</span>'
        return (
            f'<input type="number" id="{esc_name}" name="{esc_name}"'
            f' min="0" max="{max_v}"{req_attr}> {suffix}'
        )

    if bare == "Char_t":
        return (
            f'<input type="text" maxlength="1" id="{esc_name}"'
            f' name="{esc_name}"{req_attr}>'
        )

    if bare == "Boolean_t":
        true_val = param_elem.get("trueWireValue", "Y")
        false_val = param_elem.get("falseWireValue", "N")
        esc_tv = html.escape(true_val, quote=True)
        esc_fv = html.escape(false_val, quote=True)
        return (
            f'<input type="checkbox" id="{esc_name}" name="{esc_name}"'
            f' data-true-value="{esc_tv}" data-false-value="{esc_fv}">'
        )

    if bare == "Currency_t":
        return (
            f'<input type="text" maxlength="3" pattern="[A-Z]{{3}}"'
            f' id="{esc_name}" name="{esc_name}"{req_attr}>'
        )

    if bare == "Exchange_t":
        return (
            f'<input type="text" maxlength="4" id="{esc_name}"'
            f' name="{esc_name}"{req_attr}>'
        )

    if bare == "Month-Year_t":
        return f'<input type="month" id="{esc_name}" name="{esc_name}"{req_attr}>'

    if bare == "UTCTimeStamp_t":
        return (
            f'<input type="datetime-local" id="{esc_name}"'
            f' name="{esc_name}"{req_attr}>'
        )

    if bare in ("UTCTimeOnly_t", "LocalMktTime_t"):
        return f'<input type="time" id="{esc_name}" name="{esc_name}"{req_attr}>'

    if bare == "UTCDate_t":
        return f'<input type="date" id="{esc_name}" name="{esc_name}"{req_attr}>'

    if bare == "Data_t":
        return f'<textarea id="{esc_name}" name="{esc_name}"{req_attr}></textarea>'

    # Fallback for unknown types
    return f'<input type="text" id="{esc_name}" name="{esc_name}"{req_attr}>'


def _render_strategy(strategy_elem: etree._Element, strategy_index: int) -> str:
    """Render a single <Strategy> element as an HTML section with a form."""
    name = strategy_elem.get("name", "Unknown")
    provider_id = strategy_elem.get("providerID", "")
    version = strategy_elem.get("version", "")

    esc_name = html.escape(name)

    meta_parts = []
    if provider_id:
        meta_parts.append(f"Provider: {html.escape(provider_id)}")
    if version:
        meta_parts.append(f"Version: {html.escape(version)}")
    parent = strategy_elem.getparent()
    if parent is not None:
        sit = parent.get("strategyIdentifierTag", "")
        if sit:
            meta_parts.append(f"Strategy Identifier Tag: {html.escape(sit)}")
    meta_html = " | ".join(meta_parts)

    field_groups: list[str] = []
    for child in strategy_elem:
        if child.tag != _PARAM_TAG:
            continue
        param_name = child.get("name", "")
        xsi_type = child.get(f"{{{XSI_NS}}}type", "core:String_t")
        enum_pairs = _get_enum_pairs(child)
        description = _get_description(child)

        fix_tag = child.get("fixTag", "")
        esc_pname = html.escape(param_name, quote=True)
        esc_pname_text = html.escape(param_name)
        control_html = _build_control(param_name, xsi_type, enum_pairs, child)

        # Inject data-fix-tag onto the root control element so JS can read it
        if fix_tag:
            esc_fix_tag = html.escape(fix_tag, quote=True)
            for prefix in ("<input ", "<select ", "<textarea "):
                if control_html.startswith(prefix):
                    control_html = (
                        prefix
                        + f'data-fix-tag="{esc_fix_tag}" '
                        + control_html[len(prefix):]
                    )
                    break

        desc_html = (
            f'        <span class="description">{html.escape(description)}</span>\n'
            if description
            else ""
        )
        error_html = (
            f'        <span class="field-error" id="{esc_pname}-error"'
            f' aria-live="polite"></span>\n'
        )

        field_group = (
            f'      <div class="field-group">\n'
            f'        <label for="{esc_pname}">{esc_pname_text}</label>\n'
            f'        <div class="control-wrap">{control_html}</div>\n'
            f"{desc_html}"
            f"{error_html}"
            f"      </div>"
        )
        field_groups.append(field_group)

    fields_html = "\n".join(field_groups)
    form_id = f"atdl-form-{strategy_index}"
    esc_provider_id = html.escape(provider_id, quote=True)

    return (
        f'  <section class="strategy-section">\n'
        f"    <h1>Strategy: {esc_name}</h1>\n"
        f'    <p class="meta">{meta_html}</p>\n'
        f'    <form id="{form_id}" class="atdl-form" novalidate'
        f' data-provider-id="{esc_provider_id}">\n'
        f'      <input type="hidden" name="StrategyName"'
        f' data-fix-tag="5010" value="{html.escape(name, quote=True)}">\n'
        f"      <fieldset>\n"
        f"        <legend>{esc_name}</legend>\n"
        f"{fields_html}\n"
        f"      </fieldset>\n"
        f'      <div class="actions">\n'
        f"        <button type=\"submit\">Validate &amp; Preview Values</button>\n"
        f'        <button type="reset">Reset</button>\n'
        f"      </div>\n"
        f"    </form>\n"
        f"  </section>\n"
    )


def render_html(root: etree._Element, title: str | None = None) -> str:
    """Render a ``<Strategies>`` element tree to a self-contained HTML page.

    Args:
        root: The root ``<Strategies>`` lxml element.
        title: Optional page title override. Defaults to
               ``"{first strategy name} — ATDL Preview"``.

    Returns:
        The full HTML document as a string.
    """
    strategies = [c for c in root if c.tag == _STRATEGY_TAG]

    if title is None:
        if strategies:
            first_name = strategies[0].get("name", "ATDL")
            title = f"{first_name} — ATDL Preview"
        else:
            title = "ATDL Preview"

    esc_title = html.escape(title)

    strategy_sections = "".join(
        _render_strategy(strat, i) for i, strat in enumerate(strategies)
    )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="UTF-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{esc_title}</title>\n"
        f"  <style>\n{_CSS}  </style>\n"
        "</head>\n"
        "<body>\n"
        f"{strategy_sections}"
        '  <section id="summary" hidden>\n'
        "    <h2>Order Parameter Summary</h2>\n"
        "    <table>\n"
        "      <thead><tr><th>Parameter</th><th>FIX Tag Number</th><th>Value</th></tr></thead>\n"
        '      <tbody id="summary-body"></tbody>\n'
        "    </table>\n"
        "  </section>\n"
        '  <section id="fix-message" hidden>\n'
        "    <h2>Raw FIX 4.2 Message</h2>\n"
        '    <p class="fix-meta">Fields delimited by <code>|</code> (SOH substitute).'
        " Empty optional parameters are omitted.</p>\n"
        '    <pre id="fix-message-body" class="fix-pre"></pre>\n'
        '    <div class="actions">\n'
        '      <button id="fix-copy-btn" type="button">Copy to Clipboard</button>\n'
        "    </div>\n"
        "  </section>\n"
        f"  <script>\n{_JS}  </script>\n"
        "</body>\n"
        "</html>"
    )


def write_html(
    root: etree._Element,
    output_path: str | Path,
    title: str | None = None,
) -> None:
    """Render *root* to a self-contained HTML file at *output_path*.

    Args:
        root: The root ``<Strategies>`` lxml element.
        output_path: Destination path for the HTML file.
        title: Optional page title override.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html_str = render_html(root, title=title)
    output_path.write_text(html_str, encoding="utf-8")
