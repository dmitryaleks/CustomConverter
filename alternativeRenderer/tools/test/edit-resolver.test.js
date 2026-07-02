/* Node tests for edit-resolver.js (zero dependencies, node:test).
   The source files are window-attaching IIFEs, so alias window → global. */
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");

global.window = global;
require("../../edit-resolver.js");
const R = global.AtdlEditResolver;

test("define + resolve round-trips a named edit", () => {
  const ctx = R.createContext(null);
  const edit = { field: "a", operator: "EX", edits: [] };
  R.define(ctx, "hasA", edit);
  assert.equal(R.resolve(ctx, "hasA"), edit);
});

test("resolve returns null for unknown ids and null contexts", () => {
  const ctx = R.createContext(null);
  assert.equal(R.resolve(ctx, "nope"), null);
  assert.equal(R.resolve(null, "nope"), null);
});

test("define ignores null/empty ids and null edits", () => {
  const ctx = R.createContext(null);
  R.define(ctx, null, { edits: [] });
  R.define(ctx, "", { edits: [] });
  R.define(ctx, "x", null);
  assert.equal(R.resolve(ctx, ""), null);
  assert.equal(R.resolve(ctx, "x"), null);
});

test("child context inherits and shadows parent definitions", () => {
  const root = R.createContext(null);
  const global1 = { field: "g", operator: "EX", edits: [] };
  R.define(root, "shared", global1);
  const child = R.createContext(root);
  assert.equal(R.resolve(child, "shared"), global1, "inherits parent id");

  const local = { field: "l", operator: "NX", edits: [] };
  R.define(child, "shared", local);
  assert.equal(R.resolve(child, "shared"), local, "child shadows parent");
  assert.equal(R.resolve(root, "shared"), global1, "parent unaffected");
});

test("cloneEdit deep-copies so use sites are independent", () => {
  const inner = { field: "b", operator: "EQ", value: "1", edits: [] };
  const edit = { logicOperator: "AND", edits: [inner] };
  const copy = R.cloneEdit(edit);
  assert.notEqual(copy, edit);
  assert.notEqual(copy.edits[0], inner);
  assert.deepEqual(copy.edits[0].field, "b");
  copy.edits[0].value = "999";
  assert.equal(inner.value, "1", "mutating the clone leaves the original intact");
});

test("cloneEdit drops cyclic references instead of recursing forever", () => {
  const edit = { logicOperator: "AND", edits: [] };
  edit.edits.push(edit); /* malformed: refers to itself */
  const copy = R.cloneEdit(edit);
  assert.ok(copy);
  assert.equal(copy.edits.length, 0, "cyclic child dropped");
});
