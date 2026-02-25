"""validate_schema.py — multi-phase ATDL schema validator CLI.

Usage::

    python validate_schema.py FILE [OPTIONS]

Exit codes:
    0  All selected phases passed
    1  One or more validation errors found
    2  Usage / file I/O error
"""

import argparse
import sys
from pathlib import Path

from schema_validator.runner import validate
from schema_validator.reporter import format_text, format_json

_DEFAULT_SCHEMA = Path(__file__).parent / "schemas" / "atdl-core-1-1.xsd"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Validate an ATDL 1.1 XML document (structural + referential + semantic).",
    )
    p.add_argument("file", type=Path, metavar="FILE",
                   help="Path to the ATDL XML document to validate")
    p.add_argument("--schema", type=Path, default=_DEFAULT_SCHEMA, metavar="XSD",
                   help=f"Path to atdl-core-1-1.xsd (default: {_DEFAULT_SCHEMA})")
    p.add_argument("--phases", default="1,2,3", metavar="PHASES",
                   help="Comma-separated phases to run: 1, 2, 3 (default: 1,2,3)")
    p.add_argument("--format", choices=["text", "json"], default="text",
                   dest="output_format",
                   help="Output format: text or json (default: text)")
    p.add_argument("--warnings", action="store_true",
                   help="Include warnings in output (default: errors only)")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress all output; use exit code only")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Parse phases
    try:
        phases = tuple(int(p.strip()) for p in args.phases.split(","))
    except ValueError:
        print(f"Error: invalid --phases value '{args.phases}'", file=sys.stderr)
        return 2

    if not args.file.exists():
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 2
    if not args.schema.exists():
        print(f"Error: schema not found: {args.schema}", file=sys.stderr)
        return 2

    try:
        result = validate(args.file, args.schema, phases=phases)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        if args.output_format == "json":
            print(format_json(result, include_warnings=args.warnings))
        else:
            print(format_text(result, include_warnings=args.warnings))

    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
