"""Inline the 6 bundled XSD files into alternativeRenderer/schemas-embedded.js.

Lets the renderer do XSD-driven validation from file:// (where fetch() is
blocked by Chrome) without any change to xsd-validator.js. Regenerate
after editing anything under schemas/.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SCHEMAS = HERE / "schemas"
OUT = HERE / "schemas-embedded.js"

FILES = [
    "fixatdl-core-1-1.xsd",
    "fixatdl-layout-1-1.xsd",
    "fixatdl-flow-1-1.xsd",
    "fixatdl-validation-1-1.xsd",
    "fixatdl-regions-1-1.xsd",
    "fixatdl-timezones-1-1.xsd",
]


def main() -> int:
    data = {}
    for name in FILES:
        p = SCHEMAS / name
        if not p.is_file():
            print(f"missing: {p}", file=sys.stderr)
            return 1
        data[name] = p.read_text(encoding="utf-8")

    body = json.dumps(data, indent=2, ensure_ascii=False)
    out = (
        "/* Auto-generated from schemas/*.xsd by tools/embed_schemas.py. */\n"
        "/* eslint-disable */\n"
        "window.ATDL_EMBEDDED_XSDS = " + body + ";\n"
    )
    OUT.write_text(out, encoding="utf-8")
    size = OUT.stat().st_size
    print(f"wrote {OUT.name} ({size:,} bytes, {len(data)} schemas)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
