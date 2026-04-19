/* xsd-loader.js — fetches the bundled FIXatdl 1.1 XSD files and parses
   them into a compact in-memory schema model used by xsd-validator.js.

   Supports the XSD 1.0 subset actually used by the FIXatdl 1.1 schemas:
     - <xs:element name|ref|type|abstract> with optional inline type
     - <xs:complexType> with <xs:sequence>, <xs:choice> (flattened),
       <xs:complexContent>/<xs:extension base>
     - <xs:simpleType> with <xs:restriction base>, <xs:enumeration>,
       <xs:pattern>, <xs:minLength>/<xs:maxLength>
     - <xs:attribute name|ref|type|use|default|fixed> with inline simpleType
     - <xs:attributeGroup name|ref>
     - <xs:import namespace|schemaLocation>

   Not supported (not used by these schemas): xs:group, xs:any,
   substitutionGroup, xs:union/xs:list, key/keyref/unique.

   Qualified names are stored as "{namespaceURI}localName". "xs:*"
   references stay as "{http://www.w3.org/2001/XMLSchema}foo" — the
   validator recognises that namespace as built-in.
*/
(function (global) {
  "use strict";

  var XS = "http://www.w3.org/2001/XMLSchema";

  function kidsNs(el, ns, local) {
    var out = [];
    for (var i = 0; i < el.childNodes.length; i++) {
      var c = el.childNodes[i];
      if (c.nodeType === 1 && c.namespaceURI === ns && c.localName === local) out.push(c);
    }
    return out;
  }

  /* Build a prefix→namespace map by walking up from `el` and collecting
     xmlns declarations. DOM's lookupNamespaceURI would serve the same
     purpose but varies subtly across browsers; this is explicit. */
  function namespaceMap(el) {
    var map = {};
    var n = el;
    while (n && n.nodeType === 1) {
      if (n.attributes) {
        for (var i = 0; i < n.attributes.length; i++) {
          var a = n.attributes[i];
          if (a.name === "xmlns" && !map[""]) map[""] = a.value;
          else if (a.name.indexOf("xmlns:") === 0) {
            var p = a.name.substring(6);
            if (!map[p]) map[p] = a.value;
          }
        }
      }
      n = n.parentNode;
    }
    return map;
  }

  function qname(prefixed, nsMap, defaultNs) {
    if (!prefixed) return null;
    var i = prefixed.indexOf(":");
    if (i < 0) return "{" + (defaultNs || "") + "}" + prefixed;
    var prefix = prefixed.substring(0, i);
    var local = prefixed.substring(i + 1);
    var ns = nsMap[prefix];
    return "{" + (ns || "") + "}" + local;
  }

  /* Parse a <xs:simpleType> container into { base, enumerations, pattern,
     minLength, maxLength }. */
  function parseSimpleType(st, nsMap, defaultNs) {
    var out = { base: null, enumerations: null, pattern: null, minLength: null, maxLength: null };
    var r = kidsNs(st, XS, "restriction")[0];
    if (!r) return out;
    out.base = qname(r.getAttribute("base"), nsMap, defaultNs);
    var enums = kidsNs(r, XS, "enumeration");
    if (enums.length) out.enumerations = enums.map(function (e) { return e.getAttribute("value"); });
    var p = kidsNs(r, XS, "pattern")[0];
    if (p) out.pattern = p.getAttribute("value");
    var mn = kidsNs(r, XS, "minLength")[0]; if (mn) out.minLength = parseInt(mn.getAttribute("value"), 10);
    var mx = kidsNs(r, XS, "maxLength")[0]; if (mx) out.maxLength = parseInt(mx.getAttribute("value"), 10);
    return out;
  }

  /* Parse <xs:attribute> children of `container` and <xs:attributeGroup
     ref=...> references (deferred — resolved at validate time). Inline
     simpleType restrictions are stored on the attribute directly. */
  function parseAttributes(container, nsMap, defaultNs) {
    var out = { attrs: {}, groupRefs: [] };
    kidsNs(container, XS, "attribute").forEach(function (a) {
      var name = a.getAttribute("name");
      if (!name) return;
      var inline = null;
      var st = kidsNs(a, XS, "simpleType")[0];
      if (st) inline = parseSimpleType(st, nsMap, defaultNs);
      out.attrs[name] = {
        type: qname(a.getAttribute("type"), nsMap, defaultNs),
        use: a.getAttribute("use") || "optional",
        inline: inline
      };
    });
    kidsNs(container, XS, "attributeGroup").forEach(function (g) {
      var ref = g.getAttribute("ref");
      if (ref) out.groupRefs.push(qname(ref, nsMap, defaultNs));
    });
    return out;
  }

  /* Parse a content model container (xs:sequence / xs:choice) into a flat
     list of allowed element particles. Nested sequences/choices collapse
     into the same membership set — we don't enforce order or cardinality
     (those are not the value-add here). */
  function parseParticles(seq, nsMap, defaultNs) {
    var items = [];
    (function walk(node) {
      for (var i = 0; i < node.childNodes.length; i++) {
        var c = node.childNodes[i];
        if (c.nodeType !== 1 || c.namespaceURI !== XS) continue;
        if (c.localName === "element") items.push(parseElementParticle(c, nsMap, defaultNs));
        else if (c.localName === "sequence" || c.localName === "choice" || c.localName === "all") walk(c);
      }
    })(seq);
    return items;
  }

  function parseElementParticle(e, nsMap, defaultNs) {
    var ref = e.getAttribute("ref");
    if (ref) return { kind: "ref", ref: qname(ref, nsMap, defaultNs) };
    var name = e.getAttribute("name");
    var typeAttr = e.getAttribute("type");
    var typeRef = typeAttr ? qname(typeAttr, nsMap, defaultNs) : null;
    var inline = null;
    if (!typeRef) {
      var ct = kidsNs(e, XS, "complexType")[0];
      if (ct) inline = { complex: parseComplexType(ct, nsMap, defaultNs) };
      else {
        var st = kidsNs(e, XS, "simpleType")[0];
        if (st) inline = { simple: parseSimpleType(st, nsMap, defaultNs) };
      }
    }
    return { kind: "local", key: "{" + defaultNs + "}" + name, name: name, type: typeRef, inline: inline };
  }

  function parseComplexType(ct, nsMap, defaultNs) {
    var t = {
      baseType: null,
      sequence: [],
      attrs: {},
      groupRefs: [],
      anyAttribute: false,
      abstract: ct.getAttribute("abstract") === "true"
    };
    var cc = kidsNs(ct, XS, "complexContent")[0];
    if (cc) {
      var ext = kidsNs(cc, XS, "extension")[0] || kidsNs(cc, XS, "restriction")[0];
      if (ext) {
        t.baseType = qname(ext.getAttribute("base"), nsMap, defaultNs);
        var seq = kidsNs(ext, XS, "sequence")[0] || kidsNs(ext, XS, "choice")[0] || kidsNs(ext, XS, "all")[0];
        if (seq) t.sequence = parseParticles(seq, nsMap, defaultNs);
        var a = parseAttributes(ext, nsMap, defaultNs);
        t.attrs = a.attrs; t.groupRefs = a.groupRefs;
        if (kidsNs(ext, XS, "anyAttribute")[0]) t.anyAttribute = true;
        return t;
      }
    }
    var simpleExt = kidsNs(ct, XS, "simpleContent")[0];
    if (simpleExt) {
      var sext = kidsNs(simpleExt, XS, "extension")[0] || kidsNs(simpleExt, XS, "restriction")[0];
      if (sext) {
        t.baseType = qname(sext.getAttribute("base"), nsMap, defaultNs);
        var sa = parseAttributes(sext, nsMap, defaultNs);
        t.attrs = sa.attrs; t.groupRefs = sa.groupRefs;
        if (kidsNs(sext, XS, "anyAttribute")[0]) t.anyAttribute = true;
        return t;
      }
    }
    var s = kidsNs(ct, XS, "sequence")[0] || kidsNs(ct, XS, "choice")[0] || kidsNs(ct, XS, "all")[0];
    if (s) t.sequence = parseParticles(s, nsMap, defaultNs);
    var aa = parseAttributes(ct, nsMap, defaultNs);
    t.attrs = aa.attrs; t.groupRefs = aa.groupRefs;
    if (kidsNs(ct, XS, "anyAttribute")[0]) t.anyAttribute = true;
    return t;
  }

  function parseSchemaDoc(doc, model) {
    var schema = doc.documentElement;
    if (!schema || schema.localName !== "schema" || schema.namespaceURI !== XS) return;
    var tns = schema.getAttribute("targetNamespace") || "";
    var nsMap = namespaceMap(schema);

    kidsNs(schema, XS, "complexType").forEach(function (ct) {
      var name = ct.getAttribute("name");
      if (!name) return;
      model.complexTypes["{" + tns + "}" + name] = parseComplexType(ct, nsMap, tns);
    });
    kidsNs(schema, XS, "simpleType").forEach(function (st) {
      var name = st.getAttribute("name");
      if (!name) return;
      model.simpleTypes["{" + tns + "}" + name] = parseSimpleType(st, nsMap, tns);
    });
    kidsNs(schema, XS, "attributeGroup").forEach(function (ag) {
      var name = ag.getAttribute("name");
      if (!name) return;
      model.attributeGroups["{" + tns + "}" + name] = parseAttributes(ag, nsMap, tns);
    });
    kidsNs(schema, XS, "element").forEach(function (e) {
      var name = e.getAttribute("name");
      if (!name) return;
      var decl = { typeRef: null, inline: null, abstract: e.getAttribute("abstract") === "true" };
      var t = e.getAttribute("type");
      if (t) decl.typeRef = qname(t, nsMap, tns);
      else {
        var ct = kidsNs(e, XS, "complexType")[0];
        if (ct) decl.inline = { complex: parseComplexType(ct, nsMap, tns) };
        else {
          var st = kidsNs(e, XS, "simpleType")[0];
          if (st) decl.inline = { simple: parseSimpleType(st, nsMap, tns) };
        }
      }
      model.elements["{" + tns + "}" + name] = decl;
    });
  }

  function buildModel(texts) {
    var model = { complexTypes: {}, simpleTypes: {}, attributeGroups: {}, elements: {} };
    texts.forEach(function (t) {
      var doc = new DOMParser().parseFromString(t, "application/xml");
      parseSchemaDoc(doc, model);
    });
    return model;
  }

  function load(baseUrl) {
    var files = [
      "atdl-core-1-1.xsd",
      "atdl-layout-1-1.xsd",
      "atdl-flow-1-1.xsd",
      "atdl-validation-1-1.xsd",
      "atdl-regions-1-1.xsd",
      "atdl-timezones-1-1.xsd"
    ];
    /* If schemas-embedded.js is loaded, use that — lets the page work
       from file:// where cross-origin fetch is blocked. Falls through
       to fetch() when the embedded bundle is missing or incomplete. */
    var bundle = global.ATDL_EMBEDDED_XSDS;
    if (bundle && files.every(function (f) { return typeof bundle[f] === "string"; })) {
      var texts = files.map(function (f) { return bundle[f]; });
      return Promise.resolve(buildModel(texts));
    }
    var base = (baseUrl || "schemas/");
    return Promise.all(files.map(function (f) {
      return fetch(base + f).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status + " fetching " + f);
        return r.text();
      });
    })).then(buildModel);
  }

  global.AtdlXsdLoader = { load: load };
})(window);
