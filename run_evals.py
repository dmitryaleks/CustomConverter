"""run_evals.py — batch evaluation runner for converted JSON algo descriptors.

Validates every JSON file in JSONDIR end-to-end (JSON schema checks → FIXATDL
XML conversion → XSD + semantic validation) and prints structured reports.

Usage::

    python run_evals.py JSONDIR [OPTIONS]

    Options:
      --baseline FILE    Previous results JSON for diff/changelog output
      --output FILE      Persist results to this JSON file
      --format text|json Output format (default: text)
      --warnings         Include warnings in reports

Exit codes:
    0  All files passed
    1  One or more files failed
    2  Usage / I/O error
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from lxml import etree

from converter.json_validator import validate_json
from converter.parser import parse_json
from converter.builder import build_fixatdl
from schema_validator.runner import validate as schema_validate
from source_converter.type_mapper import TypeMapper
from source_converter.dsl_parser import parse_dsl
from source_converter.reporter import (
    format_dashboard,
    format_type_report,
    format_coverage,
    format_diff,
)

_DEFAULT_SCHEMA = Path(__file__).parent / "schemas" / "atdl-core-1-1.xsd"


# ─────────────────────────────────────────────────────────────────────────────
# Per-file evaluation
# ─────────────────────────────────────────────────────────────────────────────

def _extract_parameters(json_path: Path) -> list[dict]:
    """Return a flat list of {name, type} dicts from a JSON file.

    Returns an empty list on any parse failure (caller handles errors).
    """
    try:
        with json_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or len(data) != 1:
            return []
        algo_body = next(iter(data.values()))
        params_raw = algo_body.get("PARAMETERS", []) if isinstance(algo_body, dict) else []
        result = []
        for item in params_raw:
            if isinstance(item, dict) and len(item) == 1:
                body = next(iter(item.values()))
                if isinstance(body, dict):
                    result.append({
                        "name": body.get("NAME", ""),
                        "type": body.get("TYPE", ""),
                    })
        return result
    except Exception:
        return []


def _extract_parameters_xml(xml_path: Path) -> list[dict]:
    """Return a flat list of {name, type} dicts from a DSL XML file.

    Returns an empty list on any parse failure.
    """
    try:
        algo = parse_dsl(xml_path)
        return [{"name": p.name, "type": p.type} for p in algo.parameters]
    except Exception:
        return []


def evaluate_dsl_file(xml_path: Path, schema_path: Path) -> dict:
    """Run the conversion + schema validation pipeline on a single DSL XML file.

    Skips JSON validation (sets ``json_valid=None``).

    Returns a result dict with keys:
        file, json_valid, xsd_valid, semantic_valid, errors, warnings, parameters
    """
    fname = xml_path.name
    result: dict = {
        "file": fname,
        "json_valid": None,
        "xsd_valid": None,
        "semantic_valid": None,
        "errors": [],
        "warnings": [],
        "parameters": _extract_parameters_xml(xml_path),
    }

    # ── Step 1: Parse DSL → FIXATDL XML (in-memory) ─────────────────────────
    try:
        algo = parse_dsl(xml_path)
        xml_root = build_fixatdl(algo)
        xml_bytes = etree.tostring(
            xml_root,
            pretty_print=True,
            xml_declaration=True,
            encoding="UTF-8",
        )
    except Exception as exc:
        result["xsd_valid"] = False
        result["semantic_valid"] = False
        result["errors"].append(f"Conversion error: {exc}")
        return result

    # ── Step 2: Schema validation (phases 1-3) via temp file ─────────────────
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".xml", delete=False, dir=tempfile.gettempdir()
        ) as tmp:
            tmp.write(xml_bytes)
            tmp_path = Path(tmp.name)

        try:
            val_result = schema_validate(tmp_path, schema_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        xsd_errors = [e for e in val_result.errors if e.phase == 1]
        ref_errors = [e for e in val_result.errors if e.phase == 2]
        sem_errors = [e for e in val_result.errors if e.phase == 3]
        sem_warnings = list(val_result.warnings)

        result["xsd_valid"] = len(xsd_errors) == 0
        result["semantic_valid"] = len(ref_errors) + len(sem_errors) == 0

        for e in val_result.errors:
            prefix = {1: "XSD", 2: "REF", 3: "SEM"}.get(e.phase, "ERR")
            result["errors"].append(f"[{prefix}:{e.rule_id}] {e.message}")
        for w in sem_warnings:
            result["warnings"].append(f"[SEM:{w.rule_id}] {w.message}")

    except Exception as exc:
        result["xsd_valid"] = False
        result["semantic_valid"] = False
        result["errors"].append(f"Schema validation error: {exc}")

    return result


def evaluate_file(json_path: Path, schema_path: Path) -> dict:
    """Run the full validation pipeline on a single JSON file.

    Returns a result dict with keys:
        file, json_valid, xsd_valid, semantic_valid, errors, warnings, parameters
    """
    fname = json_path.name
    result: dict = {
        "file": fname,
        "json_valid": None,
        "xsd_valid": None,
        "semantic_valid": None,
        "errors": [],
        "warnings": [],
        "parameters": _extract_parameters(json_path),
    }

    # ── Step 1: JSON validation ──────────────────────────────────────────────
    try:
        issues = validate_json(json_path)
    except (FileNotFoundError, ValueError) as exc:
        result["json_valid"] = False
        result["errors"].append(f"JSON parse error: {exc}")
        return result

    json_errors   = [i for i in issues if i.severity == "error"]
    json_warnings = [i for i in issues if i.severity == "warning"]

    for issue in json_errors:
        result["errors"].append(f"[{issue.rule_id}] {issue.message}")
    for issue in json_warnings:
        result["warnings"].append(f"[{issue.rule_id}] {issue.message}")

    if json_errors:
        result["json_valid"] = False
        # Skip XML conversion — it would likely fail or produce bad output
        return result

    result["json_valid"] = True

    # ── Step 2: Convert to FIXATDL XML (in-memory) ──────────────────────────
    try:
        algo = parse_json(json_path)
        xml_root = build_fixatdl(algo)
        xml_bytes = etree.tostring(
            xml_root,
            pretty_print=True,
            xml_declaration=True,
            encoding="UTF-8",
        )
    except Exception as exc:
        result["xsd_valid"] = False
        result["semantic_valid"] = False
        result["errors"].append(f"Conversion error: {exc}")
        return result

    # ── Step 3: Schema validation (phases 1-3) via temp file ─────────────────
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".xml", delete=False, dir=tempfile.gettempdir()
        ) as tmp:
            tmp.write(xml_bytes)
            tmp_path = Path(tmp.name)

        try:
            val_result = schema_validate(tmp_path, schema_path)
        finally:
            tmp_path.unlink(missing_ok=True)

        xsd_errors = [e for e in val_result.errors if e.phase == 1]
        ref_errors = [e for e in val_result.errors if e.phase == 2]
        sem_errors = [e for e in val_result.errors if e.phase == 3]
        sem_warnings = list(val_result.warnings)

        # XSD validity = no phase-1 errors
        result["xsd_valid"] = len(xsd_errors) == 0

        # Semantic validity = no phase-2 or phase-3 errors
        result["semantic_valid"] = len(ref_errors) + len(sem_errors) == 0

        for e in val_result.errors:
            prefix = {1: "XSD", 2: "REF", 3: "SEM"}.get(e.phase, "ERR")
            result["errors"].append(f"[{prefix}:{e.rule_id}] {e.message}")
        for w in sem_warnings:
            result["warnings"].append(f"[SEM:{w.rule_id}] {w.message}")

    except Exception as exc:
        result["xsd_valid"] = False
        result["semantic_valid"] = False
        result["errors"].append(f"Schema validation error: {exc}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Batch runner
# ─────────────────────────────────────────────────────────────────────────────

def run_batch(
    json_dir: Path,
    schema_path: Path,
    mapper: TypeMapper,
) -> list[dict]:
    """Evaluate all *.json and *.xml files in *json_dir* and return per-file results."""
    json_files = sorted(json_dir.glob("*.json"))
    xml_files  = sorted(json_dir.glob("*.xml"))
    all_files  = sorted(json_files + xml_files, key=lambda p: p.name)
    if not all_files:
        return []

    results = []
    for fp in all_files:
        # Feed each TYPE field through the mapper for coverage tracking
        params = _extract_parameters_xml(fp) if fp.suffix == ".xml" else _extract_parameters(fp)
        for p in params:
            if p.get("type"):
                mapper.map(p["type"])

        result = evaluate_dsl_file(fp, schema_path) if fp.suffix == ".xml" else evaluate_file(fp, schema_path)
        results.append(result)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Batch-evaluate a directory of converted JSON algo descriptors "
            "and report pass/fail, type mapping coverage, and diffs."
        ),
    )
    p.add_argument(
        "jsondir",
        type=Path,
        metavar="JSONDIR",
        help="Directory containing converted JSON files to evaluate",
    )
    p.add_argument(
        "--baseline",
        type=Path,
        metavar="FILE",
        help="Previous results JSON for diff/changelog output",
    )
    p.add_argument(
        "--output",
        type=Path,
        metavar="FILE",
        help="Persist results to this JSON file",
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
        help="Include warnings in reports",
    )
    p.add_argument(
        "--schema",
        type=Path,
        default=_DEFAULT_SCHEMA,
        metavar="XSD",
        help=f"Path to atdl-core-1-1.xsd (default: {_DEFAULT_SCHEMA})",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    # Ensure stdout can handle Unicode (error messages may contain ≥, –, etc.)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = _build_parser()
    args = parser.parse_args(argv)

    # ── Validate inputs ──────────────────────────────────────────────────────
    if not args.jsondir.is_dir():
        print(f"Error: '{args.jsondir}' is not a directory", file=sys.stderr)
        return 2
    if not args.schema.exists():
        print(f"Error: schema not found: {args.schema}", file=sys.stderr)
        return 2

    # ── Load baseline (if given) ─────────────────────────────────────────────
    baseline: list[dict] | None = None
    if args.baseline:
        try:
            with args.baseline.open(encoding="utf-8") as fh:
                baseline = json.load(fh)
        except FileNotFoundError:
            print(f"Error: baseline file not found: {args.baseline}", file=sys.stderr)
            return 2
        except json.JSONDecodeError as exc:
            print(f"Error: invalid JSON in baseline: {exc}", file=sys.stderr)
            return 2

    # ── Run batch ────────────────────────────────────────────────────────────
    mapper = TypeMapper()
    results = run_batch(args.jsondir, args.schema, mapper)

    fmt = args.output_format
    include_warnings = args.warnings

    if not results:
        print(f"No JSON or XML files found in '{args.jsondir}'.")
        return 0

    # ── Report A — dashboard ─────────────────────────────────────────────────
    print(format_dashboard(results, fmt=fmt, include_warnings=include_warnings))

    # ── Report B — type mapping ──────────────────────────────────────────────
    print(format_type_report(results, mapper, fmt=fmt))

    # ── Report C — coverage ──────────────────────────────────────────────────
    print(format_coverage(mapper, fmt=fmt))

    # ── Report D — diff (only when baseline supplied) ────────────────────────
    if baseline is not None:
        print(format_diff(baseline, results, fmt=fmt))

    # ── Persist results ──────────────────────────────────────────────────────
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("w", encoding="utf-8") as fh:
                json.dump(results, fh, indent=2)
            print(f"Results saved to: {args.output}", file=sys.stderr)
        except OSError as exc:
            print(f"Error writing output: {exc}", file=sys.stderr)
            return 2

    # ── Exit code ────────────────────────────────────────────────────────────
    all_passed = all(
        r.get("json_valid") is not False
        and r.get("xsd_valid")
        and r.get("semantic_valid")
        for r in results
    )
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
