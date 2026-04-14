"""DSL parser — converts a proprietary XML-based DSL to an :class:`~converter.parser.AlgoDef`.

The mapping between DSL XML structure and internal field names is driven by
``field_map.toml`` (default: the copy bundled alongside this module).

Public API
----------
parse_dsl(path, ...)                 → AlgoDef
parse_dsl_with_coverage(path, ...)   → tuple[AlgoDef, FieldCoverage]
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree

from converter.parser import AlgoDef, EnumValue, ParameterDef
from source_converter.transformers import pad_time, normalize_boolean, strip_percent

if TYPE_CHECKING:
    from source_converter.type_mapper import TypeMapper

DEFAULT_FIELD_MAP = Path(__file__).parent / "field_map.toml"

# ---------------------------------------------------------------------------
# Auto-transform registry keyed by FIXATDL type
# ---------------------------------------------------------------------------

_TIME_TYPES    = frozenset({"UTCTimeOnly_t", "LocalMktTime_t"})
_BOOL_TYPES    = frozenset({"Boolean_t"})
_PERCENT_TYPES = frozenset({"Percentage_t"})


def _auto_transform(value: str, fixatdl_type: str) -> str:
    """Apply the canonical transformer for the given FIXATDL type."""
    if fixatdl_type in _TIME_TYPES:
        return pad_time(value)
    if fixatdl_type in _BOOL_TYPES:
        return normalize_boolean(value)
    if fixatdl_type in _PERCENT_TYPES:
        return strip_percent(value)
    return value


# ---------------------------------------------------------------------------
# FieldCoverage dataclass
# ---------------------------------------------------------------------------

@dataclass
class FieldCoverage:
    """Reports which DSL fields were mapped, dropped, or missing."""

    mapped:  list[dict] = field(default_factory=list)
    """Each entry: {"dsl_attr": str, "internal_field": str, "value": str}"""

    dropped: list[str] = field(default_factory=list)
    """DSL attributes present but not in field_map."""

    missing: list[str] = field(default_factory=list)
    """field_map entries that found no data in any parameter element."""


# ---------------------------------------------------------------------------
# Namespace-transparent helpers
# ---------------------------------------------------------------------------

def _local(tag: str) -> str:
    """Strip the Clark-notation namespace prefix: '{ns}elem' → 'elem'."""
    return tag.split("}")[-1] if "}" in tag else tag


def _child_by_local(elem, name: str):
    """Return the first direct child whose local name equals *name*, or None."""
    for child in elem:
        if _local(child.tag) == name:
            return child
    return None


def _children_by_local(elem, name: str):
    """Yield all direct children whose local name equals *name*."""
    for child in elem:
        if _local(child.tag) == name:
            yield child


# ---------------------------------------------------------------------------
# FieldMap
# ---------------------------------------------------------------------------

class FieldMap:
    """Loads ``field_map.toml`` and resolves field expressions against XML elements."""

    def __init__(self, path: str | Path = DEFAULT_FIELD_MAP) -> None:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"field_map not found: {path}")
        with path.open("rb") as fh:
            cfg = tomllib.load(fh)

        self._strategy_name_expr: str = cfg["strategy"]["name"]
        self._param_container: str    = cfg["parameters"]["container"]
        self._param_element: str      = cfg["parameters"]["element"]
        self._field_expressions: dict[str, str] = dict(cfg["fields"])
        self._sv_container: str = cfg["supported_values"]["container"]
        self._sv_item: str      = cfg["supported_values"]["item"]

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def strategy_name_expr(self) -> str:
        return self._strategy_name_expr

    @property
    def param_container(self) -> str:
        return self._param_container

    @property
    def param_element(self) -> str:
        return self._param_element

    @property
    def field_expressions(self) -> dict[str, str]:
        return self._field_expressions

    @property
    def sv_container(self) -> str:
        return self._sv_container

    @property
    def sv_item(self) -> str:
        return self._sv_item

    # ── Resolution ──────────────────────────────────────────────────────────

    def resolve(self, elem, expression: str) -> str | None:
        """Resolve *expression* against *elem*, returning the value or None.

        Expression forms:
          ``"@attr"``           — attribute on *elem*
          ``"ChildElem"``       — text content of a direct child element
          ``"ChildElem/@attr"`` — attribute on a named direct child
        """
        if expression.startswith("@"):
            return elem.get(expression[1:]) or None

        if "/@" in expression:
            child_name, _, attr_name = expression.partition("/@")
            child = _child_by_local(elem, child_name)
            if child is None:
                return None
            return child.get(attr_name) or None

        # Plain child element → text content
        child = _child_by_local(elem, expression)
        if child is None:
            return None
        return (child.text or "").strip() or None

    # ── Strategy name ───────────────────────────────────────────────────────

    def resolve_strategy_name(self, root) -> str | None:
        """Extract the strategy name from the root element."""
        expr = self._strategy_name_expr
        if expr.startswith("attribute:"):
            return root.get(expr[len("attribute:"):]) or None
        if expr.startswith("element:"):
            child = _child_by_local(root, expr[len("element:"):])
            return (child.text or "").strip() or None if child is not None else None
        return None


# ---------------------------------------------------------------------------
# Core implementation
# ---------------------------------------------------------------------------

def _parse_dsl_impl(
    path: str | Path,
    field_map_path: str | Path,
    type_mapper: "TypeMapper | None",
) -> tuple[AlgoDef, FieldCoverage]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"DSL file not found: {path}")

    try:
        tree = etree.parse(str(path))
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"Malformed XML in '{path}': {exc}") from exc

    root = tree.getroot()
    fm = FieldMap(field_map_path)

    # ── Strategy name ───────────────────────────────────────────────────────
    algo_name = fm.resolve_strategy_name(root)
    if not algo_name:
        raise ValueError(f"Could not determine strategy name from '{path}'")

    # ── Locate parameter container ──────────────────────────────────────────
    container = _child_by_local(root, fm.param_container)
    if container is None:
        raise ValueError(
            f"Missing <{fm.param_container}> element in '{path}'"
        )

    # ── Parse parameters ────────────────────────────────────────────────────
    parameters: list[ParameterDef] = []
    coverage_mapped: list[dict] = []
    coverage_dropped_set: set[str] = set()
    coverage_seen_fields: set[str] = set()

    required_fields = {"name", "type", "fix_tag"}

    # Resolve the effective type mapper once, outside the loop
    if type_mapper is None:
        from source_converter.type_mapper import TypeMapper
        type_mapper = TypeMapper()

    # Pre-compute the set of DSL attributes covered by field_map expressions
    mapped_attrs = {expr[1:] for expr in fm.field_expressions.values()
                    if expr.startswith("@")}

    for param_elem in _children_by_local(container, fm.param_element):
        resolved: dict[str, str | None] = {}

        # Resolve each field expression
        for internal_field, expr in fm.field_expressions.items():
            value = fm.resolve(param_elem, expr)
            resolved[internal_field] = value
            if value is not None:
                coverage_seen_fields.add(internal_field)
                coverage_mapped.append({
                    "dsl_attr": expr,
                    "internal_field": internal_field,
                    "value": value,
                })

        # Validate required fields
        for rf in required_fields:
            if not resolved.get(rf):
                raise ValueError(
                    f"Parameter in '{path}' is missing required field '{rf}'"
                )

        # Type mapping
        raw_type: str = resolved["type"]  # type: ignore[assignment]
        mapped = type_mapper.map(raw_type)
        fixatdl_type = mapped if mapped is not None else raw_type

        # fix_tag → int
        try:
            fix_tag = int(resolved["fix_tag"])  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Parameter '{resolved['name']}' has non-integer fix_tag "
                f"'{resolved['fix_tag']}'"
            ) from exc

        # Default value with auto-transform
        default_value: str | None = resolved.get("default_value")
        if default_value is not None:
            default_value = _auto_transform(default_value, fixatdl_type)

        # Supported values (enum list)
        sv_container = _child_by_local(param_elem, fm.sv_container)
        supported_values: list[EnumValue] = []
        if sv_container is not None:
            for item in _children_by_local(sv_container, fm.sv_item):
                text = (item.text or "").strip()
                if text:
                    supported_values.append(EnumValue(value=text))

        # Collect any DSL attributes not covered by field_map
        coverage_dropped_set.update(set(param_elem.attrib.keys()) - mapped_attrs)

        parameters.append(
            ParameterDef(
                name=resolved["name"],  # type: ignore[arg-type]
                description=resolved.get("description") or "",
                type=fixatdl_type,
                fix_tag=fix_tag,
                supported_values=supported_values,
                default_value=default_value,
                min_value=resolved.get("min_value"),
                max_value=resolved.get("max_value"),
                increment=resolved.get("increment"),
            )
        )

    # ── Coverage: missing fields ─────────────────────────────────────────────
    all_optional = set(fm.field_expressions.keys()) - required_fields
    coverage_missing = sorted(all_optional - coverage_seen_fields)

    coverage = FieldCoverage(
        mapped=coverage_mapped,
        dropped=sorted(coverage_dropped_set),
        missing=coverage_missing,
    )

    return AlgoDef(name=algo_name, parameters=parameters), coverage


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_dsl(
    path: str | Path,
    field_map_path: str | Path = DEFAULT_FIELD_MAP,
    type_mapper: "TypeMapper | None" = None,
) -> AlgoDef:
    """Parse a DSL XML file and return an :class:`~converter.parser.AlgoDef`.

    Args:
        path: Path to the DSL XML file.
        field_map_path: Path to the TOML field-map config. Defaults to the
            bundled ``field_map.toml``.
        type_mapper: Optional :class:`~source_converter.type_mapper.TypeMapper`
            instance. When ``None``, the default ``TypeMapper()`` is used.

    Returns:
        An :class:`~converter.parser.AlgoDef` ready for the builder pipeline.

    Raises:
        FileNotFoundError: If *path* or *field_map_path* does not exist.
        ValueError: If the XML is malformed or required fields are absent.
    """
    algo, _ = _parse_dsl_impl(path, field_map_path, type_mapper)
    return algo


def parse_dsl_with_coverage(
    path: str | Path,
    field_map_path: str | Path = DEFAULT_FIELD_MAP,
    type_mapper: "TypeMapper | None" = None,
) -> tuple[AlgoDef, FieldCoverage]:
    """Parse a DSL XML file and return both the algo and field-coverage data.

    Args:
        path: Path to the DSL XML file.
        field_map_path: Path to the TOML field-map config.
        type_mapper: Optional :class:`~source_converter.type_mapper.TypeMapper`.

    Returns:
        A ``(AlgoDef, FieldCoverage)`` tuple.
    """
    return _parse_dsl_impl(path, field_map_path, type_mapper)
