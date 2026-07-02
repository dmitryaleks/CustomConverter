/* edit-resolver.js — named val:Edit reuse (EditRef).
   FIXatdl allows <val:Edit id="..."> declared under Strategies or Strategy
   to be referenced via <val:EditRef id="..."/> from StateRules, StrategyEdits
   and nested Edits. This module owns the name table and defensive cloning;
   it is pure data-shape logic with no DOM dependency. */
(function (global) {
  "use strict";

  /* Prototype-chained lookup table: a Strategy context inherits the
     Strategies-level context, so strategy-local ids shadow global ones. */
  function createContext(parent) {
    return Object.create(parent || null);
  }

  function define(ctx, id, edit) {
    if (!ctx || id == null || id === "" || !edit) return;
    ctx[id] = edit;
  }

  function resolve(ctx, refId) {
    if (!ctx || refId == null) return null;
    return ctx[refId] || null;
  }

  /* Deep copy so every use site owns its subtree. The Set guards against
     cyclic structures (only possible through malformed input). */
  function cloneEdit(edit, seen) {
    if (!edit) return null;
    seen = seen || new Set();
    if (seen.has(edit)) {
      console.warn("AtdlEditResolver: cyclic Edit structure — reference dropped.");
      return null;
    }
    seen.add(edit);
    var copy = {
      field: edit.field,
      field2: edit.field2,
      value: edit.value,
      operator: edit.operator,
      logicOperator: edit.logicOperator,
      edits: []
    };
    (edit.edits || []).forEach(function (sub) {
      var c = cloneEdit(sub, seen);
      if (c) copy.edits.push(c);
    });
    seen.delete(edit);
    return copy;
  }

  global.AtdlEditResolver = {
    createContext: createContext,
    define: define,
    resolve: resolve,
    cloneEdit: cloneEdit
  };
})(window);
