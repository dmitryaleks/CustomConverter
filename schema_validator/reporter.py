"""Format and emit validation results."""

from __future__ import annotations

import json

from .models import ValidationError, ValidationResult


def format_text(result: ValidationResult, include_warnings: bool = False) -> str:
    """Return a human-readable report, one line per issue."""
    lines: list[str] = []

    for err in result.errors:
        loc = f" (line {err.line})" if err.line else ""
        lines.append(f"[Phase {err.phase}] [{err.rule_id}] ERROR{loc}: {err.message}")

    if include_warnings:
        for warn in result.warnings:
            loc = f" (line {warn.line})" if warn.line else ""
            lines.append(f"[Phase {warn.phase}] [{warn.rule_id}] WARNING{loc}: {warn.message}")

    if not lines:
        lines.append("Validation passed — no errors found.")

    return "\n".join(lines)


def _error_to_dict(err: ValidationError, severity: str) -> dict:
    d: dict = {
        "severity": severity,
        "phase": err.phase,
        "rule_id": err.rule_id,
        "message": err.message,
    }
    if err.element is not None:
        d["element"] = err.element
    if err.line is not None:
        d["line"] = err.line
    return d


def format_json(result: ValidationResult, include_warnings: bool = False) -> str:
    """Return a JSON array of all issues."""
    items = [_error_to_dict(e, "error") for e in result.errors]
    if include_warnings:
        items += [_error_to_dict(w, "warning") for w in result.warnings]
    return json.dumps(items, indent=2)
