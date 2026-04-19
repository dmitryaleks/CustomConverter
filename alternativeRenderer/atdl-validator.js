/* atdl-validator.js — multi-phase FIXatdl 1.1 validator (subset).
   Mirrors the project's Python schema_validator package but runs in the
   browser against an already-parsed XML document.

   Returns { summary, errors, warnings } where each issue has:
     { phase, ruleId, message, element, line }
*/
(function (global) {
  "use strict";

  var NS_CORE = "http://www.fixprotocol.org/ATDL-1-1/Core";
  var NS_LAY  = "http://www.fixprotocol.org/ATDL-1-1/Layout";
  var NS_FLOW = "http://www.fixprotocol.org/ATDL-1-1/Flow";
  var NS_VAL  = "http://www.fixprotocol.org/ATDL-1-1/Validation";
  var NS_XSI  = "http://www.w3.org/2001/XMLSchema-instance";

  /* Allowed Parameter xsi:type local names (from atdl-core-1-1.xsd). */
  var VALID_PARAM_TYPES = [
    "Amt_t","Boolean_t","Char_t","Country_t","Currency_t","Data_t","Exchange_t",
    "Float_t","Int_t","Language_t","Length_t","LocalMktDate_t","LocalMktTime_t",
    "MonthYear_t","MultipleCharValue_t","MultipleStringValue_t","NumInGroup_t",
    "Numeric_t","Percentage_t","Price_t","PriceOffset_t","Qty_t","SeqNum_t",
    "String_t","TagNum_t","Tenor_t","UTCDate_t","UTCDateOnly_t","UTCTimeOnly_t",
    "UTCTimeStamp_t","XMLData_t"
  ];

  /* Allowed Control xsi:type local names (from atdl-layout-1-1.xsd). */
  var VALID_CONTROL_TYPES = [
    "CheckBox_t","CheckBoxList_t","Clock_t","DoubleSpinner_t","DropDownList_t",
    "EditableDropDownList_t","HiddenField_t","Label_t","MultiSelectList_t",
    "RadioButton_t","RadioButtonList_t","SingleSelectList_t","SingleSpinner_t",
    "Slider_t","TextField_t"
  ];

  var LIST_CONTROL_TYPES = {
    DropDownList_t:1, EditableDropDownList_t:1, RadioButtonList_t:1,
    CheckBoxList_t:1, SingleSelectList_t:1, MultiSelectList_t:1
  };

  var NUMERIC_TYPES = {
    Int_t:1, Length_t:1, NumInGroup_t:1, SeqNum_t:1, TagNum_t:1,
    Float_t:1, Qty_t:1, Price_t:1, PriceOffset_t:1, Amt_t:1, Numeric_t:1,
    Percentage_t:1
  };

  function bareType(qname) {
    if (!qname) return null;
    var i = qname.indexOf(":");
    return i >= 0 ? qname.substring(i + 1) : qname;
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

  function descendantsNS(el, ns, local) {
    var out = [];
    walk(el);
    function walk(n) {
      for (var i = 0; i < n.childNodes.length; i++) {
        var c = n.childNodes[i];
        if (c.nodeType !== 1) continue;
        if (c.namespaceURI === ns && c.localName === local) out.push(c);
        walk(c);
      }
    }
    return out;
  }

  function lineOf(el) {
    /* DOMParser doesn't expose source line numbers. Best-effort: return
       a logical address using the element path. */
    var parts = [];
    var n = el;
    while (n && n.nodeType === 1) {
      var nm = n.localName + (n.getAttribute && n.getAttribute("name") ? "[@name='" + n.getAttribute("name") + "']" : "");
      parts.unshift(nm);
      n = n.parentNode;
    }
    return parts.join("/");
  }

  /* Accepts either a string path (e.g. "Strategies"), a DOM Element, or null.
     For an Element, derives both the structural path and the source line
     number recorded by assignLines() during validate(). */
  function makeIssue(phase, ruleId, message, target) {
    var element = null, line = null;
    if (target == null) {
      /* nothing */
    } else if (typeof target === "string") {
      element = target;
    } else if (target.nodeType === 1) {
      element = lineOf(target);
      line = target.__atdlLine || null;
    }
    return { phase: phase, ruleId: ruleId, message: message, element: element, line: line };
  }

  /* Scan raw XML to record the source line of each opening tag in document
     order. DOMParser does not expose source positions; this rebuilds them
     from text by tracking newline counts and skipping comments, CDATA, and
     processing instructions. */
  function buildLineMap(raw) {
    var lines = [];
    var line = 1;
    var i = 0, n = raw.length;
    while (i < n) {
      var c = raw.charAt(i);
      if (c === "\n") { line++; i++; continue; }
      if (c === "<") {
        var e;
        if (raw.substr(i, 4) === "<!--") {
          e = raw.indexOf("-->", i + 4);
          if (e < 0) break;
          for (var k = i; k < e + 3; k++) if (raw.charAt(k) === "\n") line++;
          i = e + 3; continue;
        }
        if (raw.substr(i, 9) === "<![CDATA[") {
          e = raw.indexOf("]]>", i + 9);
          if (e < 0) break;
          for (var k2 = i; k2 < e + 3; k2++) if (raw.charAt(k2) === "\n") line++;
          i = e + 3; continue;
        }
        var nx = raw.charAt(i + 1);
        if (nx === "?" || nx === "!") {
          e = raw.indexOf(">", i + 2);
          if (e < 0) break;
          for (var k3 = i; k3 < e + 1; k3++) if (raw.charAt(k3) === "\n") line++;
          i = e + 1; continue;
        }
        if (nx === "/") {
          e = raw.indexOf(">", i + 2);
          if (e < 0) break;
          for (var k4 = i; k4 < e + 1; k4++) if (raw.charAt(k4) === "\n") line++;
          i = e + 1; continue;
        }
        /* Opening (or empty-element) tag — record the start line. */
        lines.push(line);
        e = raw.indexOf(">", i + 1);
        if (e < 0) break;
        for (var k5 = i; k5 < e + 1; k5++) if (raw.charAt(k5) === "\n") line++;
        i = e + 1; continue;
      }
      i++;
    }
    return lines;
  }

  function assignLines(doc, raw) {
    var lineList = buildLineMap(raw);
    var idx = 0;
    (function walk(node) {
      if (!node || node.nodeType !== 1) return;
      if (idx < lineList.length) node.__atdlLine = lineList[idx++];
      for (var i = 0; i < node.childNodes.length; i++) walk(node.childNodes[i]);
    })(doc.documentElement);
  }

  /* XSD-declared name pattern (Strategy/@name, Parameter/@name, EnumPair/@enumID).
     Schema literal: [A-Za-z][A-za-z0-9_]{0,255} — note the typo "A-za-z" in the
     XSD itself; we match it byte-for-byte so JS results agree with lxml/IDE. */
  var NAME_PATTERN = /^[A-Za-z][A-za-z0-9_]{0,255}$/;

  /* Boolean lexical space per XSD ("true"|"false"|"1"|"0"). */
  function isXsdBoolean(v) { return v === "true" || v === "false" || v === "1" || v === "0"; }
  function isXsdNonNegInt(v) { return /^\d+$/.test(v); }
  function isXsdPositiveInt(v) { return /^[1-9]\d*$/.test(v); }
  function isXsdInt(v) { return /^-?\d+$/.test(v); }
  function isXsdDecimal(v) { return /^-?\d+(\.\d+)?$/.test(v) || /^-?\.\d+$/.test(v); }

  /* ---------- Phase 1: Structure / schema-shape ---------- */
  function phase1(doc, raw) {
    var errors = [];
    var root = doc.documentElement;

    if (!root) { errors.push(makeIssue(1, "P1-01", "Document has no root element.")); return errors; }
    if (root.localName !== "Strategies" || root.namespaceURI !== NS_CORE) {
      errors.push(makeIssue(1, "P1-02",
        "Root element must be {" + NS_CORE + "}Strategies — got <" +
        (root.namespaceURI ? "{" + root.namespaceURI + "}" : "") + root.localName + ">.",
        root.localName));
      return errors;
    }
    var sit = root.getAttribute("strategyIdentifierTag");
    if (sit === null || sit === "") {
      errors.push(makeIssue(1, "P1-03", "Strategies/@strategyIdentifierTag is required.", "Strategies"));
    } else if (!isXsdPositiveInt(sit)) {
      errors.push(makeIssue(1, "P1-04", "Strategies/@strategyIdentifierTag must be a positive integer (got '" + sit + "').", "Strategies"));
    }

    childrenNS(root, NS_CORE, "Strategy").forEach(function (s) {
      var sname = s.getAttribute("name");
      if (!sname) {
        errors.push(makeIssue(1, "P1-05a", "Strategy/@name is required.", "Strategy"));
      } else if (!NAME_PATTERN.test(sname)) {
        errors.push(makeIssue(1, "P1-05b",
          "Strategy/@name '" + sname + "' violates XSD pattern [A-Za-z][A-za-z0-9_]{0,255} (only letters, digits and underscore; must start with a letter).",
          s));
      }
      if (s.getAttribute("wireValue") === null || s.getAttribute("wireValue") === "") {
        errors.push(makeIssue(1, "P1-05c", "Strategy '" + (sname || "?") + "': @wireValue is required.", s));
      }
      if (s.getAttribute("version") === null || s.getAttribute("version") === "") {
        errors.push(makeIssue(1, "P1-05d", "Strategy '" + (sname || "?") + "': @version is required.", s));
      }
      ["mutableOnCxlRpl","revertOnCxlRpl"].forEach(function (a) {
        var v = s.getAttribute(a);
        if (v != null && v !== "" && !isXsdBoolean(v)) {
          errors.push(makeIssue(1, "P1-05e", "Strategy '" + (sname || "?") + "': @" + a + " must be xsd:boolean (got '" + v + "').", s));
        }
      });

      childrenNS(s, NS_CORE, "Parameter").forEach(function (p) {
        var name = p.getAttribute("name");
        if (!name) {
          errors.push(makeIssue(1, "P1-06a", "Parameter/@name is required.", p));
        } else if (!NAME_PATTERN.test(name)) {
          errors.push(makeIssue(1, "P1-06b",
            "Parameter/@name '" + name + "' violates XSD pattern [A-Za-z][A-za-z0-9_]{0,255}.",
            p));
        }
        var xsi = p.getAttributeNS(NS_XSI, "type");
        if (!xsi) {
          errors.push(makeIssue(1, "P1-07", "Parameter '" + (name || "?") + "' missing xsi:type — Parameter_t is abstract.", p));
        } else {
          var bt = bareType(xsi);
          if (VALID_PARAM_TYPES.indexOf(bt) < 0) {
            errors.push(makeIssue(1, "P1-08",
              "Parameter '" + (name || "?") + "' has unknown xsi:type '" + xsi + "'. Allowed local names: " + VALID_PARAM_TYPES.join(", "),
              p));
          }
        }
        var ft = p.getAttribute("fixTag");
        if (ft && !isXsdPositiveInt(ft)) {
          errors.push(makeIssue(1, "P1-09", "Parameter '" + (name || "?") + "' fixTag '" + ft + "' must be a positive integer.", p));
        }
        ["const","mutableOnCxlRpl","revertOnCxlRpl","definedByFIX","multiplyBy100"].forEach(function (a) {
          var v = p.getAttribute(a);
          if (v != null && v !== "" && !isXsdBoolean(v)) {
            errors.push(makeIssue(1, "P1-09b", "Parameter '" + (name || "?") + "': @" + a + " must be xsd:boolean (got '" + v + "').", p));
          }
        });
        var u = p.getAttribute("use");
        if (u != null && u !== "" && ["required","optional","conditional"].indexOf(u) < 0) {
          errors.push(makeIssue(1, "P1-09c", "Parameter '" + (name || "?") + "': @use must be required|optional|conditional (got '" + u + "').", p));
        }
        ["minLength","maxLength","precision"].forEach(function (a) {
          var v = p.getAttribute(a);
          if (v != null && v !== "" && !isXsdNonNegInt(v)) {
            errors.push(makeIssue(1, "P1-09d", "Parameter '" + (name || "?") + "': @" + a + " must be a non-negative integer (got '" + v + "').", p));
          }
        });
        ["minValue","maxValue"].forEach(function (a) {
          var v = p.getAttribute(a);
          if (v != null && v !== "" && !isXsdDecimal(v)) {
            errors.push(makeIssue(1, "P1-09e", "Parameter '" + (name || "?") + "': @" + a + " must be a decimal (got '" + v + "').", p));
          }
        });

        childrenNS(p, NS_CORE, "EnumPair").forEach(function (ep) {
          var eid = ep.getAttribute("enumID");
          if (eid === null || eid === "") {
            errors.push(makeIssue(1, "P1-13a", "Parameter '" + (name || "?") + "': EnumPair/@enumID is required.", ep));
          } else if (!NAME_PATTERN.test(eid)) {
            errors.push(makeIssue(1, "P1-13b",
              "Parameter '" + (name || "?") + "': EnumPair/@enumID '" + eid + "' violates XSD pattern [A-Za-z][A-za-z0-9_]{0,255}.",
              ep));
          }
          if (ep.getAttribute("wireValue") === null) {
            errors.push(makeIssue(1, "P1-13c", "Parameter '" + (name || "?") + "': EnumPair/@wireValue is required.", ep));
          }
        });
      });

      var layout = childrenNS(s, NS_LAY, "StrategyLayout")[0];
      if (layout) {
        descendantsNS(layout, NS_LAY, "Control").forEach(function (c) {
          var cid = c.getAttribute("ID");
          if (!cid) {
            errors.push(makeIssue(1, "P1-10", "Control/@ID is required.", c));
          }
          var xsi = c.getAttributeNS(NS_XSI, "type");
          if (!xsi) {
            errors.push(makeIssue(1, "P1-11", "Control '" + (cid || "?") + "' missing xsi:type.", c));
          } else {
            var bt = bareType(xsi);
            if (VALID_CONTROL_TYPES.indexOf(bt) < 0) {
              errors.push(makeIssue(1, "P1-12",
                "Control '" + (cid || "?") + "' has unknown xsi:type '" + xsi + "'. Allowed: " + VALID_CONTROL_TYPES.join(", "),
                c));
            }
          }
          var inc = c.getAttribute("increment");
          if (inc != null && inc !== "" && !isXsdDecimal(inc)) {
            errors.push(makeIssue(1, "P1-12b", "Control '" + (cid || "?") + "': @increment must be a decimal (got '" + inc + "').", c));
          }
        });
      }
    });

    return errors;
  }

  /* ---------- Phase 2: Referential integrity ---------- */
  function phase2(doc) {
    var errors = [];
    var root = doc.documentElement;
    if (!root || root.localName !== "Strategies" || root.namespaceURI !== NS_CORE) return errors;

    childrenNS(root, NS_CORE, "Strategy").forEach(function (s) {
      var sname = s.getAttribute("name") || "?";
      var paramNames = {}; /* name → element */
      var paramEnumIds = {}; /* paramName → set */

      childrenNS(s, NS_CORE, "Parameter").forEach(function (p) {
        var n = p.getAttribute("name");
        if (n) {
          paramNames[n] = p;
          var ids = {};
          childrenNS(p, NS_CORE, "EnumPair").forEach(function (ep) {
            var id = ep.getAttribute("enumID");
            if (id) ids[id] = true;
          });
          paramEnumIds[n] = ids;
        }
      });

      var seenRef = {};
      var layout = childrenNS(s, NS_LAY, "StrategyLayout")[0];
      var ctrls = layout ? descendantsNS(layout, NS_LAY, "Control") : [];

      ctrls.forEach(function (c) {
        var ref = c.getAttribute("parameterRef");
        var ctrlId = c.getAttribute("ID") || "?";
        if (ref) {
          if (!paramNames[ref]) {
            errors.push(makeIssue(2, "REF-01",
              "Strategy '" + sname + "': Control '" + ctrlId + "' references unknown parameter '" + ref + "'.",
              c));
          }
          if (seenRef[ref]) {
            errors.push(makeIssue(2, "REF-02",
              "Strategy '" + sname + "': parameter '" + ref + "' is referenced by more than one Control.",
              c));
          }
          seenRef[ref] = true;
        }
        var xsi = c.getAttributeNS(NS_XSI, "type");
        var bt = bareType(xsi) || "";
        if (LIST_CONTROL_TYPES[bt]) {
          var paramIds = paramEnumIds[ref] || {};
          var liIds = {};
          childrenNS(c, NS_LAY, "ListItem").forEach(function (li) {
            var eid = li.getAttribute("enumID");
            if (!eid) return;
            liIds[eid] = true;
            if (paramNames[ref] && !paramIds[eid]) {
              errors.push(makeIssue(2, "REF-06",
                "Strategy '" + sname + "': Control '" + ctrlId + "' has ListItem enumID='" + eid +
                "' not found in parameter '" + ref + "' EnumPairs.",
                c));
            }
          });
          var iv = c.getAttribute("initValue");
          if (iv) {
            var ids = (bt === "MultiSelectList_t") ? iv.split(/\s+/) : [iv];
            ids.forEach(function (cid) {
              if (cid && !liIds[cid]) {
                errors.push(makeIssue(2, "REF-07",
                  "Strategy '" + sname + "': Control '" + ctrlId + "' initValue '" + cid + "' is not a valid ListItem enumID.",
                  c));
              }
            });
          }
        }
      });

      /* REF-05: Edit field references must name a Parameter */
      descendantsNS(s, NS_VAL, "Edit").forEach(function (edit) {
        ["field", "field2"].forEach(function (a) {
          var v = edit.getAttribute(a);
          if (v && !paramNames[v]) {
            errors.push(makeIssue(2, "REF-05",
              "Strategy '" + sname + "': Edit references unknown parameter '" + v + "' via @" + a + ".",
              edit));
          }
        });
      });
    });

    return errors;
  }

  /* ---------- Phase 3: Semantic / business rules ---------- */
  function phase3(doc) {
    var errors = [];
    var warnings = [];
    var root = doc.documentElement;
    if (!root || root.localName !== "Strategies" || root.namespaceURI !== NS_CORE) return { errors: errors, warnings: warnings };

    var sit = root.getAttribute("strategyIdentifierTag");
    var stratList = childrenNS(root, NS_CORE, "Strategy");
    var seenStrat = {};
    var seenStratWire = {}; /* wireValue → first strategy name (SEM-21) */

    stratList.forEach(function (s) {
      var sname = s.getAttribute("name") || "?";

      /* SEM-05 */
      if (seenStrat[sname]) {
        errors.push(makeIssue(3, "SEM-05", "Duplicate Strategy name '" + sname + "'.", s));
      }
      seenStrat[sname] = true;

      /* SEM-21: Strategy wireValue must be unique across all Strategies, otherwise
         the receiving system cannot tell which strategy the order targets. */
      var swv = s.getAttribute("wireValue");
      if (swv) {
        if (seenStratWire[swv]) {
          errors.push(makeIssue(3, "SEM-21",
            "Duplicate Strategy wireValue '" + swv + "' (also used by Strategy '" + seenStratWire[swv] + "').", s));
        } else {
          seenStratWire[swv] = sname;
        }
      }

      var seenParam = {};
      var fixTags = {};
      childrenNS(s, NS_CORE, "Parameter").forEach(function (p) {
        var name = p.getAttribute("name") || "?";
        if (seenParam[name]) {
          errors.push(makeIssue(3, "SEM-06", "Strategy '" + sname + "': duplicate Parameter name '" + name + "'.", p));
        }
        seenParam[name] = true;

        var ft = p.getAttribute("fixTag");
        if (ft) {
          if (fixTags[ft]) {
            errors.push(makeIssue(3, "SEM-15", "Strategy '" + sname + "': Parameter fixTag " + ft + " used by both '" + fixTags[ft] + "' and '" + name + "'.", p));
          }
          fixTags[ft] = name;
          if (sit && ft === sit) {
            errors.push(makeIssue(3, "SEM-16", "Strategy '" + sname + "': Parameter '" + name + "' fixTag " + ft + " collides with Strategies/@strategyIdentifierTag.", p));
          }
          var n = parseInt(ft, 10);
          if (!isNaN(n) && (n < 5000 || n > 9999)) {
            warnings.push(makeIssue(3, "SEM-14W",
              "Parameter '" + name + "' fixTag " + ft + " is outside the user-defined range (5000–9999).",
              p));
          }
        }

        var bt = bareType(p.getAttributeNS(NS_XSI, "type")) || "";

        /* SEM-01 / SEM-02: unique wireValue / enumID */
        var seenWire = {}, seenEid = {};
        childrenNS(p, NS_CORE, "EnumPair").forEach(function (ep) {
          var wv = ep.getAttribute("wireValue");
          var eid = ep.getAttribute("enumID");
          if (wv != null) {
            if (seenWire[wv]) errors.push(makeIssue(3, "SEM-01", "Strategy '" + sname + "', Parameter '" + name + "': duplicate EnumPair wireValue '" + wv + "'.", ep));
            seenWire[wv] = true;
          }
          if (eid != null) {
            if (seenEid[eid]) errors.push(makeIssue(3, "SEM-02", "Strategy '" + sname + "', Parameter '" + name + "': duplicate EnumPair enumID '" + eid + "'.", ep));
            seenEid[eid] = true;
            if (!/^[A-Za-z][A-Za-z0-9_]{0,255}$/.test(eid)) {
              errors.push(makeIssue(3, "SEM-03", "Strategy '" + sname + "', Parameter '" + name + "': enumID '" + eid + "' must match [A-Za-z][A-Za-z0-9_]{0,255}.", ep));
            }
          }
        });

        /* SEM-09: minValue ≤ maxValue */
        var minV = p.getAttribute("minValue"), maxV = p.getAttribute("maxValue");
        if (NUMERIC_TYPES[bt] && minV != null && maxV != null) {
          var lo = parseFloat(minV), hi = parseFloat(maxV);
          if (!isNaN(lo) && !isNaN(hi) && lo > hi) {
            errors.push(makeIssue(3, "SEM-09", "Strategy '" + sname + "', Parameter '" + name + "': minValue (" + lo + ") > maxValue (" + hi + ").", p));
          }
        }

        /* SEM-23W: minValue/maxValue on a non-numeric parameter has no effect
           (XSD allows the attributes on Parameter_t but they are only meaningful
           for numeric subtypes). */
        if (!NUMERIC_TYPES[bt] && bt && (minV != null || maxV != null)) {
          warnings.push(makeIssue(3, "SEM-23W",
            "Strategy '" + sname + "', Parameter '" + name + "': minValue/maxValue declared on non-numeric type '" + bt + "' — value bounds will be ignored.",
            p));
        }

        /* SEM-10: minLength ≤ maxLength (string types) */
        var minL = p.getAttribute("minLength"), maxL = p.getAttribute("maxLength");
        if (minL != null && maxL != null) {
          var a = parseInt(minL, 10), b = parseInt(maxL, 10);
          if (!isNaN(a) && !isNaN(b) && a > b) {
            errors.push(makeIssue(3, "SEM-10", "Strategy '" + sname + "', Parameter '" + name + "': minLength (" + a + ") > maxLength (" + b + ").", p));
          }
        }
      });

      /* Build per-strategy parameter index (type, min, max) once. */
      var paramType = {}, paramMin = {}, paramMax = {};
      var paramElems = childrenNS(s, NS_CORE, "Parameter");
      paramElems.forEach(function (p) {
        var nm = p.getAttribute("name");
        if (!nm) return;
        paramType[nm] = bareType(p.getAttributeNS(NS_XSI, "type"));
        var mn = p.getAttribute("minValue"), mx = p.getAttribute("maxValue");
        if (mn != null && mn !== "") paramMin[nm] = parseFloat(mn);
        if (mx != null && mx !== "") paramMax[nm] = parseFloat(mx);
      });

      /* SEM-28W: Strategy declares no Parameters — nothing for the user to
         configure and no fields to send beyond the strategy identifier. */
      if (paramElems.length === 0) {
        warnings.push(makeIssue(3, "SEM-28W",
          "Strategy '" + sname + "' declares no Parameters — the form will be empty.", s));
      }

      var layout = childrenNS(s, NS_LAY, "StrategyLayout")[0];
      var seenCtrlId = {};      /* SEM-18: Control/@ID uniqueness within strategy */
      var boundParams = {};     /* SEM-19W: which Parameters are bound by some Control */
      if (layout) {
        descendantsNS(layout, NS_LAY, "Control").forEach(function (c) {
          var cid = c.getAttribute("ID") || "?";
          var ref = c.getAttribute("parameterRef");
          var ctrl = bareType(c.getAttributeNS(NS_XSI, "type"));

          /* SEM-18: duplicate Control ID within a strategy. */
          if (cid && cid !== "?") {
            if (seenCtrlId[cid]) {
              errors.push(makeIssue(3, "SEM-18",
                "Strategy '" + sname + "': duplicate Control ID '" + cid + "'.", c));
            }
            seenCtrlId[cid] = true;
          }

          /* SEM-20W: input-bearing controls should reference a parameter.
             Label_t is the only purely decorative control type. */
          if (!ref && ctrl && ctrl !== "Label_t") {
            warnings.push(makeIssue(3, "SEM-20W",
              "Strategy '" + sname + "': Control '" + cid + "' (" + ctrl + ") has no parameterRef — its value will not be sent.", c));
          }
          if (ref) boundParams[ref] = true;

          /* SEM-17: ListItem enumIDs within a single Control must be unique
             (otherwise two drop-down options collapse to one). */
          if (LIST_CONTROL_TYPES[ctrl]) {
            var seenLi = {};
            var listItems = childrenNS(c, NS_LAY, "ListItem");
            listItems.forEach(function (li) {
              var eid = li.getAttribute("enumID");
              if (!eid) return;
              if (seenLi[eid]) {
                errors.push(makeIssue(3, "SEM-17",
                  "Strategy '" + sname + "': Control '" + cid + "' has duplicate ListItem enumID '" + eid + "'.", li));
              }
              seenLi[eid] = true;
            });

            /* SEM-26W: list-style controls with no options render an empty
               drop-down. (Skip if the bound parameter has EnumPairs — those
               can populate the list at runtime via the parameter side.) */
            if (listItems.length === 0) {
              var paramHasEnums = false;
              paramElems.forEach(function (pe) {
                if (pe.getAttribute("name") === ref &&
                    childrenNS(pe, NS_CORE, "EnumPair").length > 0) {
                  paramHasEnums = true;
                }
              });
              if (!paramHasEnums) {
                warnings.push(makeIssue(3, "SEM-26W",
                  "Strategy '" + sname + "': List-style Control '" + cid + "' (" + ctrl + ") has no ListItems — drop-down will be empty.", c));
              }
            }
          }

          if (!ref || !paramType[ref]) return;
          var pt = paramType[ref];

          /* SEM-08W / SEM-08bW: type compatibility (existing). */
          if ((ctrl === "SingleSpinner_t" || ctrl === "DoubleSpinner_t" || ctrl === "Slider_t") && !NUMERIC_TYPES[pt]) {
            warnings.push(makeIssue(3, "SEM-08W",
              "Strategy '" + sname + "': Control '" + cid + "' (" + ctrl + ") bound to non-numeric parameter '" + ref + "' (" + pt + ").",
              c));
          }
          if (ctrl === "Clock_t" && ["UTCTimeOnly_t","UTCTimestamp_t","UTCDate_t","LocalMktDate_t","LocalMktTime_t","MonthYear_t"].indexOf(pt) < 0) {
            warnings.push(makeIssue(3, "SEM-08bW",
              "Strategy '" + sname + "': Control '" + cid + "' (Clock_t) bound to non-time parameter '" + ref + "' (" + pt + ").",
              c));
          }

          /* SEM-25W: initValue must fall inside the parameter's [minValue,
             maxValue] bounds when both are declared and the parameter is
             numeric. (For list controls, REF-07 already validates the
             initValue against the ListItem set.) */
          var iv = c.getAttribute("initValue");
          if (iv != null && iv !== "" && NUMERIC_TYPES[pt] && !LIST_CONTROL_TYPES[ctrl]) {
            var ivn = parseFloat(iv);
            if (!isNaN(ivn)) {
              if (paramMin[ref] != null && ivn < paramMin[ref]) {
                warnings.push(makeIssue(3, "SEM-25W",
                  "Strategy '" + sname + "': Control '" + cid + "' initValue " + iv + " is below parameter '" + ref + "' minValue " + paramMin[ref] + ".", c));
              }
              if (paramMax[ref] != null && ivn > paramMax[ref]) {
                warnings.push(makeIssue(3, "SEM-25W",
                  "Strategy '" + sname + "': Control '" + cid + "' initValue " + iv + " is above parameter '" + ref + "' maxValue " + paramMax[ref] + ".", c));
              }
            }
          }
        });
      }

      /* SEM-19W: Parameters that no Control binds to are unreachable from
         the UI. Skip parameters marked const="true" — those are sent as
         constants regardless of UI presence. */
      paramElems.forEach(function (p) {
        var nm = p.getAttribute("name");
        if (!nm || boundParams[nm]) return;
        if (p.getAttribute("const") === "true") return;
        warnings.push(makeIssue(3, "SEM-19W",
          "Strategy '" + sname + "': Parameter '" + nm + "' is not bound to any Control — user cannot set its value.", p));
      });
    });

    return { errors: errors, warnings: warnings };
  }

  /* ---------- Top-level entry ---------- */
  function validate(xmlText, options) {
    options = options || {};
    var doc = new DOMParser().parseFromString(xmlText, "application/xml");
    var perr = doc.getElementsByTagName("parsererror")[0];
    if (perr) {
      var msg = (perr.textContent || "Invalid XML").replace(/\s+/g, " ").trim();
      return {
        wellFormed: false,
        summary: { strategies: 0, parameters: 0, controls: 0 },
        errors: [makeIssue(0, "XML-WF", "XML parse error: " + msg)],
        warnings: [],
        xsdAvailable: !!options.xsdModel
      };
    }

    assignLines(doc, xmlText);

    var root = doc.documentElement;
    var strategies = (root && root.namespaceURI === NS_CORE && root.localName === "Strategies")
      ? childrenNS(root, NS_CORE, "Strategy") : [];
    var totalParams = 0, totalCtrls = 0;
    strategies.forEach(function (s) {
      totalParams += childrenNS(s, NS_CORE, "Parameter").length;
      var lay = childrenNS(s, NS_LAY, "StrategyLayout")[0];
      if (lay) totalCtrls += descendantsNS(lay, NS_LAY, "Control").length;
    });

    /* Phase 0: XSD-driven structural validation (only if the caller
       supplied a parsed schema model and AtdlXsdValidator is present). */
    var p0 = [];
    if (options.xsdModel && global.AtdlXsdValidator) {
      p0 = global.AtdlXsdValidator.validate(doc, options.xsdModel);
    }

    var p1 = phase1(doc, xmlText);
    var p2 = (p1.length === 0) ? phase2(doc) : [];
    var p3 = (p1.length === 0) ? phase3(doc) : { errors: [], warnings: [] };

    return {
      wellFormed: true,
      summary: { strategies: strategies.length, parameters: totalParams, controls: totalCtrls },
      errors: p0.concat(p1, p2, p3.errors),
      warnings: p3.warnings,
      xsdAvailable: !!options.xsdModel
    };
  }

  global.AtdlValidator = { validate: validate };
})(window);
