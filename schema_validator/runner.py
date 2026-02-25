"""Orchestrate all validation phases and return a consolidated result."""

from __future__ import annotations

from pathlib import Path

from . import phase1_xsd, phase2_refs, phase3_sem
from .loader import load
from .models import ValidationResult


def validate(
    xml_path: str | Path,
    schema_path: str | Path,
    *,
    phases: tuple[int, ...] = (1, 2, 3),
    schemas_dir: str | Path | None = None,
) -> ValidationResult:
    """Run selected validation phases against *xml_path*.

    Args:
        xml_path: Path to the ATDL XML document.
        schema_path: Path to ``atdl-core-1-1.xsd`` (entry-point XSD).
        phases: Tuple of phase numbers to run.  Defaults to all three.
        schemas_dir: Directory containing all ATDL XSD files.  Defaults to
            the directory that contains *schema_path*.

    Returns:
        :class:`ValidationResult` with ``errors`` and ``warnings`` lists.

    Notes:
        Phase 2 and Phase 3 are skipped when Phase 1 produces errors, because
        referential and semantic checks are unreliable on structurally invalid
        XML.  Pass ``phases=(2,)`` or ``phases=(3,)`` to override this
        behaviour (e.g. for targeted unit testing).
    """
    xml_path = Path(xml_path)
    schema_path = Path(schema_path)
    if schemas_dir is None:
        schemas_dir = schema_path.parent

    result = ValidationResult()

    # --- Phase 1 ---
    if 1 in phases:
        p1_errors = phase1_xsd.run(xml_path, schema_path)
        result.errors.extend(p1_errors)
        if p1_errors and 1 in phases and (2 in phases or 3 in phases):
            # Short-circuit: later phases are unreliable on invalid XML
            return result

    # Build document context for Phases 2 and 3
    if 2 in phases or 3 in phases:
        ctx = load(xml_path, schemas_dir)

        if 2 in phases:
            result.errors.extend(phase2_refs.run(ctx))

        if 3 in phases:
            sem_errors, sem_warnings = phase3_sem.run(ctx)
            result.errors.extend(sem_errors)
            result.warnings.extend(sem_warnings)

    return result
