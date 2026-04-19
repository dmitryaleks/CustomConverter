/* xml-highlight.js — minimal XML syntax highlighter with line numbers.
   Emits HTML wrapping tokens in spans with classes:
     xml-decl, xml-comment, xml-tag-bracket, xml-tag, xml-attr, xml-string, xml-text
*/
(function (global) {
  "use strict";

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  /* Tokenize then emit — regex-based, handles <?xml?>, comments, tags with attrs. */
  function highlight(text) {
    /* Strategy: split by top-level constructs. Process markup regions
       and leave text regions as escaped plain text. */
    var out = "";
    var i = 0, n = text.length;
    while (i < n) {
      if (text.charCodeAt(i) === 60 /* '<' */) {
        if (text.substr(i, 4) === "<!--") {
          var end = text.indexOf("-->", i + 4);
          if (end < 0) { out += wrap("xml-comment", escapeHtml(text.substr(i))); i = n; }
          else { out += wrap("xml-comment", escapeHtml(text.substring(i, end + 3))); i = end + 3; }
        } else if (text.substr(i, 5) === "<?xml" || text.charAt(i + 1) === "?") {
          var pEnd = text.indexOf("?>", i + 2);
          if (pEnd < 0) { out += wrap("xml-decl", escapeHtml(text.substr(i))); i = n; }
          else { out += wrap("xml-decl", escapeHtml(text.substring(i, pEnd + 2))); i = pEnd + 2; }
        } else if (text.substr(i, 9) === "<![CDATA[") {
          var cEnd = text.indexOf("]]>", i + 9);
          if (cEnd < 0) { out += wrap("xml-cdata", escapeHtml(text.substr(i))); i = n; }
          else { out += wrap("xml-cdata", escapeHtml(text.substring(i, cEnd + 3))); i = cEnd + 3; }
        } else {
          /* Regular tag */
          var tagEnd = text.indexOf(">", i + 1);
          if (tagEnd < 0) { out += escapeHtml(text.substr(i)); i = n; }
          else {
            out += renderTag(text.substring(i, tagEnd + 1));
            i = tagEnd + 1;
          }
        }
      } else {
        /* Text node until next < */
        var lt = text.indexOf("<", i);
        if (lt < 0) { out += wrap("xml-text", escapeHtml(text.substr(i))); i = n; }
        else { out += wrap("xml-text", escapeHtml(text.substring(i, lt))); i = lt; }
      }
    }
    return out;
  }

  function wrap(cls, content) {
    if (!content) return "";
    return '<span class="' + cls + '">' + content + "</span>";
  }

  /* Render a single tag (including opening/closing/empty). */
  function renderTag(src) {
    /* Closing tag? */
    var m = /^<\/([\w:-]+)\s*>$/.exec(src);
    if (m) {
      return wrap("xml-tag-bracket", "&lt;/") + wrap("xml-tag", escapeHtml(m[1])) + wrap("xml-tag-bracket", "&gt;");
    }
    /* Opening / empty-element tag: <name attrs .../> or <name attrs ...> */
    var mm = /^<([\w:-]+)([\s\S]*?)(\/?)\s*>$/.exec(src);
    if (!mm) return escapeHtml(src);
    var name = mm[1], rest = mm[2], slash = mm[3];
    return wrap("xml-tag-bracket", "&lt;") +
           wrap("xml-tag", escapeHtml(name)) +
           renderAttrs(rest) +
           wrap("xml-tag-bracket", escapeHtml(slash) + "&gt;");
  }

  function renderAttrs(src) {
    /* Preserve whitespace, color attribute names and string values. */
    var out = "";
    var re = /(\s+)([\w:-]+)\s*=\s*("(?:[^"]|&quot;)*"|'(?:[^']|&apos;)*')/g;
    var lastIndex = 0;
    var m;
    while ((m = re.exec(src))) {
      if (m.index > lastIndex) out += escapeHtml(src.substring(lastIndex, m.index));
      out += escapeHtml(m[1]);
      out += wrap("xml-attr", escapeHtml(m[2]));
      out += "=";
      out += wrap("xml-string", escapeHtml(m[3]));
      lastIndex = m.index + m[0].length;
    }
    if (lastIndex < src.length) out += escapeHtml(src.substring(lastIndex));
    return out;
  }

  /* Render the highlighted text inside a line-numbered block. Spans emitted
     by highlight() can contain literal newlines (e.g. xml-text whitespace
     between tags, multi-line comments, multi-line tag attribute lists).
     Splitting naively on "\n" leaves orphan </span> tags on continuation
     lines, which the browser silently reparents — turning sibling tag
     spans into extra flex children of .xml-line and pushing the content
     to the right. Balance the spans by closing them at end of each line
     and reopening on the next. */
  function renderWithLineNumbers(text, markers) {
    var highlighted = highlight(text);
    var lines = highlighted.split("\n");
    var width = String(lines.length).length;
    var openTag = null; /* the <span ...> tag currently open across newline */
    var spanRe = /<span\b[^>]*>|<\/span>/g;
    var rows = lines.map(function (raw, idx) {
      var prefix = openTag || "";
      var line = prefix + raw;
      spanRe.lastIndex = 0;
      var depth = 0, lastOpen = null, m;
      while ((m = spanRe.exec(line))) {
        if (m[0] === "</span>") depth--;
        else { depth++; lastOpen = m[0]; }
      }
      if (depth > 0) {
        line += "</span>";
        openTag = lastOpen;
      } else {
        openTag = null;
      }
      var num = String(idx + 1).padStart(width, " ");
      var lineNo = idx + 1;
      var mark = markers && markers[lineNo];
      var cls = "xml-line" + (mark ? " xml-line-" + mark : "");
      var attr = mark ? ' data-issue="' + mark + '"' : "";
      return '<div class="' + cls + '"' + attr + '><span class="xml-lineno">' + num + '</span>' +
             '<span class="xml-lnbody">' + (line === "" ? " " : line) + '</span></div>';
    });
    return rows.join("");
  }

  global.AtdlHighlight = {
    highlight: highlight,
    renderWithLineNumbers: renderWithLineNumbers
  };
})(window);
