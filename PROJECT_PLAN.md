# Converter and Validator for ATDL

Converts a proprietary algo descriptor format (JSON) to FIXATDL 1.1 XML and
optionally validates the output against the official FIXATDL 1.1 XSD schema.

In addition, enables rendering ATDL into an interactive HTML page for a human and interactive in-browser verification.

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

| Input field       | FIXATDL output                          | Notes                                    |
|-------------------|-----------------------------------------|------------------------------------------|
| Top-level key     | `Strategy@name`, `@uiRep`, `@wireValue` | All three set to the same value          |
| `NAME`            | `Parameter@name`                        |                                          |
| `TYPE`            | `Parameter@xsi:type`                    | Prefixed with `core:`, e.g. `core:String_t` |
| `FIXTAGNUMBER`    | `Parameter@fixTag`                      |                                          |
| `SUPPORTED_VALUES`| `<EnumPair enumID="X" wireValue="X"/>`  | One element per value; enumID sanitised to start with a letter |
| `DESCRIPTION`     | XML comment before `<Parameter>`        | `<!-- name: description -->`             |

**Hard-coded defaults**

| Attribute                         | Value / Source                         |
|-----------------------------------|----------------------------------------|
| `Strategy@fixMsgType`             | `"D"` (NewOrderSingle)                 |
| `Strategy@providerID`             | `--provider-id` CLI flag (default `CustomProvider`) |
| `Strategy@version`                | `--strategy-version` CLI flag (default `1`) |
| `Strategies@strategyIdentifierTag`| `--strategy-identifier-tag` CLI flag (default `847`) |
| `Parameter@mutableOnCxlRpl`       | `"true"`                               |

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

```
python main.py input.json output.xml [OPTIONS]

Options:
  --validate                  Validate output XML against the XSD schema.
                              Exit 0 = valid, exit 1 = schema errors.
  --provider-id ID            Strategy@providerID  (default: CustomProvider)
  --strategy-version VER      Strategy@version     (default: 1)
  --strategy-identifier-tag N Strategies@strategyIdentifierTag (default: 847)
  --schema XSD                Path to XSD file (default: schemas/atdl-core-1-1.xsd)
```

---

## Project Layout

```
CustomConverter/
├── main.py                  ← CLI entrypoint
├── converter/
│   ├── __init__.py
│   ├── parser.py            ← JSON → AlgoDef / ParameterDef dataclasses
│   ├── builder.py           ← data model → FIXATDL XML (lxml)
│   └── validator.py         ← XSD validation (lxml)
├── schemas/
│   ├── atdl-core-1-1.xsd    ← root schema (imported by validator)
│   ├── atdl-flow-1-1.xsd
│   ├── atdl-layout-1-1.xsd
│   ├── atdl-regions-1-1.xsd
│   ├── atdl-timezones-1-1.xsd
│   └── atdl-validation-1-1.xsd
├── tests/
│   ├── test_parser.py       ← 14 tests
│   ├── test_builder.py      ← 26 tests
│   └── test_validator.py    ← 5 tests
├── sample.json              ← example input
├── requirements.txt         ← lxml>=5.0
└── PROJECT_PLAN.md          ← this file
```

---

## Implementation Status

| Phase | Description                   | Status      |
|-------|-------------------------------|-------------|
| 1     | Project setup, requirements   | ✅ Done      |
| 2     | Data model (`parser.py`)      | ✅ Done      |
| 3     | XML builder (`builder.py`)    | ✅ Done      |
| 4     | Validator (`validator.py`)    | ✅ Done      |
| 5     | CLI entrypoint (`main.py`)    | ✅ Done      |
| 6     | Unit tests (49 tests, all pass)| ✅ Done     |
| 7     | PROJECT_PLAN.md update        | ✅ Done      |

---

## Running Tests

```bash
python -m pytest tests/ -v
```

All 49 tests pass.
