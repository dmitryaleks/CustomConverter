/* Node tests for the pure half of state-rules.js: evalEdit (operators and
   logic operators) and computeOutcomes (XNOR truth table, value-on-trigger,
   {NULL} passthrough, per-ListItem outcomes, cascade fixture). */
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");

global.window = global;
require("../../state-rules.js");
const { evalEdit, computeOutcomes } = global.AtdlStateRules;

function leaf(field, operator, value) {
  return { field, operator, value, edits: [] };
}

test("evalEdit: comparison operators", () => {
  assert.equal(evalEdit(leaf("a", "EQ", "x"), { a: "x" }), true);
  assert.equal(evalEdit(leaf("a", "EQ", "x"), { a: "y" }), false);
  assert.equal(evalEdit(leaf("a", "NE", "x"), { a: "y" }), true);
  assert.equal(evalEdit(leaf("a", "GT", "5"), { a: "7" }), true);
  assert.equal(evalEdit(leaf("a", "GT", "5"), { a: "5" }), false);
  assert.equal(evalEdit(leaf("a", "GE", "5"), { a: "5" }), true);
  assert.equal(evalEdit(leaf("a", "LT", "5"), { a: "4.5" }), true);
  assert.equal(evalEdit(leaf("a", "LE", "5"), { a: "5" }), true);
});

test("evalEdit: EX/NX treat null (uninitialized) and empty as absent", () => {
  assert.equal(evalEdit(leaf("a", "EX"), { a: "1" }), true);
  assert.equal(evalEdit(leaf("a", "EX"), { a: null }), false);
  assert.equal(evalEdit(leaf("a", "EX"), { a: "" }), false);
  assert.equal(evalEdit(leaf("a", "EX"), {}), false);
  assert.equal(evalEdit(leaf("a", "NX"), { a: null }), true);
  assert.equal(evalEdit(leaf("a", "NX"), { a: "1" }), false);
});

test("evalEdit: field2 compares two controls", () => {
  const edit = { field: "a", field2: "b", operator: "GT", edits: [] };
  assert.equal(evalEdit(edit, { a: "9", b: "3" }), true);
  assert.equal(evalEdit(edit, { a: "2", b: "3" }), false);
});

test("evalEdit: logic operators over nested edits", () => {
  const t = leaf("a", "EQ", "1");
  const f = leaf("a", "EQ", "2");
  const values = { a: "1" };
  assert.equal(evalEdit({ logicOperator: "AND", edits: [t, t] }, values), true);
  assert.equal(evalEdit({ logicOperator: "AND", edits: [t, f] }, values), false);
  assert.equal(evalEdit({ logicOperator: "OR", edits: [f, t] }, values), true);
  assert.equal(evalEdit({ logicOperator: "OR", edits: [f, f] }, values), false);
  assert.equal(evalEdit({ logicOperator: "XOR", edits: [t, f] }, values), true);
  assert.equal(evalEdit({ logicOperator: "XOR", edits: [t, t] }, values), false);
  assert.equal(evalEdit({ logicOperator: "NOT", edits: [f] }, values), true);
  assert.equal(evalEdit({ logicOperator: "NOT", edits: [t] }, values), false);
});

test("evalEdit: missing edit (unresolved EditRef) is lenient-true", () => {
  assert.equal(evalEdit(null, {}), true);
});

function ctrl(id, stateRules, listItems) {
  return { id, stateRules: stateRules || [], listItems: listItems || [] };
}
function rule(props) {
  return Object.assign({ enabled: null, visible: null, value: null, edit: null }, props);
}

test("computeOutcomes: visible/enabled follow the XNOR truth table", () => {
  const c = ctrl("f", [rule({ visible: true, enabled: false, edit: leaf("a", "EQ", "on") })]);
  let out = computeOutcomes([c], { a: "on" }).outcomes.f;
  assert.equal(out.visible, true, "condition true, visible=true → show");
  assert.equal(out.enabled, false, "condition true, enabled=false → disable");
  out = computeOutcomes([c], { a: "off" }).outcomes.f;
  assert.equal(out.visible, false, "condition false, visible=true → hide");
  assert.equal(out.enabled, true, "condition false, enabled=false → enable");
});

test("computeOutcomes: value applies only while the condition is true", () => {
  const c = ctrl("f", [rule({ value: "25", edit: leaf("a", "EQ", "HIGH") })]);
  assert.equal(computeOutcomes([c], { a: "HIGH" }).outcomes.f.setValue, "25");
  assert.equal(computeOutcomes([c], { a: "LOW" }).outcomes.f.setValue, undefined);
});

test("computeOutcomes: {NULL} token passes through as a setValue", () => {
  const c = ctrl("f", [rule({ value: "{NULL}", edit: leaf("a", "EQ", "false") })]);
  assert.equal(computeOutcomes([c], { a: "false" }).outcomes.f.setValue, "{NULL}");
});

test("computeOutcomes: later rules override earlier ones per aspect", () => {
  const c = ctrl("f", [
    rule({ visible: true, edit: leaf("a", "EX") }),
    rule({ visible: false, edit: leaf("b", "EQ", "1") })
  ]);
  const out = computeOutcomes([c], { a: "x", b: "1" }).outcomes.f;
  assert.equal(out.visible, false, "second rule wins");
});

test("computeOutcomes: per-ListItem rules land in listOutcomes", () => {
  const li = { enumID: "LAST", uiRep: "Last", stateRules: [rule({ visible: true, edit: leaf("style", "NE", "AGG") })] };
  const c = ctrl("peg", [], [li]);
  let res = computeOutcomes([c], { style: "AGG" });
  assert.equal(res.listOutcomes.peg.LAST.visible, false);
  res = computeOutcomes([c], { style: "PASS" });
  assert.equal(res.listOutcomes.peg.LAST.visible, true);
});

test("computeOutcomes: a ListItem value rule sets the parent control's value", () => {
  const li = { enumID: "X", uiRep: "X", stateRules: [rule({ value: "X", edit: leaf("a", "EQ", "1") })] };
  const c = ctrl("peg", [], [li]);
  const res = computeOutcomes([c], { a: "1" });
  assert.equal(res.outcomes.peg.setValue, "X");
  assert.equal(res.listOutcomes.peg.X.setValue, undefined, "not duplicated on the item");
});

test("computeOutcomes: two-hop cascade converges across passes", () => {
  /* Urgency HIGH forces MaxPct to 25; MaxPct >= 25 reveals RiskAck.
     Simulates the fixpoint loop: pass 1 computes the value-set, pass 2
     (with the value applied) flips the dependent visibility. */
  const maxPct = ctrl("maxPct", [rule({ value: "25", edit: leaf("urgency", "EQ", "HIGH") })]);
  const riskAck = ctrl("riskAck", [rule({ visible: true, edit: leaf("maxPct", "GE", "25") })]);
  const all = [maxPct, riskAck];

  const pass1 = computeOutcomes(all, { urgency: "HIGH", maxPct: "10", riskAck: null });
  assert.equal(pass1.outcomes.maxPct.setValue, "25");
  assert.equal(pass1.outcomes.riskAck.visible, false, "not yet visible on pass 1");

  const pass2 = computeOutcomes(all, { urgency: "HIGH", maxPct: "25", riskAck: null });
  assert.equal(pass2.outcomes.riskAck.visible, true, "visible once the set value lands");
});
