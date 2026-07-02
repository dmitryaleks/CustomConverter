# FIXatdl 1.1 Browser Renderer (`alternativeRenderer`)

A dependency-free, browser-only renderer for **FIXatdl 1.1** strategy documents.
Drop a FIXatdl XML file onto the page and each strategy renders as an interactive
order-entry form with live conditional behavior (flow:StateRule), multi-phase
validation, and a raw FIX message preview.

Everything runs locally in the browser — plain JavaScript attached to `window`
via IIFEs, no frameworks, no build step, no network calls.

## Running

Serve the folder over HTTP so the bundled XSDs can be fetched (the XSD phase is
skipped with a visible notice when opened from `file://`):

```bash
cd alternativeRenderer
python -m http.server 8000
# open http://localhost:8000
```

Then drop any file from `sample/` onto the page.

## File map

| File | Responsibility |
|---|---|
| `index.html` / `styles.css` | Page shell, tabs, styling |
| `atdl-parser.js` | FIXatdl XML → JS model (strategies, parameters, controls, panels, state rules, strategy edits) |
| `edit-resolver.js` | Named `val:Edit` table + `EditRef` resolution (Strategies→Strategy scoping, deep clone, cycle guard) |
| `widgets.js` | Control factory (one builder per `Control_t` subtype) + value read/write in both value spaces |
| `state-rules.js` | StateRule engine: Edit evaluation, fixpoint application of enabled/visible/value effects |
| `fix-builder.js` | FIX 4.2 message assembly (header, body-length, checksum) |
| `app.js` | Orchestration: file intake, tabs, panel/control rendering, submission, FIX load/preview |
| `xsd-loader.js` / `xsd-validator.js` / `atdl-validator.js` | Multi-phase validation (XSD, XML shape, referential, semantic) shown in the Source & Validation tab |
| `schemas/` | Official FIXatdl 1.1 XSDs |
| `sample/` | Example strategy documents |
| `tools/test/` | Node unit tests for the pure (DOM-free) logic |

## Conditional rendering (flow:StateRule)

The engine implements the FIXatdl 1.1 flow semantics:

- **Condition grammar** — full `val:Edit` support: leaf operators `EQ NE GT GE
  LT LE EX NX`, logic operators `AND OR XOR NOT` over nested `Edit`/`EditRef`
  children, and `field2` (control-vs-control) comparisons.
- **Named Edits / EditRef** — `<val:Edit id="...">` declared under `Strategies`
  or `Strategy` can be referenced by `<val:EditRef id="..."/>` from StateRules,
  StrategyEdits, and nested Edits. Strategy-level names shadow Strategies-level
  ones. Unresolved references warn on the console and fall back to
  always-true (lenient).
- **Value spaces** — per the spec, an Edit inside a StateRule references
  **Control IDs** and compares **control values**: the `enumID` of the selected
  ListItem for list controls, `"true"`/`"false"` for CheckBox/RadioButton, raw
  display text otherwise. Wire values (`EnumPair@wireValue`) are used only when
  building the FIX message. The code mirrors this split:
  `AtdlWidgets.readUiValue`/`setUiValue` (UI space) vs `readValue`/`setValue`
  (wire space).
- **Effects** — `enabled` and `visible` follow the XSD truth table (XNOR with
  the condition result); `value` applies only while the condition is true.
  The special token **`{NULL}`** clears a control to an *uninitialized* state
  (empty text/number, blank placeholder option, nothing checked; sliders track
  an explicit flag). CheckBox/RadioButton are "always initialized" per the
  spec, so `{NULL}` on them is a warned no-op.
- **Cascading** — rules are applied to a fixpoint (capped at 25 passes): a rule
  that sets control B's value re-triggers rules that depend on B. A console
  warning fires if contradictory rules fail to converge.
- **Per-ListItem StateRules** — individual `<lay:ListItem>` entries can be
  hidden/disabled; if the currently selected entry becomes blocked, its
  selection is cleared (feeding back into the fixpoint).
- **StrategyEdit** — `<val:StrategyEdit>` rules run at submit time in
  **parameter/wireValue space**. A failing rule blocks the FIX preview and
  shows its `errorMessage` above the form actions.

### FIX output rules

When building the FIX message, a parameter's tag is **omitted** if its control is:

1. hidden by a StateRule,
2. disabled by a StateRule (atdl4j behavior; controlled by the
   `EXCLUDE_DISABLED_FROM_WIRE` constant in `app.js` — the spec is explicit
   only about hidden/uninitialized), or
3. uninitialized (empty, or cleared via `{NULL}`).

Hidden/disabled controls are also skipped by required/range validation, so a
required-but-hidden field does not block submission. Parameters with a
`constValue` and no control are still emitted.

## Control rendering fidelity

All `Control_t` subtypes render: TextField, SingleSpinner, DoubleSpinner
(innerIncrement → arrow step, outerIncrement → ± nudge buttons), DropDownList,
EditableDropDownList (datalist; typed text matched by `uiRep`), Single/Multi
SelectList, CheckBox and RadioButton (`checkedEnumRef`/`uncheckedEnumRef`
resolved through EnumPairs to wire values; RadioButtons sharing a `radioGroup`
are natively mutually exclusive), CheckBoxList, RadioButtonList, Slider
(discrete when ListItems are present, walking enumIDs), Clock (HTML input per
FIX type; `initValueMode="1"` swaps in the current time when `initValue` has
past), Label (`initValue` takes precedence over `label`), HiddenField, TextArea.

Panels honor `title`, `orientation`, `collapsible`/`collapsed`, `color`
(`"R,G,B"` background), and the `border` tri-state (`Line` always,
`None` never, unset → only when titled). Control `tooltip` renders as a hover
title; `HelpText` as an expandable note.

## Demo / manual QA

`sample/STATE_RULES_DEMO.xml` exercises every conditional feature; the header
comment inside the file is a 10-point walkthrough (checkbox-driven
enable/hide, `{NULL}` tag omission, per-ListItem hiding, required-but-hidden
submission, a two-hop value cascade, radioGroup exclusivity, DoubleSpinner
increments, Clock initValueMode, StrategyEdit blocking). Each StateRule carries
a `<Description>` stating its expected behavior.

## Tests

Pure logic (Edit evaluation, outcome computation, EditRef resolution) is unit
tested in Node with zero dependencies:

```bash
node --test "alternativeRenderer/tools/test/*.test.js"
```

Note: pass the glob, not a bare directory with a trailing slash (fails on
Windows). DOM behavior (widgets, panels, submission) is verified in the
browser against the samples.

## Known limitations

- `FIX_`-prefixed standard-field references (`initFixField` /
  `initPolicy="UseFixField"`, and `Edit@field` values like `FIX_OrderQty`
  inside StrategyEdits) are not evaluated — there is no FIX field-name→tag
  dictionary. They log a console note; StrategyEdits using them are treated as
  passing.
- `incrementPolicy` / `innerIncrementPolicy` / `outerIncrementPolicy` values
  `Tick`/`LotSize` cannot be honored without market data; the literal
  increments are used and the policy is noted in the control's tooltip.
- `Clock_t@localMktTz` timezone math is not applied; `initValueMode`
  comparisons use browser-local time.
- `sample/VWAP.xml` carries a pre-existing schema violation (an invalid
  `const="true"` attribute) that the Source & Validation tab reports by design.
