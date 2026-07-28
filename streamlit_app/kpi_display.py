"""Consistent KPI display names for Streamlit Run 1–3."""

from __future__ import annotations

from des.run_report import kpi_label

_WAIT_KEY_FRAGMENTS = (
    "_wait_days",
    "flow_wait_mean",
    "flow_wait_median",
    "completed_mean_rtt",
)


def is_wait_kpi_key(key: str) -> bool:
    return any(part in key for part in _WAIT_KEY_FRAGMENTS)


def streamlit_kpi_label(key: str) -> str:
    """
    Human-readable KPI name for dashboards and tables.

    Wait durations are labelled with **(yr)** — values are still converted from
    simulation days in the UI layer.
    """
    label = kpi_label(key)
    if not is_wait_kpi_key(key):
        return label
    for suffix in (" (days)", " — days", "(days)"):
        label = label.replace(suffix, "")
    if "(yr)" not in label and "years" not in label.lower():
        label = f"{label} (yr)"
    return label


def calibration_target_label(key: str, *, kind: str) -> str:
    """Run 1 matching-target dropdown label ([Stock] / [Flow] prefix)."""
    kind_title = "Stock" if kind == "stock" else "Flow"
    return f"[{kind_title}] {streamlit_kpi_label(key)}"


def run3_delta_metric_label(key: str) -> str:
    """Short label for Run 3 policy vs baseline delta strip."""
    return streamlit_kpi_label(key)
