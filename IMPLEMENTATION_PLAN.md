# Implementation Plan — HTML Renderer

## Chapter 1 — Overview of Existing Implementation

Phases 1–7 are complete. The converter reads a proprietary JSON algo descriptor and
produces a FIXATDL 1.1 XML file, optionally validated against the official XSD schema.

| Phase | Module / File | Description | Status |
|-------|--------------|-------------|--------|
| 1 | `requirements.txt`, `.venv` | Project setup, dependencies (`lxml≥5.0`) | ✅ Done |
| 2 | `converter/parser.py` | JSON → `AlgoDef` / `ParameterDef` dataclasses | ✅ Done |
| 3 | `converter/builder.py` | Data model → FIXATDL 1.1 XML (lxml) | ✅ Done |
| 4 | `converter/validator.py` | XSD validation via lxml | ✅ Done |
| 5 | `main.py` | CLI entrypoint (`argparse`) | ✅ Done |
| 6 | `tests/` | 49 unit tests, all passing | ✅ Done |
| 7 | `PROJECT_PLAN.md` | Documentation update | ✅ Done |

The generated XML contains only Core-namespace elements (`Strategy`, `Parameter`,
`EnumPair`). There are no `StrategyLayout` / `StrategyPanel` / control elements from
the Layout sub-schema. The renderer therefore auto-derives HTML controls from parameter
types and `EnumPair` children.

---

## Chapter 2 — HTML Renderer (`converter/renderer.py`)

### 2.1 Goal

Produce a self-contained, single-file HTML page from an lxml `<Strategies>` element
tree. The page renders each strategy as an interactive HTML form for in-browser review
and verification. No external CDN or JS framework — fully offline-capable.

### 2.2 Public API

```python
# converter/renderer.py
def render_html(root: etree._Element, title: str | None = None) -> str: ...
def write_html(root: etree._Element, output_path: str | Path, title: str | None = None) -> None: ...
```

`render_html` returns the full HTML string.
`write_html` delegates to `render_html` and writes UTF-8 bytes to disk
(parallel to `write_fixatdl` in `builder.py`).

### 2.3 Parameter-to-Control Mapping

| `xsi:type` value | HTML control | Key attributes |
|------------------|-------------|----------------|
| `core:String_t` | `<input type="text">` | `maxlength` ← `maxLength`; `minlength` ← `minLength` |
| `core:Int_t`, `SeqNum_t`, `Length_t`, `NumInGroup_t`, `TagNum_t` | `<input type="number" step="1">` | `min`/`max` ← `minValue`/`maxValue` |
| `core:Float_t`, `Qty_t`, `Price_t`, `PriceOffset_t`, `Amt_t`, `Numeric_t` | `<input type="number">` | `step` derived from `precision` attr (default `"any"`) |
| `core:Percentage_t` | `<input type="number" min="0" max="100">` | honour `multiplyBy100`; display `%` suffix |
| `core:Char_t` | `<input type="text" maxlength="1">` | |
| `core:Boolean_t` | `<input type="checkbox">` | `data-true-value`/`data-false-value` from schema attrs |
| `core:MultipleCharValue_t`, `MultipleStringValue_t` | `<select multiple>` | options from `EnumPair` |
| `core:Currency_t` | `<input type="text" maxlength="3" pattern="[A-Z]{3}">` | |
| `core:Exchange_t` | `<input type="text" maxlength="4">` | |
| `core:Month-Year_t` | `<input type="month">` | |
| `core:UTCTimeStamp_t` | `<input type="datetime-local">` | |
| `core:UTCTimeOnly_t`, `LocalMktTime_t` | `<input type="time">` | |
| `core:UTCDate_t` | `<input type="date">` | |
| `core:Data_t` | `<textarea>` | |
| **Any type with `EnumPair` children** | `<select>` (single) | overrides type-based choice; options from `enumID`/`wireValue` |

Additional rules:
- `constValue` present → render as `<input readonly value="{constValue}">` regardless of type.
- `use="required"` → add HTML `required` attribute.

### 2.4 HTML Output Structure

```
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{strategy_name} — ATDL Preview</title>
  <style>/* inline CSS: clean form layout, responsive, colour-coded required fields */</style>
</head>
<body>
  <section class="strategy-section">
    <h1>Strategy: {strategy_name}</h1>
    <p class="meta">Provider: {providerID} | Version: {version} | ...</p>
    <form id="atdl-form-0" class="atdl-form" novalidate>
      <fieldset>
        <legend>{strategy_name}</legend>
        <!-- repeated per parameter -->
        <div class="field-group">
          <label for="{name}">{name}</label>
          <div class="control-wrap">{control element}</div>
          <span class="description">{description from XML comment}</span>
          <span class="field-error" id="{name}-error" aria-live="polite"></span>
        </div>
      </fieldset>
      <div class="actions">
        <button type="submit">Validate &amp; Preview Values</button>
        <button type="reset">Reset</button>
      </div>
    </form>
  </section>
  <section id="summary" hidden>
    <h2>Order Parameter Summary</h2>
    <table>
      <thead><tr><th>Parameter</th><th>Value</th></tr></thead>
      <tbody id="summary-body"><!-- JS-populated --></tbody>
    </table>
  </section>
  <script>/* inline JS */</script>
</body>
</html>
```

Multiple `<Strategy>` children in `<Strategies>` each produce a separate
`<section class="strategy-section">`. The page title uses the first strategy's name.

### 2.5 Inline JavaScript Behaviour

- On form submit: `preventDefault()`, validate all `required` fields (excluding
  `readonly` inputs), mark invalid with `aria-invalid="true"` + red outline, show
  inline error text in the sibling `<span class="field-error">`.
- On valid submit: populate the `#summary` table with name → current value rows
  (checkboxes use `data-true-value`/`data-false-value`), unhide the section,
  smooth-scroll to it.
- On form reset: clear the `#summary` section and remove all `aria-invalid` markers
  and error text.

### 2.6 Description Extraction

`builder.py` prepends XML comments in the form `<!-- paramName: description text -->`.
The renderer retrieves `param_elem.getprevious()`; if the preceding sibling is a
comment node (detected via `callable(prev.tag)`), it extracts the text after the
first `:` and trims whitespace. This text is placed in a
`<span class="description">` following the control.

---

## Chapter 3 — CLI Integration

Add a single optional `--html PATH` argument to `main.py`.

### Usage

```
python main.py input.json output.xml --html output.html [other flags]
```

### Changes to `main.py`

1. In `_build_parser()`, add:
   ```python
   p.add_argument(
       "--html",
       type=Path,
       metavar="HTML",
       help="Render ATDL strategies to a self-contained HTML file",
   )
   ```

2. In `main()`, after the `write_fixatdl()` call:
   ```python
   if args.html:
       from converter.renderer import write_html
       write_html(root, args.html)
   ```

3. No changes to exit codes or existing flags.

---

## Chapter 4 — Unit Tests (`tests/test_renderer.py`)

Minimum 9 test cases:

| Test | What it checks |
|------|---------------|
| `test_render_returns_html_doctype` | output starts with `<!DOCTYPE html>` |
| `test_strategy_name_in_title_and_h1` | strategy name appears in `<title>` and `<h1>` |
| `test_string_param_renders_text_input` | `String_t` → `<input type="text">` |
| `test_int_param_renders_number_input` | `Int_t` → `<input type="number" step="1">` |
| `test_enum_pairs_render_select` | params with `EnumPair` children → `<select>` with `<option>` per pair |
| `test_boolean_param_renders_checkbox` | `Boolean_t` → `<input type="checkbox">` |
| `test_const_value_renders_readonly` | `constValue` attr → `readonly` + `value` on input |
| `test_description_in_html` | description comment text appears in `.description` span |
| `test_write_html_creates_file` | `write_html(root, path)` → UTF-8 HTML file on disk |
| `test_cli_html_flag_writes_file` | `main(["in.json","out.xml","--html","out.html"])` → HTML file created |

Test helpers build `<Strategies>` / `<Strategy>` / `<Parameter>` elements directly
with lxml (no disk I/O needed for the unit tests). The CLI test uses `tmp_path` and
writes a minimal JSON fixture.

---

## Chapter 5 — Project Layout Update

```
CustomConverter/
├── converter/
│   ├── __init__.py
│   ├── parser.py
│   ├── builder.py
│   ├── validator.py
│   └── renderer.py       ← NEW
├── tests/
│   ├── __init__.py
│   ├── test_parser.py
│   ├── test_builder.py
│   ├── test_validator.py
│   └── test_renderer.py  ← NEW
├── main.py               ← modified (--html flag)
├── schemas/
├── requirements.txt      ← no changes (stdlib html, textwrap; lxml already present)
└── PROJECT_PLAN.md
```

`requirements.txt` — no new dependencies. The renderer uses only stdlib modules
(`html`, `pathlib`) plus `lxml`, which is already required.

---

## Chapter 6 — Verification

```bash
# 1. Convert and render
python main.py sample.json output.xml --html output.html

# 2. Open in browser and verify form fields match parameters in sample.json
start output.html    # Windows
open output.html     # macOS

# 3. Run full test suite (should include new renderer tests)
python -m pytest tests/ -v

# 4. Confirm HTML is self-contained (no network requests)
# Use browser DevTools → Network tab → reload → 0 external requests
```

Expected test counts after implementation:
- Existing: 49 converter tests + 58 schema-validator tests = 107 passing
- New: ≥ 10 renderer tests
- Total: ≥ 117 passing
