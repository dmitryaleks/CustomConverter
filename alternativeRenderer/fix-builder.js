/* fix-builder.js — assemble a FIX 4.2 message preview from form values. */
(function (global) {
  "use strict";

  function pad2(n) { return n < 10 ? "0" + n : String(n); }

  function timestampUTC() {
    var d = new Date();
    return d.getUTCFullYear() + pad2(d.getUTCMonth() + 1) + pad2(d.getUTCDate())
         + "-" + pad2(d.getUTCHours()) + ":" + pad2(d.getUTCMinutes()) + ":" + pad2(d.getUTCSeconds());
  }

  /* values: ordered array of {tag, value} pairs (excluding header/checksum). */
  function build(strategy, values) {
    var SOH = "\x01";
    var bodyParts = [
      "35=" + (strategy.fixMsgType || "D"),
      "49=" + (strategy.providerID || "PROVIDER"),
      "56=BROKER",
      "34=1",
      "52=" + timestampUTC()
    ];
    /* StrategyName as TargetStrategy (847) by default unless explicitly overridden. */
    var sit = strategy.strategyIdentifierTag || "847";
    bodyParts.push(sit + "=" + (strategy.wireValue || strategy.name));
    values.forEach(function (kv) {
      if (kv.value === null || kv.value === undefined) return;
      var s = String(kv.value);
      if (s === "") return;
      bodyParts.push(kv.tag + "=" + s);
    });
    var bodyStr = bodyParts.join(SOH) + SOH;
    var header = "8=FIX.4.2" + SOH + "9=" + bodyStr.length + SOH;
    var raw = header + bodyStr;
    var cs = 0;
    for (var i = 0; i < raw.length; i++) cs += raw.charCodeAt(i);
    raw += "10=" + ("00" + (cs % 256)).slice(-3) + SOH;
    return raw;
  }

  global.AtdlFix = { build: build };
})(window);
