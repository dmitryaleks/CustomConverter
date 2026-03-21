# Implementation Plan — CustomConverter

## Chapter 1 — Project Phases (all complete)

All phases are complete. 228 tests pass across the full pipeline.

| Phase | Module / File | Description | Status |
|-------|--------------|-------------|--------|
| 1 | `requirements.txt`, `.venv` | Project setup, dependencies (`lxml≥5.0`) | ✅ Done |
| 2 | `converter/parser.py` | JSON → `AlgoDef` / `ParameterDef` dataclasses | ✅ Done |
| 3 | `converter/builder.py` | Data model → FIXATDL 1.1 XML (lxml) | ✅ Done |
| 4 | `converter/validator.py` | XSD validation via lxml | ✅ Done |
| 5 | `main.py` | CLI entrypoint (`argparse`) | ✅ Done |
| 6 | `tests/` (initial) | 49 unit tests — parser, builder, validator | ✅ Done |
| 7 | `PROJECT_PLAN.md` | Documentation update | ✅ Done |
| 8 | `converter/renderer.py` | lxml XML tree → self-contained HTML page | ✅ Done |
| 9 | `main.py --html` | CLI `--html` flag wires in renderer | ✅ Done |
| 10 | `tests/test_renderer.py` | 17 renderer tests | ✅ Done |
| 11 | `schema_validator/` | Standalone 3-phase ATDL XML validator | ✅ Done |
| 12 | `validate_schema.py` | Schema validator CLI (`--phases`, `--format`, `--warnings`) | ✅ Done |
| 13 | `tests/test_phase{1,2,3}.py` | 58 schema validator tests (REF-01..07, SEM-01..16) | ✅ Done |
| 14 | `converter/json_validator.py` | JSON descriptor validator — 25 rules (JSON-01..25) | ✅ Done |
| 15 | `validate_json.py` | JSON validator CLI (`--format`, `--warnings`, `--quiet`) | ✅ Done |
| 16 | `tests/test_json_validator.py` | 86 JSON validator tests | ✅ Done |
| 17 | `examples/adversarial/` | 8 adversarial JSON files, one per rule group | ✅ Done |
| 18 | `tests/test_adversarial_examples.py` | 18 disk-based adversarial example tests | ✅ Done |

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

## Chapter 6 — HTML Renderer Verification

```bash
# 1. Convert and render
python main.py sample.json output.xml --html output.html

# 2. Open in browser and verify form fields match parameters in sample.json
start output.html    # Windows
open output.html     # macOS

# 3. Run full test suite
python -m pytest tests/ -v

# 4. Confirm HTML is self-contained (no network requests)
# Use browser DevTools → Network tab → reload → 0 external requests
```

---

## Chapter 7 — JSON Descriptor Validator (`converter/json_validator.py`)

### 7.1 Purpose

Validate a proprietary ATDL JSON algo descriptor before conversion. Catches structural
problems, wrong types, semantic violations, and type-specific constraints with clear rule
IDs and JSON paths, so errors are fixed at the source rather than surfacing as cryptic
XML build failures.

### 7.2 Public API

```python
# converter/json_validator.py
def validate_data(data: Any) -> list[ValidationIssue]: ...
def validate_json(path: str | Path) -> list[ValidationIssue]: ...
```

`validate_data` accepts an already-parsed value. `validate_json` loads the file from
disk, raises `FileNotFoundError` / `ValueError` on I/O or parse errors, then delegates
to `validate_data`.

### 7.3 Rules Reference

| Rule | Severity | Check |
|------|----------|-------|
| JSON-01 | Error | Root must be a JSON object |
| JSON-02 | Error | Root object must have exactly one key (the algo name) |
| JSON-03 | Error | Algo name must be a non-empty string |
| JSON-04 | Error | Algo value must be a JSON object containing a `PARAMETERS` key |
| JSON-05 | Error | `PARAMETERS` must be a JSON array |
| JSON-06 | Error | `PARAMETERS` array must not be empty |
| JSON-07 | Error | Each entry in `PARAMETERS` must be a single-key JSON object |
| JSON-08 | Error | The parameter body must be a JSON object |
| JSON-09 | Error | `NAME` field is required |
| JSON-10 | Error | `TYPE` field is required |
| JSON-11 | Error | `FIXTAGNUMBER` field is required |
| JSON-12 | Error | `NAME` must be a non-empty string |
| JSON-13 | Error | `TYPE` must be a recognised FIXATDL 1.1 parameter type |
| JSON-14 | Error | `FIXTAGNUMBER` must be a positive integer |
| JSON-15 | Error | `NAME` values must be unique within the strategy |
| JSON-16 | Error | `FIXTAGNUMBER` values must be unique within the strategy |
| JSON-17 | Error | `DESCRIPTION`, if present, must be a string |
| JSON-18 | Error | `SUPPORTED_VALUES`, if present, must be a JSON array |
| JSON-19 | Error | Each `SUPPORTED_VALUES` item must be a non-empty string |
| JSON-20 | Error | `NAME` must match `[A-Za-z][A-Za-z0-9_]*` |
| JSON-21 | Warning | `FIXTAGNUMBER` in the standard FIX range 1–4999 |
| JSON-22 | Error | `SUPPORTED_VALUES` items must be unique within a parameter |
| JSON-23 | Error | `Boolean_t` must have 0 or exactly 2 `SUPPORTED_VALUES` entries |
| JSON-24 | Error | `Char_t` / `MultipleCharValue_t` entries must be single characters |
| JSON-25 | Warning | Unrecognised fields in a parameter body |

### 7.4 CLI (`validate_json.py`)

```
python validate_json.py FILE [--format text|json] [--warnings] [--quiet]
```

Exit codes: `0` = valid, `1` = errors found, `2` = file/JSON error.

### 7.5 Tests

`tests/test_json_validator.py` — 86 tests covering all 25 rules, file-based loading,
and the CLI (exit codes, `--format json`, `--warnings`, `--quiet`).

---

## Chapter 8 — Adversarial JSON Examples (`examples/adversarial/`)

### 8.1 Purpose

Eight realistic JSON algo descriptor files that each intentionally trigger specific
validator rules. They serve as living documentation — readable by humans, executable
as tests — showing precisely which input patterns each rule catches.

### 8.2 File Inventory

| File | Rules triggered | Notes |
|------|----------------|-------|
| `wrong_fix_tag_range.json` | 3× JSON-21 (warning) | VWAP algo using FIX tags 38, 44, 126 |
| `malformed_names.json` | 3× JSON-20 (error) | Names starting with digit, containing hyphen, containing spaces |
| `duplicate_parameters.json` | JSON-15 + JSON-16 | Same NAME and FIXTAGNUMBER used twice |
| `bad_enum_constraints.json` | JSON-22 + JSON-23 + JSON-24 | Multi-char Char_t values; Boolean_t with 1 entry; duplicate MultipleCharValue_t entry |
| `unknown_extensions.json` | 5× JSON-25 (warning) | 3 unknown fields on StartTime, 2 on EndTime |
| `missing_required_fields.json` | JSON-09 + JSON-10 + JSON-11 | One required field omitted per parameter |
| `invalid_types.json` | 3× JSON-13 (error) | Java/C# type names: `Double`, `Integer`, `DateTime` |
| `multi_error.json` | JSON-13,16,20,21,22,23,25 | Two parameters hitting 7 distinct rule IDs |

### 8.3 Tests (`tests/test_adversarial_examples.py`)

18 tests in `TestAdversarialExamples`. Each test calls `validate_json(path)` with the
file loaded from disk and asserts on rule ID presence, exact counts, message content,
or severity mix.

---

## Chapter 9 — Current Test Inventory

```
tests/test_parser.py                14 tests — JSON parsing, error cases
tests/test_builder.py               26 tests — XML structure, attributes, EnumPairs
tests/test_validator.py              5 tests — XSD validation pass/fail
tests/test_phase1.py                 8 tests — structural checks (Phase 1 XSD)
tests/test_phase2.py                25 tests — referential integrity (REF-01..07)
tests/test_phase3.py                25 tests — semantic rules (SEM-01..16)
tests/test_renderer.py              17 tests — HTML control mapping, CLI --html flag
tests/test_json_validator.py        86 tests — JSON-01..25, file-based, CLI
tests/test_adversarial_examples.py  18 tests — disk-based adversarial JSON examples
─────────────────────────────────────────────────────────────────────────────────
Total                              228 tests — all passing
