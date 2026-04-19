"""Ground-truth XSD validation for the sample ATDL files.

Uses lxml's built-in XSD 1.0 validator to validate each sample under
alternativeRenderer/sample/ against the bundled schemas. This is the
reference the JS xsd-validator.js should approximate.
"""
from __future__ import annotations
import sys
from pathlib import Path
from lxml import etree

HERE = Path(__file__).resolve().parent.parent
SCHEMAS = HERE / "schemas"
SAMPLES = HERE / "sample"

ROOT_XSD = SCHEMAS / "atdl-core-1-1.xsd"


def build_schema() -> etree.XMLSchema:
    parser = etree.XMLParser()
    tree = etree.parse(str(ROOT_XSD), parser)
    # lxml auto-resolves xs:import schemaLocation= siblings in same dir
    return etree.XMLSchema(tree)


def validate_file(schema: etree.XMLSchema, path: Path) -> list[str]:
    try:
        doc = etree.parse(str(path))
    except etree.XMLSyntaxError as e:
        return [f"XML syntax error: {e}"]
    if schema.validate(doc):
        return []
    return [f"line {e.line}: {e.message}" for e in schema.error_log]


def main() -> int:
    schema = build_schema()
    print(f"Schema OK: {ROOT_XSD.name}\n")
    total = 0
    for xml in sorted(SAMPLES.glob("*.xml")):
        errs = validate_file(schema, xml)
        print(f"=== {xml.name} — {len(errs)} error(s) ===")
        for e in errs[:20]:
            print(f"  {e}")
        if len(errs) > 20:
            print(f"  ... ({len(errs) - 20} more)")
        print()
        total += len(errs)
    print(f"Total errors across samples: {total}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
