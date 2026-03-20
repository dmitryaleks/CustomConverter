# CustomConverter

Convert a proprietary ATDL JSON algorithm descriptor into valid **FIXATDL 1.1 XML**, then optionally validate the result against the official FIXATDL 1.1 XSD schemas.

Two independent CLI tools are provided:

| Tool | Purpose |
|---|---|
| `main.py` | Convert a JSON algo descriptor → FIXATDL 1.1 XML, with optional HTML rendering |
| `validate_schema.py` | Validate any ATDL XML document (structural + referential + semantic) |

---

## Requirements

- Python 3.10+
- [`lxml`](https://lxml.de/) >= 5.0

```bash
pip install -r requirements.txt
```

---

## Project Structure

```
CustomConverter/
├── main.py                      # Converter CLI
├── validate_schema.py           # Schema validator CLI
├── sample.json                  # Example input JSON
├── stealth.json                 # STEALTH algo example (10 parameters)
├── requirements.txt
├── converter/
│   ├── parser.py                # JSON → AlgoDef/ParameterDef dataclasses
│   ├── builder.py               # dataclasses → lxml XML tree
│   ├── validator.py             # XSD validation (used by --validate flag)
│   └── renderer.py              # lxml XML tree → self-contained HTML page
├── schema_validator/
│   ├── loader.py                # XML parsing and element indexing
│   ├── phase1_xsd.py            # Phase 1: XSD structural validation
│   ├── phase2_refs.py           # Phase 2: referential integrity (REF-01..07)
│   ├── phase3_sem.py            # Phase 3: semantic/business rules (SEM-01..16)
│   ├── reporter.py              # Text and JSON output formatters
│   └── runner.py                # Orchestrator (runs all three phases)
├── schemas/
│   ├── atdl-core-1-1.xsd        # Root schema (imports the others)
│   ├── atdl-validation-1-1.xsd
│   ├── atdl-layout-1-1.xsd
│   ├── atdl-flow-1-1.xsd
│   ├── atdl-regions-1-1.xsd
│   └── atdl-timezones-1-1.xsd
└── tests/
    ├── fixtures/
    │   └── valid_full.xml        # Valid ATDL document exercising all sub-schemas
    ├── test_parser.py
    ├── test_builder.py
    ├── test_validator.py
    ├── test_phase1.py
    ├── test_phase2.py
    ├── test_phase3.py
    └── test_renderer.py
```

---

## Tool 1 — Converter (`main.py`)

Converts a proprietary ATDL JSON descriptor into a FIXATDL 1.1 XML file.

### Input JSON format

The JSON file must have exactly one top-level key — the algorithm name. Its value must contain a `PARAMETERS` array where each item is a single-key object:

```json
{
  "MyAlgo": {
    "PARAMETERS": [
      {
        "MyParam1": {
          "NAME": "myParam1",
          "DESCRIPTION": "My first parameter",
          "TYPE": "String_t",
          "FIXTAGNUMBER": 5001,
          "SUPPORTED_VALUES": ["A", "B", "C"]
        }
      },
      {
        "MyParam2": {
          "NAME": "myParam2",
          "DESCRIPTION": "An integer param with no enum values",
          "TYPE": "Int_t",
          "FIXTAGNUMBER": 5002
        }
      }
    ]
  }
}
```

#### Field reference

| JSON field | Required | Maps to | Notes |
|---|---|---|---|
| Top-level key | Yes | `Strategy@name`, `@uiRep`, `@wireValue` | The algo name |
| `NAME` | Yes | `Parameter@name` | Parameter name |
| `TYPE` | Yes | `Parameter@xsi:type` | FIX type, e.g. `String_t`, `Int_t`, `Qty_t` |
| `FIXTAGNUMBER` | Yes | `Parameter@fixTag` | Positive integer |
| `DESCRIPTION` | No | XML comment before `<Parameter>` | Not a standard ATDL attribute |
| `SUPPORTED_VALUES` | No | `<EnumPair>` children | List of strings |

#### Supported TYPE values

Any FIXATDL 1.1 parameter type:
`String_t`, `MultipleCharValue_t`, `MultipleStringValue_t`, `Int_t`, `Float_t`,
`Qty_t`, `Price_t`, `PriceOffset_t`, `Amt_t`, `Percentage_t`, `Boolean_t`,
`Char_t`, `UTCTimestamp_t`, `UTCTimeOnly_t`, `LocalMktDate_t`, `MonthYear_t`,
`Data_t`, `Country_t`, `Currency_t`, `Exchange_t`, `Language_t`, `TagNum_t`,
`SeqNum_t`, `Length_t`, `NumInGroup_t`, `UTCDateOnly_t`, `LocalMktTime_t`.

### Usage

```
python main.py INPUT OUTPUT [OPTIONS]
```

| Argument | Description |
|---|---|
| `INPUT` | Path to the input JSON file |
| `OUTPUT` | Path for the output XML file (created or overwritten) |
| `--html HTML` | Render strategies to a self-contained interactive HTML file |
| `--validate` | Validate the output XML against the bundled XSD after writing |
| `--provider-id ID` | Value for `Strategy@providerID` (default: `CustomProvider`) |
| `--strategy-version VER` | Value for `Strategy@version` (default: `1`) |
| `--strategy-identifier-tag TAG` | FIX tag for `Strategies@strategyIdentifierTag` (default: `847`) |
| `--schema XSD` | Path to `atdl-core-1-1.xsd` (default: `schemas/atdl-core-1-1.xsd`) |

#### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success (and XSD validation passed when `--validate` is used) |
| `1` | XSD validation errors (only when `--validate` is used) |
| `2` | Input/IO error (file not found, invalid JSON, write failure) |

### Examples

**Basic conversion:**

```bash
python main.py sample.json output.xml
```

**Convert and validate against the bundled XSD:**

```bash
python main.py sample.json output.xml --validate
```

**Custom provider and version:**

```bash
python main.py sample.json output.xml --validate --provider-id ACME --strategy-version 2
```

**Convert and render an interactive HTML preview:**

```bash
python main.py sample.json output.xml --html output.html
```

**Full pipeline — convert, render HTML, and validate XSD in one step:**

```bash
python main.py sample.json output.xml --html output.html --validate
```

**Custom strategy identifier tag:**

```bash
python main.py sample.json output.xml --strategy-identifier-tag 5000
```

### HTML output

The `--html` flag produces a **self-contained, offline-capable HTML page** with no external dependencies. Each strategy is rendered as an interactive form:

- Parameter types are automatically mapped to appropriate HTML controls (see table below).
- Descriptions from the JSON `DESCRIPTION` field appear as hint text below each control.
- Required fields (parameters with `use="required"`) are highlighted with an orange left border.
- Clicking **Validate & Preview Values** validates all required fields and renders a wire-value summary table.
- Clicking **Reset** clears the form and hides the summary.

#### Parameter type → HTML control mapping

| FIXATDL type | HTML control |
|---|---|
| `String_t` | `<input type="text">` |
| `Int_t`, `SeqNum_t`, `Length_t`, `NumInGroup_t`, `TagNum_t` | `<input type="number" step="1">` |
| `Float_t`, `Qty_t`, `Price_t`, `PriceOffset_t`, `Amt_t`, `Numeric_t` | `<input type="number">` |
| `Percentage_t` | `<input type="number" min="0" max="100">` + `%` suffix |
| `Char_t` | `<input type="text" maxlength="1">` |
| `Boolean_t` | `<input type="checkbox">` |
| `Currency_t` | `<input type="text" maxlength="3" pattern="[A-Z]{3}">` |
| `Exchange_t` | `<input type="text" maxlength="4">` |
| `Month-Year_t` | `<input type="month">` |
| `UTCTimeStamp_t` | `<input type="datetime-local">` |
| `UTCTimeOnly_t`, `LocalMktTime_t` | `<input type="time">` |
| `UTCDate_t` | `<input type="date">` |
| `Data_t` | `<textarea>` |
| `MultipleCharValue_t`, `MultipleStringValue_t` | `<select multiple>` |
| Any type with `SUPPORTED_VALUES` | `<select>` (single, options from enum pairs) |
| Any type with `constValue` | `<input readonly>` |

### Output XML

The generated XML follows the FIXATDL 1.1 structure. For `sample.json`:

```xml
<?xml version='1.0' encoding='UTF-8'?>
<Strategies xmlns="http://www.fixprotocol.org/ATDL-1-1/Core"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xmlns:core="http://www.fixprotocol.org/ATDL-1-1/Core"
            strategyIdentifierTag="847"
            xsi:schemaLocation="http://www.fixprotocol.org/ATDL-1-1/Core schemas/atdl-core-1-1.xsd">
  <Strategy name="MyAlgo" uiRep="MyAlgo" wireValue="MyAlgo"
            fixMsgType="D" providerID="CustomProvider" version="1">
    <!-- myParam1: My first parameter -->
    <Parameter name="myParam1" xsi:type="core:String_t" fixTag="5001" mutableOnCxlRpl="true">
      <EnumPair enumID="A" wireValue="A"/>
      <EnumPair enumID="B" wireValue="B"/>
      <EnumPair enumID="C" wireValue="C"/>
    </Parameter>
    <!-- myParam2: An integer param with no enum values -->
    <Parameter name="myParam2" xsi:type="core:Int_t" fixTag="5002" mutableOnCxlRpl="true"/>
  </Strategy>
</Strategies>
```

**Notes on generated attributes:**

- `Strategy@uiRep` and `@wireValue` are both set to the algo name.
- `Strategy@fixMsgType` is always `"D"` (NewOrderSingle).
- `Parameter@mutableOnCxlRpl` is always `"true"`.
- `SUPPORTED_VALUES` items whose first character is not a letter are prefixed with `V_` to satisfy the `EnumPair@enumID` pattern constraint (`[A-Za-z][A-Za-z0-9_]{0,255}`).
- `DESCRIPTION` is written as a preceding XML comment, not as an XML attribute (not part of the ATDL schema).

---

## Tool 2 — Schema Validator (`validate_schema.py`)

Validates any FIXATDL 1.1 XML document through three escalating phases. Each phase catches a different class of errors:

| Phase | Type | Catches |
|---|---|---|
| 1 | **Structural** | XSD constraint violations (missing attributes, bad types, ordering) |
| 2 | **Referential** | Cross-element references that do not resolve (REF-01..07) |
| 3 | **Semantic** | Business rule violations expressed in prose, not schema (SEM-01..16) |

Phase 2 and Phase 3 are skipped automatically if Phase 1 fails — referential and semantic checks are unreliable on structurally invalid XML.

### Usage

```
python validate_schema.py FILE [OPTIONS]
```

| Argument | Description |
|---|---|
| `FILE` | Path to the ATDL XML document to validate |
| `--schema XSD` | Path to `atdl-core-1-1.xsd` (default: `schemas/atdl-core-1-1.xsd`) |
| `--phases PHASES` | Comma-separated phases to run: `1`, `2`, `3` (default: `1,2,3`) |
| `--format text\|json` | Output format (default: `text`) |
| `--warnings` | Include warnings in output (default: errors only) |
| `--quiet` | Suppress all output; rely on exit code only |

#### Exit codes

| Code | Meaning |
|---|---|
| `0` | All selected phases passed — no errors found |
| `1` | One or more validation errors found |
| `2` | Usage error or file not found |

### Examples

**Validate with default settings (all phases, text output):**

```bash
python validate_schema.py output.xml
```

```
Validation passed — no errors found.
```

**Validate and include warnings:**

```bash
python validate_schema.py output.xml --warnings
```

```
[Phase 3] [SEM-04] WARNING (line 12): Strategy 'MyAlgo', Parameter 'myParam1': const='true' but no constValue attribute supplied
```

**JSON output (useful for CI pipelines):**

```bash
python validate_schema.py output.xml --format json
```

```json
[
  {
    "severity": "error",
    "phase": 2,
    "rule_id": "REF-01",
    "message": "Strategy 'MyAlgo', Control 'ctrlSide': parameterRef='BadName' does not match any Parameter in this strategy",
    "element": "Strategy[@name='MyAlgo']/Control[@ID='ctrlSide']",
    "line": 34
  }
]
```

**JSON output with warnings:**

```bash
python validate_schema.py output.xml --format json --warnings
```

**Run Phase 1 only (XSD check):**

```bash
python validate_schema.py output.xml --phases 1
```

**Run Phases 2 and 3 only (skip XSD):**

```bash
python validate_schema.py output.xml --phases 2,3
```

**Silent check for use in shell scripts:**

```bash
python validate_schema.py output.xml --quiet
if [ $? -eq 0 ]; then
    echo "Valid"
else
    echo "Invalid — check errors"
fi
```

### Text output format

Each line follows the pattern:

```
[Phase N] [RULE-ID] ERROR (line L): <message>
[Phase N] [RULE-ID] WARNING (line L): <message>
```

Line numbers are included when available (Phases 2 and 3). Phase 1 errors include the XSD error message directly from lxml.

### Validation rules reference

#### Phase 1 — Structural (XSD)

Enforced automatically by `atdl-core-1-1.xsd` and its imports. Common failures:

- `Strategies@strategyIdentifierTag` missing or not a positive integer
- `Strategy@name`, `@wireValue`, `@version` missing
- `Parameter@name` / `EnumPair@enumID` violating pattern `[A-Za-z][A-Za-z0-9_]{0,255}`
- Invalid enumeration values for `Region@name`, `Edit@operator`, `Edit@logicOperator`
- Element order violations (e.g. `val:StrategyEdit` placed before `lay:StrategyLayout`)

#### Phase 2 — Referential integrity

| Rule | Check |
|---|---|
| REF-01 | `Control@parameterRef` must name a `Parameter` in the same `Strategy` |
| REF-02 | Each `Parameter` is referenced by at most one `Control@parameterRef` |
| REF-03 | `EditRef@id` in `StrategyEdit`/`Edit` must resolve to a declared `Edit@id` |
| REF-04 | `EditRef@id` inside `StateRule` must resolve to a declared `Edit@id` |
| REF-05 | `Edit@field` and `Edit@field2` must name a `Parameter` in the same `Strategy` |
| REF-06 | `ListItem@enumID` must match an `EnumPair@enumID` on the referenced parameter |
| REF-07 | `Control@initValue` for list controls must be a `ListItem@enumID` present in that control |

#### Phase 3 — Semantic / business rules

| Rule | Severity | Check |
|---|---|---|
| SEM-01 | Error | `EnumPair@wireValue` values must be unique within a `Parameter` |
| SEM-02 | Error | `EnumPair@enumID` values must be unique within a `Parameter` |
| SEM-03 | Error | `const="true"` and `use="required"` are contradictory |
| SEM-04 | Warning | `const="true"` without a `constValue` attribute |
| SEM-05 | Error | `Strategy@name` values must be unique within `Strategies` |
| SEM-06 | Error | `Parameter@name` values must be unique within a `Strategy` |
| SEM-07 | Error | `localMktTz` must be a valid IANA timezone from `atdl-timezones-1-1.xsd` |
| SEM-08 | Error | `Country@CountryCode` must be valid for the declared `Region@name` |
| SEM-09 | Error | `Market@MICCode` must match `[A-Z0-9]{4}` |
| SEM-10 | Error | `Edit` with `logicOperator` requires child `Edit`/`EditRef`; with `operator` must have none |
| SEM-11 | Error | `Edit@field2` and `Edit@value` are mutually exclusive |
| SEM-12 | Error | `Edit@operator` and `Edit@logicOperator` are mutually exclusive |
| SEM-13 | Error | `minValue` ≤ `maxValue` for numeric parameter types |
| SEM-14 | Error | `minLength` ≤ `maxLength` for string parameter types |
| SEM-15 | Error | `increment` must be positive for `Slider_t` and `SingleSpinner_t` controls |
| SEM-16 | Error | `Strategies@strategyIdentifierTag` must not match any `Parameter@fixTag` |

---

## Running Tests

```bash
python -m pytest tests/ -v
```

121 tests cover the converter pipeline (parser, builder, validator, renderer) and all three validation phases.

```
tests/test_parser.py       14 tests — JSON parsing, error cases
tests/test_builder.py      26 tests — XML structure, attributes, EnumPairs
tests/test_validator.py     5 tests — XSD validation pass/fail
tests/test_phase1.py        8 tests — structural checks
tests/test_phase2.py       25 tests — REF-01..07
tests/test_phase3.py       25 tests — SEM-01..16
tests/test_renderer.py     14 tests — HTML control mapping, CLI --html flag
```

---

## End-to-End Example

```bash
# 1. Convert sample.json to FIXATDL XML
python main.py sample.json output.xml

# 2. Validate the result with full detail
python validate_schema.py output.xml --warnings

# 3. Validate in JSON format (e.g. for downstream tooling)
python validate_schema.py output.xml --format json --warnings

# 4. Convert and validate in one step
python main.py sample.json output.xml --validate

# 5. Convert, validate, and render an interactive HTML preview
python main.py sample.json output.xml --validate --html output.html
```

## STEALTH Algo Example

`stealth.json` is a more complete descriptor demonstrating a range of parameter types:

| Parameter | FIXATDL type | HTML control |
|---|---|---|
| `StartTime` | `UTCTimeOnly_t` | time picker |
| `EndTime` | `UTCTimeOnly_t` | time picker |
| `TargetPrice` | `Price_t` | number input |
| `DisplayQuantity` | `Qty_t` | number input |
| `MinFillSize` | `Qty_t` | number input |
| `MaxParticipationRate` | `Percentage_t` | number input (0–100) + `%` |
| `Sentiment` | `String_t` + enum | dropdown (`Bullish` / `Bearish` / `Neutral`) |
| `VenueFocus` | `String_t` + enum | dropdown (`DarkOnly` / `LitOnly` / `Mixed` / `SmartRoute`) |
| `AllowOddLots` | `Boolean_t` | checkbox |
| `PostTradeAction` | `String_t` + enum | dropdown (`ReportOnly` / `CancelRemainder` / `MarketOnClose` / `Rollover`) |

```bash
# Convert STEALTH descriptor → XML + HTML in one step
python main.py stealth.json stealth.xml --validate --html stealth.html

# Open the interactive HTML preview
start stealth.html    # Windows
open stealth.html     # macOS
```

The rendered `stealth.html` is a fully self-contained page — no network requests, no frameworks. Fill in parameter values and click **Validate & Preview Values** to see the wire-value summary.
