"""dsl_to_json — serialise a parsed DSL algo back to the proprietary JSON format.

The proprietary JSON format is the intermediate representation consumed by
``converter.parser.parse_json`` and expected by the rest of the pipeline.  It
looks like::

    {
      "ALGO_NAME": {
        "PARAMETERS": [
          {
            "ParamName": {
              "NAME": "ParamName",
              "DESCRIPTION": "...",
              "TYPE": "UTCTimeOnly_t",
              "FIXTAGNUMBER": 7001,
              "DEFAULT_VALUE": "09:30:00",      // optional
              "SUPPORTED_VALUES": [             // optional
                {"VALUE": "A", "DESCRIPTION": ""},
                {"VALUE": "B", "DESCRIPTION": ""}
              ]
            }
          }
        ]
      }
    }

Public API
----------
algo_to_dict(algo)              → dict  (in-memory)
dsl_to_json(dsl_path, out_path) → str   (also writes file when out_path given)
"""

from __future__ import annotations

import json
from pathlib import Path

from converter.parser import AlgoDef, ParameterDef


def algo_to_dict(algo: AlgoDef) -> dict:
    """Serialise an :class:`~converter.parser.AlgoDef` to the proprietary JSON dict.

    The parameter key inside each PARAMETERS entry matches the NAME value
    (PascalCase), consistent with the sample_strategies convention.
    """
    params: list[dict] = []
    for p in algo.parameters:
        body: dict = {
            "NAME": p.name,
            "DESCRIPTION": p.description,
            "TYPE": p.type,
            "FIXTAGNUMBER": p.fix_tag,
        }
        if p.supported_values:
            body["SUPPORTED_VALUES"] = [
                {"VALUE": ev.value, "DESCRIPTION": ev.description}
                for ev in p.supported_values
            ]
        if p.default_value is not None:
            body["DEFAULT_VALUE"] = p.default_value
        if p.min_value is not None:
            body["MIN_VALUE"] = p.min_value
        if p.max_value is not None:
            body["MAX_VALUE"] = p.max_value
        if p.increment is not None:
            body["INCREMENT"] = p.increment
        params.append({p.name: body})

    return {algo.name: {"PARAMETERS": params}}


def dsl_to_json(
    dsl_path: str | Path,
    output_path: str | Path | None = None,
    *,
    field_map_path: str | Path | None = None,
    indent: int = 2,
) -> str:
    """Parse a DSL XML file and return the proprietary JSON string.

    Args:
        dsl_path: Path to the DSL XML source file.
        output_path: When provided, also write the JSON to this path.
        field_map_path: Custom field-map TOML path; defaults to bundled config.
        indent: JSON indentation (default 2).

    Returns:
        The JSON string.
    """
    from source_converter.dsl_parser import parse_dsl, DEFAULT_FIELD_MAP

    kwargs = {}
    if field_map_path is not None:
        kwargs["field_map_path"] = field_map_path

    algo = parse_dsl(dsl_path, **kwargs)
    data = algo_to_dict(algo)
    json_str = json.dumps(data, indent=indent)

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json_str + "\n", encoding="utf-8")

    return json_str
