# Schema Validator — Implementation Plan

## Purpose

Extend the existing `--validate` flag (which only checks XSD structural
conformance) with a standalone, multi-layer validation tool that catches errors
the XSD alone cannot express.  The tool operates in three escalating phases:

1. **Structural** — XSD validation against all six ATDL 1.1 schemas
2. **Referential integrity** — cross-element references that the XSD's `xs:key`
   / `xs:keyref` mechanism does not cover across optional sub-schema boundaries
3. **Semantic / business rules** — FIXATDL-specific invariants derived from the
   specification prose and schema annotations

---

## Schema Overview (Inputs to the Validator)

| File | Namespace | Role | Required |
|------|-----------|------|----------|
| `atdl-core-1-1.xsd` | `…/Core` | Data model: strategies, parameters, FIX mapping | **Yes** |
| `atdl-validation-1-1.xsd` | `…/Validation` | Conditional validation rules (`Edit`, `StrategyEdit`) | Optional |
| `atdl-layout-1-1.xsd` | `…/Layout` | UI controls and panel layout | Optional |
| `atdl-flow-1-1.xsd` | `…/Flow` | Dynamic state rules (enabled / visible / value) | Optional |
| `atdl-regions-1-1.xsd` | `…/Regions` | ISO 3166-1 country-to-region mappings | Supporting |
| `atdl-timezones-1-1.xsd` | `…/Timezones` | IANA timezone enumeration (425+ values) | Supporting |

The core schema imports all others; the single entry-point for XSD validation
is `atdl-core-1-1.xsd`.

---

## Validation Phases and Rules

### Phase 1 — Structural (XSD)

Run `lxml.etree.XMLSchema` against `atdl-core-1-1.xsd`.  Catches:

- Missing required attributes (`name`, `wireValue`, `version` on `Strategy`;
  `strategyIdentifierTag` on `Strategies`; `minSize` on `RepeatingGroup`, etc.)
- Type constraint violations (e.g. `fixTag` not a positive integer)
- Name pattern violations (`[A-Za-z][A-Za-z0-9_]{0,255}` for strategy/parameter
  names and `EnumPair@enumID`)
- Invalid enumerations (`Region@name`, `SecurityType@name`, `operator`,
  `logicOperator`, control `initPolicy`, panel `orientation`/`border`, etc.)
- Element ordering and cardinality errors

### Phase 2 — Referential Integrity

Checks that cross-element references resolve correctly.  The XSD enforces some
of these within a single schema but not across optional sub-schema boundaries.

| Rule ID | Description |
|---------|-------------|
| **REF-01** | `Control@parameterRef` must match a `Parameter@name` in the same `Strategy` |
| **REF-02** | Each `Parameter@name` is referenced by **at most one** `Control@parameterRef` within a `Strategy` |
| **REF-03** | `EditRef@id` must match an `Edit@id` declared at `Strategies` or `Strategy` scope |
| **REF-04** | `StateRule` child `EditRef@id` must resolve to a reachable `Edit@id` |
| **REF-05** | `Edit@field` and `Edit@field2` must match a `Parameter@name` in the same `Strategy` |
| **REF-06** | `ListItem@enumID` in a `Control` must match an `EnumPair@enumID` on the `Parameter` referenced by that control's `parameterRef` |
| **REF-07** | `Control@initValue` for list-type controls (DropDownList, SingleSelectList, etc.) must be a valid `enumID` present in the control's `ListItem` collection |

### Phase 3 — Semantic / Business Rules

Constraints expressed only in specification prose or schema annotations.

| Rule ID | Description |
|---------|-------------|
| **SEM-01** | `EnumPair@wireValue` values must be **unique** within a single `Parameter` |
| **SEM-02** | `EnumPair@enumID` values must be **unique** within a single `Parameter` |
| **SEM-03** | A `Parameter` with `const="true"` must not also have `use="required"` |
| **SEM-04** | A `Parameter` with `const="true"` should supply a `constValue` attribute appropriate to its `xsi:type` |
| **SEM-05** | `Strategy@name` values must be **unique** within `Strategies` |
| **SEM-06** | `Parameter@name` values must be **unique** within a `Strategy` |
| **SEM-07** | Time parameters (`UTCTimeStamp_t`, `LocalMktTime_t`) that carry a `localMktTz` attribute must supply a value from the `LocalMktTz_t` enumeration in `atdl-timezones-1-1.xsd` |
| **SEM-08** | `Country@CountryCode` values must be valid ISO 3166-1 alpha-2 codes as enumerated in `atdl-regions-1-1.xsd` for the declared region |
| **SEM-09** | `Market@MICCode` must be exactly four uppercase alphanumeric characters (`[A-Z0-9]{4}`) |
| **SEM-10** | `Edit` with `logicOperator` must contain at least one child `Edit` or `EditRef`; `Edit` with `operator` must contain no children |
| **SEM-11** | `Edit@field2` and `Edit@value` are mutually exclusive |
| **SEM-12** | `Edit@operator` and `Edit@logicOperator` are mutually exclusive |
| **SEM-13** | `Parameter@minValue` ≤ `Parameter@maxValue` where both are present (applies to `Int_t`, `Float_t`, `Qty_t`, `Price_t`, `PriceOffset_t`, `Amt_t`, `Percentage_t`) |
| **SEM-14** | `Parameter@minLength` ≤ `Parameter@maxLength` where both are present (`String_t`, `MultipleCharValue_t`, `MultipleStringValue_t`, `Data_t`) |
| **SEM-15** | `Slider_t@increment` and `SingleSpinner_t@increment` must be positive when supplied |
| **SEM-16** | `Strategies@strategyIdentifierTag` must not collide with any `Parameter@fixTag` in the document |

---

## Project File Layout

```
CustomConverter/
├── schema_validator/
│   ├── __init__.py
│   ├── loader.py          ← parse XML; index elements; load timezone/region enums from XSD
│   ├── phase1_xsd.py      ← Phase 1: lxml XSD structural validation
│   ├── phase2_refs.py     ← Phase 2: referential integrity checks
│   ├── phase3_sem.py      ← Phase 3: semantic / business rules
│   ├── reporter.py        ← format and emit errors/warnings (text + JSON)
│   └── runner.py          ← orchestrate all phases; return ValidationResult
├── validate_schema.py     ← CLI entrypoint
└── tests/
    ├── fixtures/
    │   ├── valid_full.xml           ← document exercising all sub-schemas
    │   ├── invalid_xsd.xml          ← missing required attribute
    │   ├── invalid_ref_control.xml  ← REF-01: bad parameterRef
    │   ├── invalid_ref_edit.xml     ← REF-03: unresolved EditRef
    │   ├── invalid_sem_dup_wire.xml ← SEM-01: duplicate wireValue
    │   └── invalid_sem_minmax.xml   ← SEM-13: minValue > maxValue
    ├── test_phase1.py
    ├── test_phase2.py
    └── test_phase3.py
```

---

## Internal Data Model

```python
@dataclass
class ValidationError:
    phase: int                  # 1, 2, or 3
    rule_id: str                # e.g. "REF-01", "SEM-03", "XSD"
    message: str
    element: str | None = None  # XPath or tag name where the error was found
    line: int | None = None     # source line number if available

@dataclass
class ValidationResult:
    errors: list[ValidationError]
    warnings: list[ValidationError]

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0
```

---

## Module Responsibilities

### `loader.py`
- Parse the ATDL XML document with `lxml.etree.parse`
- Build namespace-aware index maps (all `Strategy`, `Parameter`, `Control`,
  `Edit`, `StrategyEdit`, `EnumPair` elements keyed by name/id)
- Parse `atdl-timezones-1-1.xsd` to extract the full `LocalMktTz_t` enum set
- Parse `atdl-regions-1-1.xsd` to extract country-code sets per region
- Return a `DocumentContext` dataclass holding all indexed elements

### `phase1_xsd.py`
- `run(doc_path, schema_path) -> list[ValidationError]`
- Load schema with `lxml.etree.XMLSchema`; validate; map each error log entry

### `phase2_refs.py`
- `run(ctx: DocumentContext) -> list[ValidationError]`
- Implement REF-01 through REF-07 using the indexed maps (O(1) lookups)

### `phase3_sem.py`
- `run(ctx: DocumentContext) -> list[ValidationError]`
- Implement SEM-01 through SEM-16
- Numeric comparisons cast attribute strings to the appropriate Python types

### `reporter.py`
- `format_text(result: ValidationResult) -> str` — human-readable, line-per-error
- `format_json(result: ValidationResult) -> str` — machine-readable JSON array

### `runner.py`
- `validate(xml_path, schema_path, *, phases=(1,2,3)) -> ValidationResult`
- Short-circuits after Phase 1 if structural errors are present (referential
  and semantic checks are unreliable on structurally invalid XML)
- Allows callers to run a subset of phases (useful in unit tests)

---

## CLI Entrypoint (`validate_schema.py`)

```
usage: validate_schema.py FILE [OPTIONS]

Positional:
  FILE                  Path to the ATDL XML file to validate

Options:
  --schema XSD          Path to atdl-core-1-1.xsd
                        (default: schemas/atdl-core-1-1.xsd)
  --phases 1,2,3        Comma-separated list of phases to run (default: 1,2,3)
  --format text|json    Output format (default: text)
  --warnings            Include warnings in output (default: errors only)
  --quiet               Suppress output; use exit code only
```

**Exit codes:**
- `0` — all selected phases passed (no errors)
- `1` — one or more validation errors found
- `2` — tool usage error or file I/O error

---

## Implementation Steps

| Step | Description |
|------|-------------|
| 1 | Create `schema_validator/` package |
| 2 | Implement `loader.py` — XML parsing and element indexing |
| 3 | Implement `phase1_xsd.py` — wrap lxml XSD validation |
| 4 | Implement `phase2_refs.py` — REF-01 through REF-07 |
| 5 | Implement `phase3_sem.py` — SEM-01 through SEM-16 |
| 6 | Implement `reporter.py` — text and JSON formatters |
| 7 | Implement `runner.py` — orchestrator with short-circuit logic |
| 8 | Implement `validate_schema.py` — CLI entrypoint |
| 9 | Create test fixtures (valid_full + one invalid file per rule category) |
| 10 | Write unit tests for each phase module |

---

## Libraries

| Library | Use | Source |
|---------|-----|--------|
| `lxml` | XML parsing and XSD validation | `requirements.txt` (already present) |
| `argparse` | CLI argument parsing | built-in |
| `dataclasses` | `ValidationError`, `ValidationResult`, `DocumentContext` | built-in |
| `json` | JSON output format | built-in |
| `pathlib` | Path handling | built-in |

No new dependencies are required.

---

## Relationship to Existing Code

- `converter/validator.py` performs Phase 1 only; `phase1_xsd.py` supersedes
  it internally (the converter can optionally delegate to the new module)
- The new tool is a **standalone CLI** (`validate_schema.py`) independent of
  the converter pipeline, but shares the same `schemas/` directory
- Both tools co-exist; the converter's `--validate` flag may be updated in a
  future step to invoke the full three-phase runner instead of Phase 1 alone
