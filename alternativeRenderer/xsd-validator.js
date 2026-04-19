/* xsd-validator.js — structural validation of an ATDL XML document against
   the schema model produced by xsd-loader.js. Emits the same issue shape
   (phase / ruleId / message / element / line) as atdl-validator.js.

   Rules fired (all errors, phase 0):
     XSD-ROOT      Root element is not declared in any loaded schema.
     XSD-CHILD     Child element is not allowed at this position per the
                   parent's content model.
     XSD-TYPE      xsi:type points to a type not declared in any schema.
     XSD-ABSTRACT  Element's declared type is abstract and no xsi:type
                   selects a concrete subtype.
     XSD-ATTR      Attribute is not declared on the element's type (nor
                   inherited through any extension ancestor).
     XSD-REQ       Attribute with use="required" is missing.
     XSD-VAL       Attribute value fails its simple type facet (enum /
                   pattern / length) or built-in lexical form.
*/
(function (global) {
  "use strict";

  var XS    = "http://www.w3.org/2001/XMLSchema";
  var NS_XSI = "http://www.w3.org/2001/XMLSchema-instance";

  function key(ns, local) { return "{" + (ns || "") + "}" + local; }

  function resolveQName(el, prefixed) {
    if (!prefixed) return null;
    var i = prefixed.indexOf(":");
    if (i < 0) return "{" + (el.namespaceURI || "") + "}" + prefixed;
    var prefix = prefixed.substring(0, i);
    var local  = prefixed.substring(i + 1);
    var ns = el.lookupNamespaceURI ? el.lookupNamespaceURI(prefix) : null;
    return "{" + (ns || "") + "}" + local;
  }

  /* Walk the extension chain of a complex type and merge allowed
     attributes (including deref'd attribute groups) and allowed child
     elements into a single effective type. */
  function flatten(typeRef, model, out, seen) {
    if (!typeRef || seen[typeRef]) return;
    seen[typeRef] = true;
    var ct = model.complexTypes[typeRef];
    if (!ct) return;
    flatten(ct.baseType, model, out, seen);
    Object.keys(ct.attrs).forEach(function (k) { out.attrs[k] = ct.attrs[k]; });
    ct.groupRefs.forEach(function (gRef) {
      var g = model.attributeGroups[gRef];
      if (!g) return;
      Object.keys(g.attrs).forEach(function (k) { out.attrs[k] = g.attrs[k]; });
      g.groupRefs.forEach(function (gg) {
        var sub = model.attributeGroups[gg];
        if (sub) Object.keys(sub.attrs).forEach(function (k) { out.attrs[k] = sub.attrs[k]; });
      });
    });
    if (ct.anyAttribute) out.anyAttribute = true;
    ct.sequence.forEach(function (item) {
      if (item.kind === "ref") {
        var decl = model.elements[item.ref];
        var tref = decl ? decl.typeRef : null;
        var inline = decl ? decl.inline : null;
        out.children[item.ref] = { typeRef: tref, inline: inline, abstract: decl ? decl.abstract : false };
      } else if (item.kind === "local") {
        out.children[item.key] = { typeRef: item.type, inline: item.inline, abstract: false };
      }
    });
  }

  function effectiveType(el, declaredType, model) {
    var xsi = el.getAttributeNS(NS_XSI, "type");
    if (!xsi) return { typeRef: declaredType, xsiUsed: false };
    var resolved = resolveQName(el, xsi);
    return { typeRef: resolved, xsiUsed: true, xsiRaw: xsi };
  }

  /* Built-in lexical checks for the xs:* types FIXatdl actually uses. */
  function checkBuiltin(typeRef, value) {
    if (!typeRef || typeRef.indexOf("{" + XS + "}") !== 0) return null;
    var local = typeRef.substring(XS.length + 2);
    switch (local) {
      case "string": case "token": case "normalizedString":
      case "Name": case "NCName": case "NMTOKEN": case "ID": case "IDREF":
      case "anyURI": case "QName": case "anySimpleType": case "anyType":
        return null;
      case "boolean":
        return /^(true|false|0|1)$/.test(value) ? null : "must be xsd:boolean";
      case "integer": case "int": case "long": case "short": case "byte":
        return /^[+-]?\d+$/.test(value) ? null : "must be an integer";
      case "nonNegativeInteger": case "unsignedInt": case "unsignedLong": case "unsignedShort": case "unsignedByte":
        return /^\+?\d+$/.test(value) ? null : "must be a non-negative integer";
      case "positiveInteger":
        return /^\+?[1-9]\d*$/.test(value) ? null : "must be a positive integer";
      case "negativeInteger":
        return /^-[1-9]\d*$/.test(value) ? null : "must be a negative integer";
      case "nonPositiveInteger":
        return /^(?:0|-[1-9]\d*)$/.test(value) ? null : "must be a non-positive integer";
      case "decimal": case "float": case "double":
        return /^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(value) ? null : "must be a decimal number";
      case "date":
        return /^-?\d{4}-\d{2}-\d{2}(Z|[+-]\d{2}:\d{2})?$/.test(value) ? null : "must be xsd:date";
      case "time":
        return /^\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$/.test(value) ? null : "must be xsd:time";
      case "dateTime":
        return /^-?\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$/.test(value) ? null : "must be xsd:dateTime";
      default:
        return null; /* unknown xs:* type — don't flag */
    }
  }

  /* Recursively validate a value against a simple type (walks its base
     chain until a built-in or null base is reached). */
  function checkSimple(st, value, model) {
    if (!st) return null;
    if (st.enumerations && st.enumerations.length > 0) {
      if (st.enumerations.indexOf(value) < 0) {
        var preview = st.enumerations.slice(0, 8).join(", ");
        if (st.enumerations.length > 8) preview += ", …";
        return "value not in enumeration {" + preview + "}";
      }
    }
    if (st.pattern) {
      try {
        var re = new RegExp("^(?:" + st.pattern + ")$");
        if (!re.test(value)) return "does not match pattern '" + st.pattern + "'";
      } catch (e) { /* unsupported regex, skip */ }
    }
    if (st.minLength != null && value.length < st.minLength) return "length " + value.length + " < minLength " + st.minLength;
    if (st.maxLength != null && value.length > st.maxLength) return "length " + value.length + " > maxLength " + st.maxLength;
    if (st.base) {
      var nested = model.simpleTypes[st.base];
      if (nested) return checkSimple(nested, value, model);
      return checkBuiltin(st.base, value);
    }
    return null;
  }

  function validateAttrValue(def, value, model) {
    if (def.inline) {
      var err = checkSimple(def.inline, value, model);
      if (err) return err;
    }
    if (def.type) {
      var st = model.simpleTypes[def.type];
      if (st) return checkSimple(st, value, model);
      return checkBuiltin(def.type, value);
    }
    return null;
  }

  function validate(doc, model) {
    var issues = [];
    if (!doc || !doc.documentElement) return issues;
    if (!model || !model.elements) return issues;

    var root = doc.documentElement;
    var rootKey = key(root.namespaceURI, root.localName);
    var rootDecl = model.elements[rootKey];
    if (!rootDecl) {
      issues.push(makeIssue("XSD-ROOT",
        "Root element <" + root.localName + "> is not declared in the bundled schemas.",
        root));
      return issues;
    }

    walk(root, rootDecl.typeRef, rootDecl.inline, rootDecl.abstract, issues, model);
    return issues;
  }

  function walk(el, declaredType, inlineDecl, declaredAbstract, issues, model) {
    /* Resolve the effective type: xsi:type overrides the declared one. */
    var eff = effectiveType(el, declaredType, model);
    var typeRef = eff.typeRef;
    var ctInline = (inlineDecl && inlineDecl.complex) || null;

    if (eff.xsiUsed) {
      if (!model.complexTypes[typeRef] && !model.simpleTypes[typeRef]) {
        issues.push(makeIssue("XSD-TYPE",
          "xsi:type '" + eff.xsiRaw + "' is not declared in the loaded schemas.", el));
        return;
      }
      ctInline = null; /* xsi:type supersedes any inline decl */
    } else {
      var declCt = typeRef && model.complexTypes[typeRef];
      if (declCt && declCt.abstract && !ctInline) {
        issues.push(makeIssue("XSD-ABSTRACT",
          "<" + el.localName + "> uses abstract type '" + localOf(typeRef) + "' and must carry xsi:type selecting a concrete subtype.", el));
        return;
      }
    }

    /* Simple-typed elements: validate textContent, skip attrs/children. */
    var st = typeRef ? model.simpleTypes[typeRef] : null;
    if (st) {
      var err = checkSimple(st, el.textContent || "", model);
      if (err) issues.push(makeIssue("XSD-VAL", "<" + el.localName + ">: " + err, el));
      return;
    }

    /* Non-declared complex type (and no inline) — silently skip walking. */
    if (!ctInline && !model.complexTypes[typeRef]) return;

    /* Build the effective attribute + child element set. */
    var eff2 = { attrs: {}, children: {}, anyAttribute: false };
    if (ctInline) {
      /* inline complexType: walk just this type (no base chain). */
      Object.keys(ctInline.attrs).forEach(function (k) { eff2.attrs[k] = ctInline.attrs[k]; });
      ctInline.sequence.forEach(function (item) {
        if (item.kind === "ref") {
          var decl = model.elements[item.ref];
          eff2.children[item.ref] = { typeRef: decl && decl.typeRef, inline: decl && decl.inline, abstract: decl && decl.abstract };
        } else {
          eff2.children[item.key] = { typeRef: item.type, inline: item.inline, abstract: false };
        }
      });
      if (ctInline.anyAttribute) eff2.anyAttribute = true;
    } else {
      flatten(typeRef, model, eff2, {});
    }

    /* Attributes: unknown, required, value-constrained. */
    var present = {};
    for (var i = 0; i < el.attributes.length; i++) {
      var a = el.attributes[i];
      if (a.name === "xmlns" || a.name.indexOf("xmlns:") === 0) continue;
      if (a.namespaceURI === NS_XSI) continue;
      present[a.localName] = a.value;
      var def = eff2.attrs[a.localName];
      if (!def) {
        if (!eff2.anyAttribute) {
          issues.push(makeIssue("XSD-ATTR",
            "Unknown attribute '" + a.localName + "' on <" + el.localName + ">.", el));
        }
      } else {
        var msg = validateAttrValue(def, a.value, model);
        if (msg) {
          issues.push(makeIssue("XSD-VAL",
            "<" + el.localName + ">/@" + a.localName + " = '" + a.value + "' — " + msg + ".", el));
        }
      }
    }
    Object.keys(eff2.attrs).forEach(function (n) {
      if (eff2.attrs[n].use === "required" && !(n in present)) {
        issues.push(makeIssue("XSD-REQ",
          "Required attribute '" + n + "' missing on <" + el.localName + ">.", el));
      }
    });

    /* Children: allowed membership + recurse. */
    for (var j = 0; j < el.childNodes.length; j++) {
      var c = el.childNodes[j];
      if (c.nodeType !== 1) continue;
      var cKey = key(c.namespaceURI, c.localName);
      var slot = eff2.children[cKey];
      if (!slot) {
        issues.push(makeIssue("XSD-CHILD",
          "<" + c.localName + "> is not an allowed child of <" + el.localName + ">.", c));
        continue;
      }
      walk(c, slot.typeRef, slot.inline, slot.abstract, issues, model);
    }
  }

  function makeIssue(ruleId, message, el) {
    return {
      phase: 0,
      ruleId: ruleId,
      message: message,
      element: (function () {
        var parts = [];
        var n = el;
        while (n && n.nodeType === 1) {
          var seg = n.localName + (n.getAttribute && n.getAttribute("name") ? "[@name='" + n.getAttribute("name") + "']" : "");
          parts.unshift(seg);
          n = n.parentNode;
        }
        return parts.join("/");
      })(),
      line: el && el.__atdlLine ? el.__atdlLine : null
    };
  }

  function localOf(qname) {
    if (!qname) return "?";
    var i = qname.indexOf("}");
    return i >= 0 ? qname.substring(i + 1) : qname;
  }

  global.AtdlXsdValidator = { validate: validate };
})(window);
