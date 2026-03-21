"""CustomConverter CLI — converts a proprietary ATDL JSON or XML DSL to FIXATDL 1.1 XML.

Usage::

    python main.py input.json or input.xml output.xml [--validate]
                   [--provider-id ID] [--strategy-version VER]
                   [--strategy-identifier-tag TAG]

Exit codes:
    0  Success (and validation passed when --validate is used)
    1  Validation errors
    2  Input / conversion errors
"""

import argparse
import sys
from pathlib import Path

from converter.parser import parse_json
from converter.builder import build_fixatdl, write_fixatdl

_DEFAULT_SCHEMA = Path(__file__).parent / "schemas" / "atdl-core-1-1.xsd"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Convert proprietary ATDL JSON to FIXATDL 1.1 XML.",
    )
    p.add_argument("input", type=Path, help="Path to the input JSON or XML DSL file")
    p.add_argument("output", type=Path, help="Path for the output XML file")
    p.add_argument(
        "--validate",
        action="store_true",
        help="Validate the output XML against the FIXATDL 1.1 XSD schema",
    )
    p.add_argument(
        "--provider-id",
        default="CustomProvider",
        metavar="ID",
        help="Value for Strategy@providerID (default: CustomProvider)",
    )
    p.add_argument(
        "--strategy-version",
        default="1",
        metavar="VER",
        help="Value for Strategy@version (default: 1)",
    )
    p.add_argument(
        "--strategy-identifier-tag",
        type=int,
        default=847,
        metavar="TAG",
        help=(
            "FIX tag number used to identify the algorithm "
            "(Strategies@strategyIdentifierTag, default: 847)"
        ),
    )
    p.add_argument(
        "--schema",
        type=Path,
        default=_DEFAULT_SCHEMA,
        metavar="XSD",
        help=f"Path to the FIXATDL XSD schema (default: {_DEFAULT_SCHEMA})",
    )
    p.add_argument(
        "--html",
        type=Path,
        metavar="HTML",
        help="Render ATDL strategies to a self-contained HTML file",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # --- Parse input (JSON or XML DSL) ---
    try:
        if args.input.suffix.lower() == ".xml":
            from source_converter.dsl_parser import parse_dsl
            algo = parse_dsl(args.input)
        else:
            algo = parse_json(args.input)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    # --- Build XML ---
    root = build_fixatdl(
        algo,
        provider_id=args.provider_id,
        strategy_version=args.strategy_version,
        strategy_identifier_tag=args.strategy_identifier_tag,
    )

    # --- Write output ---
    try:
        write_fixatdl(root, args.output)
    except OSError as exc:
        print(f"Error writing output: {exc}", file=sys.stderr)
        return 2

    # --- Optional HTML render ---
    if args.html:
        from converter.renderer import write_html
        try:
            write_html(root, args.html)
        except OSError as exc:
            print(f"Error writing HTML output: {exc}", file=sys.stderr)
            return 2

    # --- Optional validation ---
    if args.validate:
        from converter.validator import validate

        try:
            errors = validate(args.output, args.schema)
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

        if errors:
            for msg in errors:
                print(f"Validation error: {msg}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
