# Schema Validator — Reference

Standalone three-phase validator for FIXATDL 1.1 XML documents.
All implementation steps are complete; 58 tests pass.

---

## Purpose

Extends the existing `--validate` flag (Phase 1 XSD only) with a standalone
multi-layer validation tool that catches errors the XSD alone cannot express.
The tool operates in three escalating phases:

1. **Structural** — XSD validation against all six ATDL 1.1 schemas
2. **Referential integrity** — cross-element references that the XSD's `xs:key`
   / `xs:keyref` mechanism does not cover across optional sub-schema boundaries
3. **Semantic / business rules** — FIXATDL-specific invariants derived from the
   specification prose and schema annotations

Phase 2 and Phase 3 are skipped automatically when Phase 1 reports errors —
referential and semantic checks are unreliable on structurally invalid XML.

---

## Schema Overview

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

## Validation Rules

### Phase 1 — Structural (XSD)

Run `lxml.etree.XMLSchema` against `atdl-core-1-1.xsd`. Catches:

- Missing required attributes (`name`, `wireValue`, `version` on `Strategy`;
  `strategyIdentifierTag` on `Strategies`; `minSize` on `RepeatingGroup`, etc.)
- Type constraint violations (e.g. `fixTag` not a positive integer)
- Name pattern violations (`[A-Za-z][A-Za-z0-9_]{0,255}` for strategy/parameter
  names and `EnumPair@enumID`)
- Invalid enumerations (`Region@name`, `SecurityType@name`, `operator`,
  `logicOperator`, control `initPolicy`, panel `orientation`/`border`, etc.)
- Element ordering and cardinality errors

### Phase 2 — Referential Integrity

| Rule | Description |
|------|-------------|
| REF-01 | `Control@parameterRef` must match a `Parameter@name` in the same `Strategy` |
| REF-02 | Each `Parameter@name` is referenced by at most one `Control@parameterRef` within a `Strategy` |
| REF-03 | `EditRef@id` must match an `Edit@id` declared at `Strategies` or `Strategy` scope |
| REF-04 | `StateRule` child `EditRef@id` must resolve to a reachable `Edit@id` |
| REF-05 | `Edit@field` and `Edit@field2` must match a `Parameter@name` in the same `Strategy` |
| REF-06 | `ListItem@enumID` in a `Control` must match an `EnumPair@enumID` on the `Parameter` referenced by that control's `parameterRef` |
| REF-07 | `Control@initValue` for list-type controls must be a valid `enumID` present in the control's `ListItem` collection |

### Phase 3 — Semantic / Business Rules

| Rule | Severity | Description |
|------|----------|-------------|
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
| SEM-15 | Error | `increment` must be positive for `Slider_t` and `SingleSpinner_t` |
| SEM-16 | Error | `Strategies@strategyIdentifierTag` must not collide with any `Parameter@fixTag` |

---

## Project File Layout

```
CustomConverter/
├── schema_validator/
│   ├── __init__.py
│   ├── loader.py          ← parse XML; index elements; load timezone/region enums from XSD
│   ├── phase1_xsd.py      ← Phase 1: lxml XSD structural validation
│   ├── phase2_refs.py     ← Phase 2: referential integrity checks (REF-01..07)
│   ├── phase3_sem.py      ← Phase 3: semantic / business rules (SEM-01..16)
│   ├── reporter.py        ← format and emit errors/warnings (text + JSON)
│   └── runner.py          ← orchestrate all phases; short-circuit on Phase 1 failure
├── validate_schema.py     ← CLI entrypoint
└── tests/
    ├── fixtures/
    │   └── valid_full.xml ← document exercising all sub-schemas (used by all three phases)
    ├── test_phase1.py     ←  8 tests
    ├── test_phase2.py     ← 25 tests (REF-01..07)
    └── test_phase3.py     ← 25 tests (SEM-01..16)
```

Tests for Phase 2 and Phase 3 build invalid XML programmatically via helper
functions rather than loading additional fixture files.

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
- `localMktTz` values are stripped before comparison (enum values in
  `atdl-timezones-1-1.xsd` contain trailing spaces)

### `reporter.py`
- `format_text(result: ValidationResult) -> str` — human-readable, one line per finding
- `format_json(result: ValidationResult) -> str` — machine-readable JSON array

### `runner.py`
- `validate(xml_path, schema_path, *, phases=(1,2,3)) -> ValidationResult`
- Short-circuits after Phase 1 if structural errors are present
- Allows callers to run a subset of phases (useful in unit tests)

---

## CLI (`validate_schema.py`)

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

**Exit codes:** `0` = valid, `1` = errors found, `2` = usage/file error.

---

## Implementation Status

| Step | Description | Status |
|------|-------------|--------|
| 1 | Create `schema_validator/` package | ✅ Done |
| 2 | `loader.py` — XML parsing and element indexing | ✅ Done |
| 3 | `phase1_xsd.py` — wrap lxml XSD validation | ✅ Done |
| 4 | `phase2_refs.py` — REF-01 through REF-07 | ✅ Done |
| 5 | `phase3_sem.py` — SEM-01 through SEM-16 | ✅ Done |
| 6 | `reporter.py` — text and JSON formatters | ✅ Done |
| 7 | `runner.py` — orchestrator with short-circuit logic | ✅ Done |
| 8 | `validate_schema.py` — CLI entrypoint | ✅ Done |
| 9 | Test fixture (`valid_full.xml`) | ✅ Done |
| 10 | Unit tests — `test_phase{1,2,3}.py` (58 tests total) | ✅ Done |

---

## Relationship to Existing Code

- `converter/validator.py` performs Phase 1 only and is used by the converter's
  `--validate` flag; `schema_validator/phase1_xsd.py` provides the same check
  as a standalone module
- Both tools co-exist and share the `schemas/` directory
- No new runtime dependencies — `lxml` was already required by the converter
