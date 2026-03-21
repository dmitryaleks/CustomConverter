"""TypeMapper — translate source type vocabulary → FIXATDL 1.1 types.

Usage::

    from source_converter.type_mapper import TypeMapper

    mapper = TypeMapper()
    fixatdl_type = mapper.map("price")   # → "Price_t"
    unknown       = mapper.map("Widget") # → None
    report        = mapper.coverage_report()
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

_HERE = Path(__file__).parent
DEFAULT_TYPE_MAP = _HERE / "type_map.toml"


def _load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file using stdlib tomllib (3.11+) or tomli fallback."""
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            raise ImportError(
                "tomllib (stdlib) or tomli package required to read type_map.toml"
            )
    with path.open("rb") as fh:
        return tomllib.load(fh)


class TypeMapper:
    """Map source type names to FIXATDL 1.1 parameter types.

    The mapping is loaded from a TOML config file (default:
    ``source_converter/type_map.toml``).  All lookups are case-insensitive.
    Every lookup is recorded so that :meth:`coverage_report` can show which
    source types have no mapping.

    Args:
        config_path: Path to the TOML mapping file.  Defaults to the
            ``type_map.toml`` bundled with this package.

    Raises:
        FileNotFoundError: if *config_path* does not exist.
    """

    def __init__(self, config_path: str | Path = DEFAULT_TYPE_MAP) -> None:
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Type map config not found: {config_path}")
        data = _load_toml(config_path)
        raw: dict[str, str] = data.get("types", {})
        # Normalise keys to lowercase for case-insensitive lookup
        self._mapping: dict[str, str] = {k.lower(): v for k, v in raw.items()}
        # Track all lookups: source_key_lowercase → set of original forms seen
        self._seen_mapped: dict[str, str] = {}       # source_lower → fixatdl
        self._seen_unmapped: list[str] = []           # source strings with no mapping
        self._total_lookups: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def map(self, source_type: str) -> str | None:
        """Return the FIXATDL type for *source_type*, or ``None`` if unmapped.

        The lookup is case-insensitive.  Each call is recorded for coverage
        reporting.

        Args:
            source_type: A type name from the source vocabulary.

        Returns:
            The corresponding FIXATDL 1.1 type string (e.g. ``"Price_t"``)
            or ``None`` if no mapping exists.
        """
        self._total_lookups += 1
        key = source_type.lower()
        result = self._mapping.get(key)
        if result is not None:
            self._seen_mapped[source_type] = result
        else:
            self._seen_unmapped.append(source_type)
        return result

    def coverage_report(self) -> dict:
        """Return a coverage summary of all lookups performed so far.

        Returns:
            A dict with keys:

            ``mapped``
                List of ``{"source": str, "fixatdl": str}`` dicts for every
                source type that was successfully mapped.

            ``unmapped``
                List of source type strings that had no mapping.

            ``total_lookups``
                Total number of :meth:`map` calls made.
        """
        mapped = [
            {"source": src, "fixatdl": fixatdl}
            for src, fixatdl in self._seen_mapped.items()
        ]
        return {
            "mapped": mapped,
            "unmapped": list(self._seen_unmapped),
            "total_lookups": self._total_lookups,
        }

    # ------------------------------------------------------------------
    # Introspection helpers (used by reporter)
    # ------------------------------------------------------------------

    @property
    def all_entries(self) -> dict[str, str]:
        """All configured mappings (lowercase source → FIXATDL type)."""
        return dict(self._mapping)
