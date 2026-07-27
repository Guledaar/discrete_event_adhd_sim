"""Run 3 — KPI time-series charts over the post-switch decay window."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from des.runners import POLICY_KPI_TIME_SERIES_KEYS

from kpi_display import streamlit_kpi_label
from helpers import (
    DAYS_PER_YEAR,
    decay_kpi_y_scale,
    flow_count_decay_keys,
    flow_wait_mean_median_pairs,
    is_wait_duration_column,
)

POLICY_COLORS = ["#2980b9", "#e74c3c", "#9b59b6", "#f39c12", "#1abc9c", "#e67e22"]


def _run_series(run: dict) -> pd.DataFrame:
    s = run.get("series")
    return s if isinstance(s, pd.DataFrame) else pd.DataFrame()


def decay_scenario_runs_from_result(result: dict[str, Any], *, policy_label: str = "Policy") -> list[dict]:
    """Baseline + policy ``kpi_time_series`` from one Run 3 result (this run only)."""
    runs: list[dict] = []
    n_reps = int(result.get("n_reps", 1))
    decay_years = int(round(float(result.get("decay_period_days", 365)) / 365))
    tag = f"{decay_years}yr decay"
    if result.get("control_summary"):
        cs = result["control_summary"]
        ts = cs.get("kpi_time_series")
        if ts is not None and not ts.empty:
            runs.append(
                {
                    "label": f"Baseline ({tag})",
                    "is_baseline": True,
                    "n_reps": int(result.get("control_n_reps", n_reps)),
                    "decay_years": decay_years,
                    "series": ts,
                }
            )
    ps = result.get("policy_summary")
    if ps is not None:
        ts = ps.get("kpi_time_series")
        if ts is not None and not ts.empty:
            runs.append(
                {
                    "label": f"{policy_label} ({tag})",
                    "is_baseline": False,
                    "n_reps": n_reps,
                    "decay_years": decay_years,
                    "series": ts,
                }
            )
    return runs


def _series_title(column: str) -> str:
    if (
        column in POLICY_KPI_TIME_SERIES_KEYS
        or column.startswith(("flow_", "backlog_", "capacity_", "assessments_", "diagnoses_"))
    ):
        return streamlit_kpi_label(column)
    return column.replace("_", " ").replace("flow count ", "").title()


def _add_traces(
    fig: go.Figure,
    scenario_runs: list[dict],
    column: str,
    *,
    y_scale: float = 1.0,
    suffix: str = "",
    line_dash: str | None = None,
) -> bool:
    """Add one trace per scenario for *column*; optional 95% CI band when aggregated."""
    added = False
    ci_lo, ci_hi = f"{column}_ci_lower", f"{column}_ci_upper"
    for i, run in enumerate(scenario_runs):
        s = _run_series(run)
        if s.empty or column not in s.columns:
            continue
        color = "#2c3e50" if run.get("is_baseline") else POLICY_COLORS[i % len(POLICY_COLORS)]
        dash = "dash" if run.get("is_baseline") else (line_dash or "solid")
        label = run["label"]
        if suffix:
            label = f"{label} — {suffix}"
        if run.get("n_reps", 1) > 1 and ci_lo in s.columns and ci_hi in s.columns:
            fig.add_trace(
                go.Scatter(
                    x=s["years_since_switch"],
                    y=s[ci_hi] * y_scale,
                    line={"width": 0},
                    showlegend=False,
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=s["years_since_switch"],
                    y=s[ci_lo] * y_scale,
                    fill="tonexty",
                    line={"width": 0},
                    showlegend=False,
                    opacity=0.2,
                )
            )
        fig.add_trace(
            go.Scatter(
                x=s["years_since_switch"],
                y=s[column] * y_scale,
                name=label,
                line={"color": color, "dash": dash},
            )
        )
        added = True
    return added


def _show_figure(fig: go.Figure, *, title: str, y_suffix: str = "") -> None:
    fig.update_layout(title=title, xaxis_title="Years since policy switch (T*)", height=380)
    if y_suffix:
        fig.update_yaxes(title=y_suffix)
    st.plotly_chart(fig, use_container_width=True)


def _plot_single_metric(
    scenario_runs: list[dict],
    column: str,
    *,
    chart_title: str | None = None,
) -> None:
    if not any(column in _run_series(run).columns for run in scenario_runs):
        return
    y_scale = decay_kpi_y_scale(column)
    title = chart_title or _series_title(column)
    if is_wait_duration_column(column) and "(yr)" not in title and "(years)" not in title.lower():
        title = f"{title} (yr)"
    fig = go.Figure()
    if _add_traces(fig, scenario_runs, column, y_scale=y_scale):
        y_label = "Years" if y_scale != 1.0 else ("%" if column.endswith("_pct") else "Count / rate")
        _show_figure(fig, title=title, y_suffix=y_label)


def render_run3_decay_period_charts(scenario_runs: list[dict]) -> None:
    """
    Policy effect over the decay window: backlog stock, backlog median waits,
    flow counts, and flow-window median wait times.
    """
    if not scenario_runs:
        st.info("Run a policy scenario to see KPIs over the decay period.")
        return

    decay_years = scenario_runs[0].get("decay_years")
    st.caption(
        "Checkpoints from **T\\*** through the end of the **decay period**. "
        "Solid lines = policy scenarios; dashed = baseline (no change at T*). "
        "Wait charts use **median** wait (yr). "
        "Shaded bands = 95% CI across replications when `n_reps > 1`."
        + (f" Decay window: **{decay_years} yr**." if decay_years else "")
    )

    tab_backlog, tab_bl_wait, tab_flow_n, tab_flow_w = st.tabs(
        [
            "Backlog / PTL — count",
            "Backlog / PTL — RTT waits",
            "Flow — event counts",
            "Flow — wait times",
        ]
    )

    with tab_backlog:
        st.markdown("**Backlog / PTL size over decay period**")
        _plot_single_metric(scenario_runs, "backlog_patients_at_horizon")
        with st.expander("Other backlog headline KPIs", expanded=False):
            for col in (
                "backlog_over_18_weeks_pct",
                "backlog_over_52_weeks_pct",
                "assessments_per_month",
                "diagnoses_per_month",
            ):
                _plot_single_metric(scenario_runs, col)

    with tab_bl_wait:
        st.markdown("**Backlog / PTL — median RTT wait (yr)**")
        _plot_single_metric(
            scenario_runs,
            "backlog_median_wait_days",
            chart_title=streamlit_kpi_label("backlog_median_wait_days"),
        )

    with tab_flow_n:
        st.markdown("**Flow-window event counts over decay period**")
        st.caption("Rolling flow window at each checkpoint (widens from T* until full window length).")
        for col in flow_count_decay_keys():
            _plot_single_metric(scenario_runs, col)

    with tab_flow_w:
        st.markdown("**Flow-window wait times — median (yr)**")
        for _title, _mean_col, median_col in flow_wait_mean_median_pairs():
            _plot_single_metric(
                scenario_runs,
                median_col,
                chart_title=f"{streamlit_kpi_label(median_col)}",
            )
