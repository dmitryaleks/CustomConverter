"""Validate FIXATDL XML against the official ATDL 1.1 XSD schema."""

from __future__ import annotations

from pathlib import Path

from lxml import etree


def validate(
    xml_path: str | Path,
    schema_path: str | Path,
) -> list[str]:
    """Validate *xml_path* against *schema_path*.

    Returns:
        A list of error message strings.  An empty list means the document
        is valid.

    Raises:
        FileNotFoundError: if either file does not exist.
        lxml.etree.XMLSyntaxError: if the XML or XSD is malformed.
    """
    xml_path = Path(xml_path)
    schema_path = Path(schema_path)

    if not xml_path.exists():
        raise FileNotFoundError(f"XML file not found: {xml_path}")
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    schema_doc = etree.parse(str(schema_path))
    schema = etree.XMLSchema(schema_doc)

    xml_doc = etree.parse(str(xml_path))
    schema.validate(xml_doc)

    return [str(err.message) for err in schema.error_log]
