"""Collision-safe CSV exports for completed simulation runs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, Mapping, Union
from uuid import uuid4

import pandas as pd

from des.kpi import RunResult

PathLike = Union[str, Path]

_CAPACITY_KEYS = (
    "clinician_hours_released",
    "clinician_hours_used",
    "clinician_hours_unused",
    "overall_clinician_utilisation",
    "assessment_utilisation",
    "workshop_utilisation",
)


def _safe_name(value: str) -> str:
    """Return a filesystem-safe, non-empty label."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return cleaned or "simulation"


def _reserve_run_directory(
    output_root: Path,
    scenario: str,
    rep: int,
) -> Path:
    """Atomically create a unique directory for one physical simulation."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    directory = (
        output_root
        / _safe_name(scenario)
        / f"{timestamp}_rep-{int(rep):03d}_{uuid4().hex[:8]}"
    )
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def _atomic_to_csv(frame: pd.DataFrame, destination: Path) -> None:
    """Write a DataFrame through a temporary sibling and atomically rename it."""
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        frame.to_csv(temporary, index=False)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def export_run_result(
    result: RunResult,
    *,
    output_root: PathLike = "run_output/simulations",
    scenario: str = "baseline",
    rep: int = 0,
    metadata: Mapping[str, Any] | None = None,
) -> Dict[str, str]:
    """
    Export one completed simulation into a new, non-overwriting run directory.

    Four stable filenames are written beneath a uniquely reserved directory:
    ``kpis.csv``, ``capacity_summary.csv``, ``validation_report.csv`` and
    ``patient_summary.csv``.  Existing exports are never replaced; timestamp,
    replication index and a UUID suffix make the directory safe for parallel
    replications.

    Parameters
    ----------
    result : RunResult
        Completed KPI result with summary, patient, capacity and validation
        tables.
    output_root : str or pathlib.Path, optional
        Parent directory for automatic simulation exports.
    scenario : str, optional
        Scenario label used as a directory component.
    rep : int, optional
        Replication index included in the unique directory name.
    metadata : mapping, optional
        Run metadata appended to the one-row KPI and capacity summaries, for
        example warm-up and collection durations.

    Returns
    -------
    dict[str, str]
        Mapping from report name to absolute CSV path.

    Notes
    -----
    ``patient_summary.csv`` contains the enriched arrival-cohort patient table
    returned by :func:`des.kpi.compute_kpis`.  It therefore excludes warm-up
    arrivals by design.  ``validation_report.csv`` contains one PASS, WARNING
    or FAIL row per internal validation rule.
    """
    run_directory = _reserve_run_directory(Path(output_root), scenario, rep)
    run_metadata = dict(metadata or {})
    run_metadata.setdefault("scenario", scenario)
    run_metadata.setdefault("rep", rep)

    kpi_row = {**result.summary, **run_metadata}
    capacity_row = {
        key: result.summary.get(key, float("nan")) for key in _CAPACITY_KEYS
    }
    capacity_row.update(run_metadata)

    reports = {
        "kpis": pd.DataFrame([kpi_row]),
        "capacity_summary": pd.DataFrame([capacity_row]),
        "validation_report": result.validation_report.copy(),
        "patient_summary": result.patients.copy(),
    }
    paths: Dict[str, str] = {}
    for name, frame in reports.items():
        path = run_directory / f"{name}.csv"
        _atomic_to_csv(frame, path)
        paths[name] = str(path.resolve())

    result.export_paths = paths
    return paths


__all__ = ["export_run_result"]
