# CustomConverter — Project Plan

Converts a proprietary algo descriptor format (JSON) to FIXATDL 1.1 XML,
validates the output against the official FIXATDL 1.1 XSD schema, validates
the input JSON against 25 structural and semantic rules, and renders strategies
as interactive self-contained HTML pages for in-browser review.

Three independent CLI tools are provided:

| Tool | Purpose |
|------|---------|
| `main.py` | Convert JSON → FIXATDL 1.1 XML, with optional HTML rendering |
| `validate_json.py` | Validate a JSON algo descriptor (JSON-01..25) |
| `validate_schema.py` | Validate any ATDL XML document (3 phases, REF-01..07, SEM-01..16) |

---

## Input Format

Standard JSON, one algo per file:

```json
{
  "AlgoName": {
    "PARAMETERS": [
      {
        "ParamKey": {
          "NAME": "paramName",
          "DESCRIPTION": "Human-readable description",
          "TYPE": "String_t",
          "FIXTAGNUMBER": 5001,
          "SUPPORTED_VALUES": ["A", "B", "C"]
        }
      }
    ]
  }
}
```

Top-level key is the algo name.  Each element in `PARAMETERS` is a
single-key dict (`{ PARAM_KEY: { ...fields... } }`).

---

## Field Mapping

| Input field        | FIXATDL output                          | Notes |
|--------------------|-----------------------------------------|-------|
| Top-level key      | `Strategy@name`, `@uiRep`, `@wireValue` | All three set to the same value |
| `NAME`             | `Parameter@name`                        | |
| `TYPE`             | `Parameter@xsi:type`                    | Prefixed with `core:`, e.g. `core:String_t` |
| `FIXTAGNUMBER`     | `Parameter@fixTag`                      | |
| `SUPPORTED_VALUES` | `<EnumPair enumID="X" wireValue="X"/>`  | One element per value; enumID sanitised to start with a letter |
| `DESCRIPTION`      | XML comment before `<Parameter>`        | `<!-- name: description -->` |

**Hard-coded defaults**

| Attribute                          | Value / Source |
|------------------------------------|----------------|
| `Strategy@fixMsgType`              | `"D"` (NewOrderSingle) |
| `Strategy@providerID`              | `--provider-id` CLI flag (default `CustomProvider`) |
| `Strategy@version`                 | `--strategy-version` CLI flag (default `1`) |
| `Strategies@strategyIdentifierTag` | `--strategy-identifier-tag` CLI flag (default `847`) |
| `Parameter@mutableOnCxlRpl`        | `"true"` |

---

## Output XML Structure

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
    <Parameter name="myParam1" xsi:type="core:String_t" fixTag="5001"
               mutableOnCxlRpl="true">
      <EnumPair enumID="A" wireValue="A"/>
      <EnumPair enumID="B" wireValue="B"/>
      <EnumPair enumID="C" wireValue="C"/>
    </Parameter>
  </Strategy>
</Strategies>
```

**Note:** The root element is `<Strategies>` (namespace
`http://www.fixprotocol.org/ATDL-1-1/Core`), not a `<FIXATDL>` wrapper.
This matches the actual FIXATDL 1.1 XSD (`schemas/atdl-core-1-1.xsd`).

---

## CLI Usage

### Tool 1 — Converter (`main.py`)

```
python main.py input.json output.xml [OPTIONS]

Options:
  --html HTML                 Render strategies to a self-contained HTML file.
  --validate                  Validate output XML against the XSD schema.
                              Exit 0 = valid, exit 1 = schema errors.
  --provider-id ID            Strategy@providerID  (default: CustomProvider)
  --strategy-version VER      Strategy@version     (default: 1)
  --strategy-identifier-tag N Strategies@strategyIdentifierTag (default: 847)
  --schema XSD                Path to XSD file (default: schemas/atdl-core-1-1.xsd)
```

### Tool 2 — JSON Descriptor Validator (`validate_json.py`)

```
python validate_json.py FILE [OPTIONS]

Options:
  --format text|json   Output format (default: text)
  --warnings           Include warnings in output (default: errors only)
  --quiet              Suppress all output; use exit code only

Exit codes: 0 = valid, 1 = errors found, 2 = file/JSON error
```

### Tool 3 — Schema Validator (`validate_schema.py`)

```
python validate_schema.py FILE [OPTIONS]

Options:
  --schema XSD         Path to atdl-core-1-1.xsd (default: schemas/atdl-core-1-1.xsd)
  --phases 1,2,3       Phases to run (default: 1,2,3)
  --format text|json   Output format (default: text)
  --warnings           Include warnings in output (default: errors only)
  --quiet              Suppress all output; use exit code only

Exit codes: 0 = valid, 1 = errors found, 2 = usage/file error
```

---

## Project Layout

```
CustomConverter/
├── main.py                      ← Converter CLI
├── validate_json.py             ← JSON validator CLI
├── validate_schema.py           ← Schema validator CLI
├── sample.json                  ← Minimal example input
├── stealth.json                 ← STEALTH algo example (10 parameters)
├── requirements.txt             ← lxml>=5.0
├── converter/
│   ├── parser.py                ← JSON → AlgoDef / ParameterDef dataclasses
│   ├── builder.py               ← data model → FIXATDL XML (lxml)
│   ├── validator.py             ← XSD validation (lxml)
│   ├── renderer.py              ← lxml XML tree → self-contained HTML page
│   └── json_validator.py        ← JSON descriptor validation (JSON-01..25)
├── schema_validator/
│   ├── loader.py                ← XML parsing and element indexing
│   ├── phase1_xsd.py            ← Phase 1: XSD structural validation
│   ├── phase2_refs.py           ← Phase 2: referential integrity (REF-01..07)
│   ├── phase3_sem.py            ← Phase 3: semantic/business rules (SEM-01..16)
│   ├── reporter.py              ← text and JSON output formatters
│   └── runner.py                ← orchestrator (runs all three phases)
├── schemas/
│   ├── atdl-core-1-1.xsd        ← root schema (imported by validator)
│   ├── atdl-flow-1-1.xsd
│   ├── atdl-layout-1-1.xsd
│   ├── atdl-regions-1-1.xsd
│   ├── atdl-timezones-1-1.xsd
│   └── atdl-validation-1-1.xsd
├── examples/
│   └── adversarial/
│       ├── wrong_fix_tag_range.json     ← JSON-21
│       ├── malformed_names.json         ← JSON-20
│       ├── duplicate_parameters.json    ← JSON-15/16
│       ├── bad_enum_constraints.json    ← JSON-22/23/24
│       ├── unknown_extensions.json      ← JSON-25
│       ├── missing_required_fields.json ← JSON-09/10/11
│       ├── invalid_types.json           ← JSON-13
│       └── multi_error.json             ← JSON-13,16,20,21,22,23,25
└── tests/
    ├── fixtures/
    │   └── valid_full.xml               ← valid ATDL document for schema tests
    ├── test_parser.py                   ← 14 tests
    ├── test_builder.py                  ← 26 tests
    ├── test_validator.py                ←  5 tests
    ├── test_phase1.py                   ←  8 tests
    ├── test_phase2.py                   ← 25 tests
    ├── test_phase3.py                   ← 25 tests
    ├── test_renderer.py                 ← 17 tests
    ├── test_json_validator.py           ← 86 tests
    └── test_adversarial_examples.py     ← 18 tests
```

---

## Implementation Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Project setup, requirements (`lxml≥5.0`) | ✅ Done |
| 2 | Data model — `converter/parser.py` | ✅ Done |
| 3 | XML builder — `converter/builder.py` | ✅ Done |
| 4 | XSD validator — `converter/validator.py` | ✅ Done |
| 5 | Converter CLI — `main.py` | ✅ Done |
| 6 | Initial unit tests (49 tests) | ✅ Done |
| 7 | HTML renderer — `converter/renderer.py` | ✅ Done |
| 8 | `--html` flag wired into `main.py` | ✅ Done |
| 9 | Renderer tests — `tests/test_renderer.py` (17 tests) | ✅ Done |
| 10 | Schema validator — `schema_validator/` package | ✅ Done |
| 11 | Schema validator CLI — `validate_schema.py` | ✅ Done |
| 12 | Schema validator tests — `test_phase{1,2,3}.py` (58 tests) | ✅ Done |
| 13 | JSON descriptor validator — `converter/json_validator.py` (25 rules) | ✅ Done |
| 14 | JSON validator CLI — `validate_json.py` | ✅ Done |
| 15 | JSON validator tests — `test_json_validator.py` (86 tests) | ✅ Done |
| 16 | Adversarial examples — `examples/adversarial/` (8 files) | ✅ Done |
| 17 | Adversarial example tests — `test_adversarial_examples.py` (18 tests) | ✅ Done |

---

## Running Tests

```bash
python -m pytest tests/ -v
```

228 tests pass across the full pipeline.
