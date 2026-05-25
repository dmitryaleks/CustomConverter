# FIXatdl 1.1 Programmatic Validator

`fixatdl_validator.py` is a **single, self-contained Python module** (standard
library only — no `lxml`, no XSD files at runtime) that validates a FIXatdl 1.1
document against the rules of the *FIX Algorithmic Trading Definition Language
v1.1 Specification with Errata 20101221* and its six XML Schema files.

Every rule is embedded directly in the code and assigned a stable **rule ID**.
The validator returns a JSON result with an overall pass/fail status and an
array of findings.

## Usage

CLI:

```bash
python fixatdl_validator.py document.xml            # compact JSON
python fixatdl_validator.py document.xml --pretty   # indented JSON
python fixatdl_validator.py document.xml --warnings-as-errors
python fixatdl_validator.py --list-rules            # dump the rule catalogue
```

Exit code is `0` when valid, `1` when invalid, `2` on usage error.

Library:

```python
from fixatdl_validator import validate_file, validate_string
result = validate_file("document.xml")
print(result["valid"], result["summary"])
```

## Output shape

```json
{
  "valid": false,
  "source": "document.xml",
  "summary": { "errors": 2, "warnings": 1, "rules": 71 },
  "errors": [
    {
      "rule_id": "PARAM-08",
      "severity": "error",
      "element": "Parameter",
      "attribute": "localMktTz",
      "line": 12,
      "message": "Parameter/@localMktTz is only applicable to UTCTimestamp_t ..."
    }
  ]
}
```

* `valid` is `true` only when there are **zero `error`-level findings**.
  `warning`-level findings never make a document invalid (unless
  `--warnings-as-errors` is given).
* `errors` contains **all** findings (errors and warnings), each with its source
  line number.

## What it checks

71 rules grouped by category. Run `--list-rules` for the full catalogue.

| Prefix   | Area | Examples |
|----------|------|----------|
| `XML-*`  | Well-formedness | `XML-01` |
| `DOC-*`  | Root `<Strategies>` | required `strategyIdentifierTag`, boolean/positive-integer attrs, ≥1 `<Strategy>` |
| `STR-*`  | `<Strategy>` | name pattern + uniqueness, required `wireValue`/`version`, `fixMsgType` enum |
| `PARAM-*`| `<Parameter>` | valid `xsi:type`, name pattern/uniqueness, min/max applicability + ordering, type-specific attribute applicability (`localMktTz`, `precision`, `multiplyBy100`, …), `constValue`/`minValue`/`maxValue` datatype checks, transport (`tag957Support` vs `fixTag`) |
| `ENUM-*` | `<EnumPair>` | required `enumID`/`wireValue`, `enumID` pattern + uniqueness |
| `EDIT-*` | `<Edit>` expressions | `operator` xor `logicOperator`, `field2` xor `value`, operator/logic enums, operand requirements, parent-must-be-logical, field reference resolution (parameter vs `FIX_` vs control), required `@id` for top-level edits |
| `EREF-*` | `<EditRef>` | id required + must resolve to a declared `Edit` |
| `SEDIT-*`| `<StrategyEdit>` | required `errorMessage`, exactly one `Edit`/`EditRef` |
| `SRULE-*`| `<StateRule>` | exactly one child `Edit`, boolean `enabled`/`visible` |
| `CTRL-*` | `<Control>` | valid `xsi:type`, unique `ID`, `parameterRef` resolution, `ListItem`/`checkedEnumRef`/`uncheckedEnumRef` ↔ `EnumPair` binding, `initPolicy`/`initFixField`, `Clock_t` `localMktTz`, type-specific attribute applicability |
| `LAY-*`  | `<StrategyLayout>`/`<StrategyPanel>` | one panel, no mixed children, `orientation`/`border` enums |
| `GEO-*`  | `<Regions>`/`<Markets>`/`<SecurityTypes>` | region-name enum, `inclusion` enum, `CountryCode` pattern, required `MICCode` |
| `RG-*`   | `<RepeatingGroup>` | required `minSize`, `fixTag`/`name` enums, ≥1 `Parameter` |

The 10 "Dependencies and Structural Constraints beyond XML Schema" from the
specification are covered by: `EDIT-01` (#1), `EDIT-03` (#2), `LAY-02` (#3),
`EDIT-10` (#4/#5/#7), `EDIT-08` (#6), `CTRL-03` (#8), `CTRL-04` (#9),
`CTRL-05` (#10).

## Notes

* **Namespace-transparent.** Parsing reduces elements/attributes to local names,
  so documents using either the `FIXatdl-1-1` or the legacy `ATDL-1-1`
  namespace URIs validate identically. Prefixes on `xsi:type` values
  (e.g. `lay:Clock_t`) are stripped before interpretation.
* **Errata accommodations.** `StrategyEdit` accepts both `@errorMessage` (the
  schema) and `@errorMsg` (the spec attribute table).
* The embedded `localMktTz` timezone list is taken verbatim from
  `fixatdl-timezones-1-1.xsd` (trailing whitespace stripped).

## Tests

```bash
python -m pytest test_fixatdl_validator.py -q
```

The official `specification/SampleStrategiesFor-v1.1.xml` validates clean.
