"""Reporter — format evaluation results into human-readable or JSON output.

Four report types:

* :func:`format_dashboard`  — aggregate pass/fail table for a batch run
* :func:`format_type_report` — per-parameter type mapping detail
* :func:`format_coverage`   — which type_map entries were/weren't used
* :func:`format_diff`       — regression / fix changelog vs a baseline run
"""

from __future__ import annotations

import json
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

_CHECK = "pass"
_CROSS = "FAIL"
_DASH  = " -- "


def _tick(val: bool | None) -> str:
    if val is True:
        return _CHECK
    if val is False:
        return _CROSS
    return _DASH


# ─────────────────────────────────────────────────────────────────────────────
# Report A — Aggregate pass/fail dashboard
# ─────────────────────────────────────────────────────────────────────────────

def format_dashboard(
    results: list[dict],
    *,
    fmt: str = "text",
    include_warnings: bool = False,
) -> str:
    """Format an aggregate pass/fail dashboard.

    Args:
        results: List of per-file result dicts as produced by ``run_evals.py``.
            Each dict has keys: ``file``, ``json_valid``, ``xsd_valid``,
            ``semantic_valid``, ``errors``, ``warnings``.
        fmt: ``"text"`` or ``"json"``.
        include_warnings: When ``True``, append warning lines below the table.

    Returns:
        Formatted string.
    """
    if fmt == "json":
        summary = _dashboard_summary(results)
        return json.dumps({"dashboard": results, "summary": summary},
                          indent=2, default=str)

    if not results:
        return "No results to display.\n"

    col_w = max(len(r["file"]) for r in results)
    col_w = max(col_w, len("Strategy"))

    header = f"{'Strategy':<{col_w}}  {'JSON':^4}  {'XSD':^4}  {'Semantic':^8}"
    sep    = "─" * len(header)
    lines  = [header, sep]

    passed_all = 0
    for r in results:
        json_sym = _tick(r.get("json_valid"))
        xsd_sym  = _tick(r.get("xsd_valid"))
        sem_sym  = _tick(r.get("semantic_valid"))
        lines.append(
            f"{r['file']:<{col_w}}  {json_sym:^4}  {xsd_sym:^4}  {sem_sym:^8}"
        )
        if r.get("json_valid") and r.get("xsd_valid") and r.get("semantic_valid"):
            passed_all += 1

        errors = r.get("errors") or []
        for e in errors:
            lines.append(f"  ERROR: {e}")

        if include_warnings:
            warnings = r.get("warnings") or []
            for w in warnings:
                lines.append(f"  WARN:  {w}")

    failed = len(results) - passed_all
    lines.append(sep)
    lines.append(
        f"Total: {len(results)}   Passed all: {passed_all}   Failed: {failed}"
    )
    return "\n".join(lines) + "\n"


def _dashboard_summary(results: list[dict]) -> dict:
    passed = sum(
        1 for r in results
        if r.get("json_valid") and r.get("xsd_valid") and r.get("semantic_valid")
    )
    return {
        "total": len(results),
        "passed_all": passed,
        "failed": len(results) - passed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Report B — Per-parameter type mapping report
# ─────────────────────────────────────────────────────────────────────────────

def format_type_report(
    results: list[dict],
    mapper: Any,
    *,
    fmt: str = "text",
) -> str:
    """Show the reverse mapping (FIXATDL type ← source alias) for each file.

    Highlights TYPE values that are not present in ``type_map.toml`` at all —
    these may be FIXATDL types used directly (fine) or unmapped source names
    that slipped through.

    Args:
        results: Per-file results list from the batch runner.
        mapper: A :class:`~source_converter.type_mapper.TypeMapper` instance
            whose ``all_entries`` reflect the loaded config.
        fmt: ``"text"`` or ``"json"``.

    Returns:
        Formatted string.
    """
    all_entries = mapper.all_entries  # lowercase source → fixatdl
    # Build reverse map: fixatdl → [source aliases]
    reverse: dict[str, list[str]] = {}
    for src, fix in all_entries.items():
        reverse.setdefault(fix, []).append(src)

    rows: list[dict] = []
    for r in results:
        for param in r.get("parameters", []):
            type_val = param.get("type", "")
            # Is this value a FIXATDL type reachable via the map?
            aliases = reverse.get(type_val, [])
            in_map = bool(aliases)
            rows.append({
                "file": r["file"],
                "param": param.get("name", ""),
                "type": type_val,
                "aliases": aliases,
                "in_map": in_map,
            })

    if fmt == "json":
        return json.dumps({"type_report": rows}, indent=2)

    if not rows:
        return "No parameter type data available.\n"

    col_f = max(len(rw["file"]) for rw in rows)
    col_f = max(col_f, 8)
    col_p = max(len(rw["param"]) for rw in rows)
    col_p = max(col_p, 9)
    col_t = max(len(rw["type"]) for rw in rows)
    col_t = max(col_t, 12)

    header = (f"{'File':<{col_f}}  {'Parameter':<{col_p}}  "
              f"{'FIXATDL Type':<{col_t}}  Source Aliases  In Map?")
    sep    = "─" * (col_f + col_p + col_t + 40)
    lines  = [header, sep]

    for rw in rows:
        aliases_str = ", ".join(rw["aliases"]) if rw["aliases"] else "(direct)"
        flag = "" if rw["in_map"] else " ← not in type_map.toml"
        lines.append(
            f"{rw['file']:<{col_f}}  {rw['param']:<{col_p}}  "
            f"{rw['type']:<{col_t}}  {aliases_str}{flag}"
        )

    return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# Report C — Coverage report
# ─────────────────────────────────────────────────────────────────────────────

def format_coverage(
    mapper: Any,
    *,
    fmt: str = "text",
) -> str:
    """Show which type_map entries were seen and which source types were missing.

    Args:
        mapper: A :class:`~source_converter.type_mapper.TypeMapper` instance
            that has already processed the batch (``map()`` calls made).
        fmt: ``"text"`` or ``"json"``.

    Returns:
        Formatted string.
    """
    report = mapper.coverage_report()

    if fmt == "json":
        return json.dumps({"coverage": report}, indent=2)

    lines = [
        f"Type mapping coverage  (total lookups: {report['total_lookups']})",
        "",
    ]

    mapped = report["mapped"]
    if mapped:
        lines.append("Mapped types:")
        for entry in mapped:
            lines.append(f"  {entry['source']!s:<20} → {entry['fixatdl']}")
    else:
        lines.append("Mapped types: (none)")

    lines.append("")
    unmapped = report["unmapped"]
    if unmapped:
        lines.append("Unmapped types (add to type_map.toml):")
        for src in unmapped:
            lines.append(f"  {src}")
    else:
        lines.append("Unmapped types: (none — full coverage)")

    return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# Report D — Conversion diff / changelog
# ─────────────────────────────────────────────────────────────────────────────

def format_diff(
    baseline: list[dict],
    current: list[dict],
    *,
    fmt: str = "text",
) -> str:
    """Compare current results against a saved baseline.

    Args:
        baseline: List of per-file results from a previous run (loaded from
            ``--output`` JSON).
        current: List of per-file results from the current run.
        fmt: ``"text"`` or ``"json"``.

    Returns:
        Formatted changelog string.
    """
    def _all_pass(r: dict) -> bool:
        return bool(r.get("json_valid") and r.get("xsd_valid") and
                    r.get("semantic_valid"))

    def _err_set(r: dict) -> frozenset[str]:
        return frozenset(r.get("errors") or [])

    base_by_file = {r["file"]: r for r in baseline}
    curr_by_file = {r["file"]: r for r in current}

    regressions: list[dict] = []
    fixes:        list[dict] = []
    changed:      list[dict] = []
    new_files:    list[str]  = []
    removed_files: list[str] = []

    all_files = sorted(set(base_by_file) | set(curr_by_file))
    for fname in all_files:
        b = base_by_file.get(fname)
        c = curr_by_file.get(fname)
        if b is None:
            new_files.append(fname)
            continue
        if c is None:
            removed_files.append(fname)
            continue
        b_pass = _all_pass(b)
        c_pass = _all_pass(c)
        if b_pass and not c_pass:
            regressions.append({"file": fname,
                                 "new_errors": sorted(_err_set(c) - _err_set(b))})
        elif not b_pass and c_pass:
            fixes.append({"file": fname,
                           "resolved_errors": sorted(_err_set(b) - _err_set(c))})
        elif _err_set(b) != _err_set(c):
            changed.append({
                "file": fname,
                "added":   sorted(_err_set(c) - _err_set(b)),
                "removed": sorted(_err_set(b) - _err_set(c)),
            })

    if fmt == "json":
        return json.dumps({
            "regressions": regressions,
            "fixes": fixes,
            "changed": changed,
            "new_files": new_files,
            "removed_files": removed_files,
        }, indent=2)

    lines = ["Conversion diff / changelog", "=" * 30, ""]

    if regressions:
        lines.append(f"Regressions ({len(regressions)} newly failing):")
        for item in regressions:
            lines.append(f"  FAIL {item['file']}")
            for e in item["new_errors"]:
                lines.append(f"      + {e}")
        lines.append("")

    if fixes:
        lines.append(f"Fixes ({len(fixes)} newly passing):")
        for item in fixes:
            lines.append(f"  pass {item['file']}")
            for e in item["resolved_errors"]:
                lines.append(f"      - {e}")
        lines.append("")

    if changed:
        lines.append(f"Changed ({len(changed)} altered error sets):")
        for item in changed:
            lines.append(f"  ~~~  {item['file']}")
            for e in item["added"]:
                lines.append(f"      + {e}")
            for e in item["removed"]:
                lines.append(f"      - {e}")
        lines.append("")

    if new_files:
        lines.append(f"New files ({len(new_files)}):")
        for f in new_files:
            lines.append(f"  + {f}")
        lines.append("")

    if removed_files:
        lines.append(f"Removed files ({len(removed_files)}):")
        for f in removed_files:
            lines.append(f"  - {f}")
        lines.append("")

    if not any([regressions, fixes, changed, new_files, removed_files]):
        lines.append("No changes — results identical to baseline.")

    return "\n".join(lines) + "\n"
