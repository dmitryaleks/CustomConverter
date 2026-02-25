"""Build FIXATDL 1.1 XML from the internal data model using lxml."""

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

from .parser import AlgoDef, ParameterDef

# Namespaces
CORE_NS = "http://www.fixprotocol.org/ATDL-1-1/Core"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

NSMAP = {
    None: CORE_NS,          # default namespace
    "xsi": XSI_NS,
    "core": CORE_NS,
}

_VALID_ENUM_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,255}$")


def _sanitize_enum_id(value: str) -> str:
    """Return a schema-valid enumID for a wireValue.

    EnumPair@enumID must match [A-Za-z][A-Za-z0-9_]{0,255}.
    If the value already matches, return it unchanged.
    Otherwise prefix with 'e_' and replace invalid chars with '_'.
    """
    if _VALID_ENUM_ID.match(value):
        return value
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not sanitized or not sanitized[0].isalpha():
        sanitized = "e_" + sanitized
    return sanitized[:256]


def _qname(local: str) -> str:
    return f"{{{CORE_NS}}}{local}"


def build_fixatdl(
    algo: AlgoDef,
    provider_id: str = "CustomProvider",
    strategy_version: str = "1",
    strategy_identifier_tag: int = 847,
) -> etree._Element:
    """Build a FIXATDL lxml element tree from an AlgoDef.

    Args:
        algo: Parsed algorithm definition.
        provider_id: Value for Strategy@providerID.
        strategy_version: Value for Strategy@version.
        strategy_identifier_tag: Value for Strategies@strategyIdentifierTag
            (FIX tag used to identify the algorithm, e.g. 847 = TargetStrategy).

    Returns:
        The root ``<Strategies>`` lxml element.
    """
    root = etree.Element(_qname("Strategies"), nsmap=NSMAP)
    root.set("strategyIdentifierTag", str(strategy_identifier_tag))
    root.set(
        f"{{{XSI_NS}}}schemaLocation",
        f"{CORE_NS} schemas/atdl-core-1-1.xsd",
    )

    strategy = etree.SubElement(root, _qname("Strategy"))
    strategy.set("name", algo.name)
    strategy.set("uiRep", algo.name)
    strategy.set("wireValue", algo.name)
    strategy.set("fixMsgType", "D")
    strategy.set("providerID", provider_id)
    strategy.set("version", strategy_version)

    for param in algo.parameters:
        _add_parameter(strategy, param)

    return root


def _add_parameter(parent: etree._Element, param: ParameterDef) -> None:
    """Append a ``<Parameter>`` element (with optional EnumPairs) to *parent*."""
    # Prepend a comment with the description if one was provided
    if param.description:
        parent.append(etree.Comment(f" {param.name}: {param.description} "))

    elem = etree.SubElement(parent, _qname("Parameter"))
    elem.set("name", param.name)
    # xsi:type references a concrete type from the core namespace
    elem.set(f"{{{XSI_NS}}}type", f"core:{param.type}")
    elem.set("fixTag", str(param.fix_tag))
    elem.set("mutableOnCxlRpl", "true")

    for wire_value in param.supported_values:
        enum_id = _sanitize_enum_id(wire_value)
        enum_pair = etree.SubElement(elem, _qname("EnumPair"))
        enum_pair.set("enumID", enum_id)
        enum_pair.set("wireValue", wire_value)


def write_fixatdl(root: etree._Element, output_path: str | Path) -> None:
    """Serialise *root* to *output_path* as pretty-printed UTF-8 XML."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    xml_bytes = etree.tostring(
        root,
        pretty_print=True,
        xml_declaration=True,
        encoding="UTF-8",
    )
    output_path.write_bytes(xml_bytes)
