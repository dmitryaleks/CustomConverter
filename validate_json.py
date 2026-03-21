"""validate_json.py — ATDL JSON algo descriptor validator CLI.

Usage::

    python validate_json.py FILE [OPTIONS]

Exit codes:
    0  No errors found (file is valid)
    1  One or more validation errors found
    2  File not found or invalid JSON
"""

import argparse
import json
import sys
from pathlib import Path

from converter.json_validator import validate_json, ValidationIssue


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Validate a proprietary ATDL JSON algo descriptor file.",
    )
    p.add_argument(
        "file",
        type=Path,
        metavar="FILE",
        help="Path to the JSON file to validate",
    )
    p.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        dest="output_format",
        help="Output format: text or json (default: text)",
    )
    p.add_argument(
        "--warnings",
        action="store_true",
        help="Include warnings in output (default: errors only)",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress all output; use exit code only",
    )
    return p


def _format_text(issues: list[ValidationIssue], include_warnings: bool) -> str:
    lines: list[str] = []
    for issue in issues:
        if issue.severity == "warning" and not include_warnings:
            continue
        sev = issue.severity.upper()
        path = f" ({issue.path})" if issue.path else ""
        lines.append(f"[{issue.rule_id}] {sev}{path}: {issue.message}")
    if not lines:
        return "Validation passed — no errors found."
    return "\n".join(lines)


def _format_json_output(issues: list[ValidationIssue], include_warnings: bool) -> str:
    items = []
    for issue in issues:
        if issue.severity == "warning" and not include_warnings:
            continue
        items.append({
            "severity": issue.severity,
            "rule_id": issue.rule_id,
            "message": issue.message,
            "path": issue.path,
        })
    return json.dumps(items, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        issues = validate_json(args.file)
    except FileNotFoundError as exc:
        if not args.quiet:
            print(f"Error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        if not args.quiet:
            print(f"Error: {exc}", file=sys.stderr)
        return 2

    errors = [i for i in issues if i.severity == "error"]

    if not args.quiet:
        if args.output_format == "json":
            print(_format_json_output(issues, args.warnings))
        else:
            print(_format_text(issues, args.warnings))

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
