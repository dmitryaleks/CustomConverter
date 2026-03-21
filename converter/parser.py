"""Parse proprietary ATDL JSON into internal data model."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParameterDef:
    name: str
    description: str
    type: str                    # FIX type string, e.g. "String_t"
    fix_tag: int
    supported_values: list[str] = field(default_factory=list)
    default_value: str | None = None


@dataclass
class AlgoDef:
    name: str
    parameters: list[ParameterDef] = field(default_factory=list)


def parse_json(path: str | Path) -> AlgoDef:
    """Load a JSON file and return an AlgoDef.

    Expected structure::

        {
          "AlgoName": {
            "PARAMETERS": [
              { "PARAM_KEY": {
                  "NAME": "...",
                  "DESCRIPTION": "...",
                  "TYPE": "String_t",
                  "FIXTAGNUMBER": 5001,
                  "SUPPORTED_VALUES": ["A", "B"],
                  "DEFAULT_VALUE": "A"
                }
              }
            ]
          }
        }
    """
    path = Path(path)
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise FileNotFoundError(f"Input file not found: {path}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(data, dict) or len(data) != 1:
        raise ValueError(
            "JSON must have exactly one top-level key (the algo name)"
        )

    algo_name, algo_body = next(iter(data.items()))

    if not isinstance(algo_body, dict) or "PARAMETERS" not in algo_body:
        raise ValueError(
            f"Algo '{algo_name}' must have a 'PARAMETERS' key"
        )

    params_raw = algo_body["PARAMETERS"]
    if not isinstance(params_raw, list):
        raise ValueError(
            f"'PARAMETERS' for algo '{algo_name}' must be a list"
        )

    parameters: list[ParameterDef] = []
    for idx, item in enumerate(params_raw):
        if not isinstance(item, dict) or len(item) != 1:
            raise ValueError(
                f"Each PARAMETERS entry must be a single-key dict (entry {idx})"
            )
        _param_key, param_body = next(iter(item.items()))

        for required in ("NAME", "TYPE", "FIXTAGNUMBER"):
            if required not in param_body:
                raise ValueError(
                    f"Parameter entry {idx} is missing required field '{required}'"
                )

        parameters.append(
            ParameterDef(
                name=param_body["NAME"],
                description=param_body.get("DESCRIPTION", ""),
                type=param_body["TYPE"],
                fix_tag=int(param_body["FIXTAGNUMBER"]),
                supported_values=list(param_body.get("SUPPORTED_VALUES") or []),
                default_value=param_body.get("DEFAULT_VALUE") or None,
            )
        )

    return AlgoDef(name=algo_name, parameters=parameters)
