"""Phase 1 — structural XSD validation via lxml."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from .models import ValidationError


def run(
    xml_path: str | Path,
    schema_path: str | Path,
) -> list[ValidationError]:
    """Validate *xml_path* against the ATDL XSD schema.

    Returns:
        List of :class:`ValidationError` instances.  Empty list = valid.
    """
    xml_path = Path(xml_path)
    schema_path = Path(schema_path)

    schema_doc = etree.parse(str(schema_path))
    schema = etree.XMLSchema(schema_doc)

    xml_doc = etree.parse(str(xml_path))
    schema.validate(xml_doc)

    errors: list[ValidationError] = []
    for entry in schema.error_log:
        errors.append(
            ValidationError(
                phase=1,
                rule_id="XSD",
                message=entry.message,
                element=entry.path or None,
                line=entry.line or None,
            )
        )
    return errors
