/* atdl-parser.js — parse FIXatdl 1.1 XML into a JS model. */
(function (global) {
  "use strict";

  var NS_CORE = "http://www.fixprotocol.org/FIXatdl-1-1/Core";
  var NS_LAY  = "http://www.fixprotocol.org/FIXatdl-1-1/Layout";
  var NS_VAL  = "http://www.fixprotocol.org/FIXatdl-1-1/Validation";
  var NS_FLOW = "http://www.fixprotocol.org/FIXatdl-1-1/Flow";
  var NS_XSI  = "http://www.w3.org/2001/XMLSchema-instance";

  /* Strip namespace prefix from xsi:type values like "core:Int_t" or "lay:DropDownList_t". */
  function bareType(qname) {
    if (!qname) return null;
    var i = qname.indexOf(":");
    return i >= 0 ? qname.substring(i + 1) : qname;
  }

  function attr(el, name) {
    var v = el.getAttribute(name);
    return v === null ? null : v;
  }

  function attrBool(el, name, fallback) {
    var v = attr(el, name);
    if (v === null) return fallback;
    v = v.toLowerCase();
    return v === "true" || v === "1" || v === "y";
  }

  function childrenNS(el, ns, local) {
    var out = [];
    for (var i = 0; i < el.childNodes.length; i++) {
      var c = el.childNodes[i];
      if (c.nodeType !== 1) continue;
      if (c.namespaceURI === ns && c.localName === local) out.push(c);
    }
    return out;
  }

  function firstChildNS(el, ns, local) {
    var list = childrenNS(el, ns, local);
    return list.length ? list[0] : null;
  }

  function textOf(el) {
    return el ? (el.textContent || "").trim() : "";
  }

  /* HelpText_t preserves whitespace (xs:whiteSpace value="preserve"). */
  function textOfPreserve(el) {
    return el ? (el.textContent || "") : null;
  }

  /* ---------- ParameterT ---------- */
  function parseParameter(el) {
    var xsiType = el.getAttributeNS(NS_XSI, "type");
    var p = {
      name: attr(el, "name"),
      type: bareType(xsiType) || "String_t",
      fixTag: attr(el, "fixTag"),
      use: attr(el, "use") || "optional",
      mutableOnCxlRpl: attrBool(el, "mutableOnCxlRpl", true),
      precision: attr(el, "precision"),
      minValue: attr(el, "minValue"),
      maxValue: attr(el, "maxValue"),
      minLength: attr(el, "minLength"),
      maxLength: attr(el, "maxLength"),
      multiplyBy100: attrBool(el, "multiplyBy100", false),
      trueWireValue: attr(el, "trueWireValue") || "Y",
      falseWireValue: attr(el, "falseWireValue") || "N",
      constValue: attr(el, "constValue"),
      definedByFIX: attrBool(el, "definedByFIX", false),
      description: textOf(firstChildNS(el, NS_CORE, "Description")),
      enumPairs: []
    };
    childrenNS(el, NS_CORE, "EnumPair").forEach(function (ep) {
      p.enumPairs.push({
        enumID: attr(ep, "enumID"),
        wireValue: attr(ep, "wireValue"),
        description: textOf(firstChildNS(ep, NS_CORE, "Description"))
      });
    });
    return p;
  }

  /* ---------- Edit / EditRef (Validation) ---------- */
  function parseEdit(el, ctx) {
    if (!el) return null;
    var edit = {
      field: attr(el, "field"),
      field2: attr(el, "field2"),
      value: attr(el, "value"),
      operator: attr(el, "operator"),
      logicOperator: attr(el, "logicOperator"),
      edits: []
    };
    /* Children may mix nested <Edit> and <EditRef> in document order. */
    var ns = el.namespaceURI;
    for (var i = 0; i < el.childNodes.length; i++) {
      var c = el.childNodes[i];
      if (c.nodeType !== 1 || c.namespaceURI !== ns) continue;
      if (c.localName === "Edit") {
        edit.edits.push(parseEdit(c, ctx));
      } else if (c.localName === "EditRef") {
        var resolved = resolveEditRef(c, ctx);
        if (resolved) edit.edits.push(resolved);
      }
    }
    var id = attr(el, "id");
    if (id) AtdlEditResolver.define(ctx, id, edit);
    return edit;
  }

  function resolveEditRef(el, ctx) {
    var refId = attr(el, "id");
    var named = AtdlEditResolver.resolve(ctx, refId);
    if (!named) {
      console.warn("FIXatdl: EditRef id='" + refId + "' does not match any previously defined Edit — reference ignored.");
      return null;
    }
    return AtdlEditResolver.cloneEdit(named);
  }

  /* StateRule and StrategyEdit both wrap exactly one Edit or EditRef. */
  function parseConditionChild(el, ctx) {
    var editEl = firstChildNS(el, NS_VAL, "Edit");
    if (editEl) return parseEdit(editEl, ctx);
    var refEl = firstChildNS(el, NS_VAL, "EditRef");
    if (refEl) return resolveEditRef(refEl, ctx);
    return null;
  }

  /* ---------- StateRule (Flow) ---------- */
  function parseStateRule(el, ctx) {
    return {
      enabled: el.hasAttribute("enabled") ? attrBool(el, "enabled", true) : null,
      visible: el.hasAttribute("visible") ? attrBool(el, "visible", true) : null,
      value:   el.hasAttribute("value") ? attr(el, "value") : null,
      edit: parseConditionChild(el, ctx)
    };
  }

  /* ---------- StrategyEdit (Validation) ---------- */
  function parseStrategyEdit(el, ctx) {
    return {
      errorMessage: attr(el, "errorMessage") || "Strategy validation rule failed.",
      description: textOf(firstChildNS(el, NS_CORE, "Description")),
      edit: parseConditionChild(el, ctx)
    };
  }

  /* ---------- ListItem ---------- */
  function parseListItem(el, ctx) {
    var li = {
      enumID: attr(el, "enumID"),
      uiRep: attr(el, "uiRep") || attr(el, "enumID"),
      stateRules: []
    };
    childrenNS(el, NS_FLOW, "StateRule").forEach(function (sr) {
      li.stateRules.push(parseStateRule(sr, ctx));
    });
    return li;
  }

  /* ---------- Control ---------- */
  function parseControl(el, ctx) {
    var xsiType = el.getAttributeNS(NS_XSI, "type");
    var ctrl = {
      id: attr(el, "ID"),
      type: bareType(xsiType) || "TextField_t",
      parameterRef: attr(el, "parameterRef"),
      label: attr(el, "label"),
      tooltip: attr(el, "tooltip"),
      helpText: textOfPreserve(firstChildNS(el, NS_LAY, "HelpText")),
      initValue: attr(el, "initValue"),
      initValueMode: attr(el, "initValueMode"),
      initFixField: attr(el, "initFixField"),
      initPolicy: attr(el, "initPolicy"),
      increment: attr(el, "increment"),
      incrementPolicy: attr(el, "incrementPolicy"),
      innerIncrement: attr(el, "innerIncrement"),
      innerIncrementPolicy: attr(el, "innerIncrementPolicy"),
      outerIncrement: attr(el, "outerIncrement"),
      outerIncrementPolicy: attr(el, "outerIncrementPolicy"),
      minValue: attr(el, "minValue"),
      maxValue: attr(el, "maxValue"),
      checkedEnumRef: attr(el, "checkedEnumRef"),
      uncheckedEnumRef: attr(el, "uncheckedEnumRef"),
      radioGroup: attr(el, "radioGroup"),
      orientation: attr(el, "orientation"),
      listItems: [],
      stateRules: []
    };
    childrenNS(el, NS_LAY, "ListItem").forEach(function (li) {
      ctrl.listItems.push(parseListItem(li, ctx));
    });
    childrenNS(el, NS_FLOW, "StateRule").forEach(function (sr) {
      ctrl.stateRules.push(parseStateRule(sr, ctx));
    });
    return ctrl;
  }

  /* ---------- StrategyPanel (recursive) ---------- */
  function parseStrategyPanel(el, ctx) {
    var panel = {
      title: attr(el, "title"),
      orientation: (attr(el, "orientation") || "VERTICAL").toUpperCase(),
      collapsible: attrBool(el, "collapsible", false),
      collapsed: attrBool(el, "collapsed", false),
      border: attr(el, "border"),
      color: attr(el, "color"),
      controls: [],
      panels: []
    };
    childrenNS(el, NS_LAY, "Control").forEach(function (c) {
      panel.controls.push(parseControl(c, ctx));
    });
    childrenNS(el, NS_LAY, "StrategyPanel").forEach(function (sp) {
      panel.panels.push(parseStrategyPanel(sp, ctx));
    });
    return panel;
  }

  /* ---------- Strategy ---------- */
  function parseStrategy(el, strategiesAttrs, parentCtx) {
    var ctx = AtdlEditResolver.createContext(parentCtx);
    var strat = {
      name: attr(el, "name"),
      uiRep: attr(el, "uiRep") || attr(el, "name"),
      wireValue: attr(el, "wireValue") || attr(el, "name"),
      providerID: attr(el, "providerID") || strategiesAttrs.providerID || "",
      version: attr(el, "version") || "",
      fixMsgType: attr(el, "fixMsgType") || "D",
      strategyIdentifierTag: strategiesAttrs.strategyIdentifierTag || "847",
      parameters: [],
      panels: [],
      strategyEdits: []
    };
    childrenNS(el, NS_CORE, "Parameter").forEach(function (p) {
      strat.parameters.push(parseParameter(p));
    });
    /* Strategy-level named Edits come before the layout in the XSD content
       model, so a single pass registers them before any EditRef use. */
    childrenNS(el, NS_VAL, "Edit").forEach(function (e) {
      parseEdit(e, ctx);
    });
    var layout = firstChildNS(el, NS_LAY, "StrategyLayout");
    if (layout) {
      childrenNS(layout, NS_LAY, "StrategyPanel").forEach(function (sp) {
        strat.panels.push(parseStrategyPanel(sp, ctx));
      });
    }
    childrenNS(el, NS_VAL, "StrategyEdit").forEach(function (se) {
      strat.strategyEdits.push(parseStrategyEdit(se, ctx));
    });
    /* Synthesize a flat panel if no layout — render parameters in declaration order. */
    if (strat.panels.length === 0 && strat.parameters.length > 0) {
      strat.panels.push({
        title: null, orientation: "VERTICAL", collapsible: false, collapsed: false,
        border: null, color: null, panels: [],
        controls: strat.parameters.map(function (p) {
          return inferControlFromParameter(p);
        })
      });
    }
    /* Index parameters by name. */
    strat.parameterMap = {};
    strat.parameters.forEach(function (p) { strat.parameterMap[p.name] = p; });
    return strat;
  }

  /* When a Strategy lacks a StrategyLayout, infer a sensible Control type per parameter. */
  function inferControlFromParameter(p) {
    var ctrl = {
      id: p.name + "_ctrl",
      parameterRef: p.name,
      label: p.name,
      tooltip: null, helpText: null,
      initValue: null, initValueMode: null, initFixField: null, initPolicy: null,
      increment: null, incrementPolicy: null,
      innerIncrement: null, innerIncrementPolicy: null,
      outerIncrement: null, outerIncrementPolicy: null,
      minValue: null, maxValue: null,
      checkedEnumRef: null, uncheckedEnumRef: null,
      radioGroup: null, orientation: null,
      listItems: [], stateRules: []
    };
    if (p.enumPairs.length > 0 && p.type !== "Boolean_t") {
      ctrl.type = "DropDownList_t";
      ctrl.listItems = p.enumPairs.map(function (e) {
        return { enumID: e.enumID, uiRep: e.enumID };
      });
    } else if (p.type === "Boolean_t") {
      ctrl.type = "CheckBox_t";
    } else if (isNumericType(p.type)) {
      ctrl.type = "SingleSpinner_t";
    } else if (isClockType(p.type)) {
      ctrl.type = "Clock_t";
    } else {
      ctrl.type = "TextField_t";
    }
    return ctrl;
  }

  function isNumericType(t) {
    return ["Int_t","Length_t","NumInGroup_t","SeqNum_t","TagNum_t",
            "Float_t","Qty_t","Price_t","PriceOffset_t","Amt_t","Numeric_t",
            "Percentage_t"].indexOf(t) >= 0;
  }

  function isClockType(t) {
    return ["UTCTimeOnly_t","UTCTimestamp_t","UTCDate_t","LocalMktDate_t",
            "MonthYear_t","LocalMktTime_t"].indexOf(t) >= 0;
  }

  /* ---------- Top level ---------- */
  function parseATDL(xmlText) {
    var doc = new DOMParser().parseFromString(xmlText, "application/xml");
    var perr = doc.getElementsByTagName("parsererror")[0];
    if (perr) {
      var msg = perr.textContent || "Invalid XML";
      throw new Error("XML parse error: " + msg.replace(/\s+/g, " ").trim());
    }
    var root = doc.documentElement;
    if (!root || root.localName !== "Strategies" || root.namespaceURI !== NS_CORE) {
      throw new Error("Root element must be <Strategies> in namespace " + NS_CORE +
                      " — got <" + (root && root.localName) + "> in " + (root && root.namespaceURI));
    }
    var stratsAttrs = {
      strategyIdentifierTag: attr(root, "strategyIdentifierTag"),
      providerID: attr(root, "providerID")
    };
    /* Strategies-level named Edits are shared by every Strategy. */
    var rootCtx = AtdlEditResolver.createContext(null);
    childrenNS(root, NS_VAL, "Edit").forEach(function (e) {
      parseEdit(e, rootCtx);
    });
    var strategies = [];
    childrenNS(root, NS_CORE, "Strategy").forEach(function (s) {
      strategies.push(parseStrategy(s, stratsAttrs, rootCtx));
    });
    return {
      strategyIdentifierTag: stratsAttrs.strategyIdentifierTag || "847",
      strategies: strategies
    };
  }

  global.AtdlParser = {
    parse: parseATDL,
    NS_CORE: NS_CORE, NS_LAY: NS_LAY, NS_VAL: NS_VAL, NS_FLOW: NS_FLOW, NS_XSI: NS_XSI,
    isNumericType: isNumericType,
    isClockType: isClockType,
    bareType: bareType
  };
})(window);
