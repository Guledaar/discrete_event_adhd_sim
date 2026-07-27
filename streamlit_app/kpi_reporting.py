"""Shared KPI strips, captions, and plots for Run 1–3 (operational reporting)."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd
import streamlit as st
from scipy.stats import t

from helpers import DAYS_PER_YEAR
from kpi_display import streamlit_kpi_label

# (kpi_key, scale, decimals, category: stock | flow | capacity)
CORE_KPI_SPECS: tuple[tuple[str, float, int, str], ...] = (
    ("backlog_patients_at_horizon", 1.0, 0, "stock"),
    ("backlog_mean_wait_days", 1.0 / DAYS_PER_YEAR, 2, "stock"),
    ("backlog_median_wait_days", 1.0 / DAYS_PER_YEAR, 2, "stock"),
    ("backlog_over_18_weeks_pct", 1.0, 1, "stock"),
    ("backlog_over_52_weeks_pct", 1.0, 1, "stock"),
    ("assessments_per_month", 1.0, 1, "flow"),
    ("diagnoses_per_month", 1.0, 1, "flow"),
    ("capacity_used_pct", 1.0, 1, "capacity"),
)

RUN2_STOCK_KEYS: tuple[tuple[str, float, int], ...] = (
    ("backlog_patients_at_horizon", 1.0, 0),
    ("backlog_mean_wait_days", 1.0 / DAYS_PER_YEAR, 2),
)

RUN2_FLOW_METRIC_ORDER: tuple[str, ...] = (
    "flow_count_referrals",
    "flow_count_assessments_started",
    "flow_count_assessments_finished",
    "flow_count_diagnoses",
    "flow_wait_mean_days_assessments_started",
    "flow_wait_median_days_assessments_started",
    "flow_wait_mean_days_assessments_finished",
    "flow_wait_median_days_assessments_finished",
)


def _category_caption(category: str) -> str:
    if category == "stock":
        return "Stock at horizon"
    if category == "flow":
        return "Flow (rolling window)"
    return "Capacity"


def stock_flow_footnote(*, horizon_label: str, flow_window_days: float | None) -> str:
    fw = f"{flow_window_days:.0f} d" if flow_window_days is not None else "—"
    return (
        f"**Stock** = snapshot at {horizon_label}. "
        f"**Flow** = rolling window **{fw}** ending at that horizon. "
        "Waits shown in **years**. See **Glossary** for definitions."
    )


def planner_question(run: int) -> str:
    questions = {
        1: "**Planning question:** When is the model in a stable state that matches provider targets (**T\\***)?",
        2: "**Planning question:** If nothing changes at **T\\***, how uncertain are backlog size, waits, and recent throughput?",
        3: "**Planning question:** After a policy at **T\\***, does backlog shrink and do waits improve vs baseline over the decay window?",
    }
    return questions.get(run, "")


def render_session_status_sidebar() -> None:
    with st.sidebar:
        st.markdown("---")
        st.markdown("**Session status**")
        t_star = st.session_state.get("t_star")
        if t_star is not None:
            st.markdown(f"T\\*: **{float(t_star):.0f} d** ({float(t_star) / DAYS_PER_YEAR:.1f} yr)")
        else:
            st.caption("T\\* not set — run **Run 1**.")

        r2 = st.session_state.get("run2_result")
        if r2 is not None:
            st.caption(f"Run 2: **{r2.get('n_reps', '?')}** rep(s) at T\\*")

        scenarios = st.session_state.get("run3_scenario_runs") or []
        policy_n = sum(1 for s in scenarios if not s.get("is_baseline"))
        if scenarios:
            st.caption(f"Run 3: **{policy_n}** policy scenario(s) in session")


def _scalar_rep_summary(values: pd.Series) -> dict[str, float | int]:
    s = pd.to_numeric(values, errors="coerce").dropna()
    n = int(len(s))
    if n == 0:
        nan = float("nan")
        return {"n": 0, "mean": nan, "ci_lower": nan, "ci_upper": nan}
    mean = float(s.mean())
    if n == 1:
        return {"n": 1, "mean": mean, "ci_lower": mean, "ci_upper": mean}
    sd = float(s.std(ddof=1))
    se = sd / np.sqrt(n)
    half = float(t.ppf(0.975, n - 1) * se)
    return {"n": n, "mean": mean, "ci_lower": mean - half, "ci_upper": mean + half}


def format_metric_display(
    mean: float,
    ci_lower: float,
    ci_upper: float,
    n: int,
    *,
    digits: int,
) -> str:
    if n == 0 or (isinstance(mean, float) and np.isnan(mean)):
        return "—"
    if n <= 1:
        return f"{mean:.{digits}f}"
    return f"{mean:.{digits}f} ({ci_lower:.{digits}f}–{ci_upper:.{digits}f})"


def _value_from_row(row: Mapping[str, Any] | pd.Series, key: str) -> float | None:
    if key not in row:
        return None
    val = row[key]
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return float(val)


def render_core_kpi_strip_from_row(
    row: Mapping[str, Any] | pd.Series,
    *,
    n_reps: int = 1,
    horizon_label: str = "horizon",
    flow_window_days: float | None = None,
) -> None:
    """Single checkpoint (Run 1 at T*)."""
    st.caption(stock_flow_footnote(horizon_label=horizon_label, flow_window_days=flow_window_days))
    cols = st.columns(len(CORE_KPI_SPECS))
    for col, (key, scale, digits, category) in zip(cols, CORE_KPI_SPECS):
        val = _value_from_row(row, key)
        label = streamlit_kpi_label(key)
        with col:
            if val is None:
                st.metric(label, "—", help=_category_caption(category))
            else:
                st.metric(
                    label,
                    f"{val * scale:.{digits}f}",
                    help=_category_caption(category),
                )
    if n_reps <= 1:
        st.caption("Single replication — point estimates only (no CI).")


def render_run2_baseline_headline_kpis(
    snapshots: pd.DataFrame,
    flow_summary: pd.DataFrame | None,
    *,
    n_reps: int,
    flow_window_days: float | None,
) -> None:
    """Run 2 — stock backlog count + mean wait; flow counts and mean/median waits (summarised)."""
    if snapshots is None or snapshots.empty:
        return
    st.caption(stock_flow_footnote(horizon_label="T*", flow_window_days=flow_window_days))
    st.markdown("**Stock at T\\***")
    cols = st.columns(len(RUN2_STOCK_KEYS))
    for col, (key, scale, digits) in zip(cols, RUN2_STOCK_KEYS):
        label = streamlit_kpi_label(key)
        if key not in snapshots.columns:
            with col:
                st.metric(label, "—", help="Stock at horizon")
            continue
        stats = _scalar_rep_summary(snapshots[key])
        display = format_metric_display(
            stats["mean"] * scale,
            stats["ci_lower"] * scale,
            stats["ci_upper"] * scale,
            int(stats["n"]),
            digits=digits,
        )
        with col:
            st.metric(label, display, help="Stock at horizon (backlog / PTL cohort)")

    st.markdown("**Flow window** (mean ± 95% CI across replications)")
    if flow_summary is None or flow_summary.empty or "metric" not in flow_summary.columns:
        st.caption("No flow summary — re-run Run 2 to refresh flow KPIs.")
    else:
        from helpers import flow_kpi_summary_to_years

        fs = flow_kpi_summary_to_years(flow_summary)
        order = {m: i for i, m in enumerate(RUN2_FLOW_METRIC_ORDER)}
        fs = fs.copy()
        fs["_ord"] = fs["metric"].astype(str).map(lambda x: order.get(x, 999))
        fs = fs.sort_values("_ord")
        rows: list[dict[str, str]] = []
        for _, r in fs.iterrows():
            metric = str(r["metric"])
            if not (
                metric.startswith("flow_count_")
                or "flow_wait_mean" in metric
                or "flow_wait_median" in metric
            ):
                continue
            is_wait = "wait" in metric
            digits = 2 if is_wait else 0
            mean = float(r["mean"])
            lo = float(r.get("ci_lower", mean))
            hi = float(r.get("ci_upper", mean))
            n = int(r.get("n", n_reps))
            rows.append(
                {
                    "KPI": streamlit_kpi_label(metric),
                    "Mean (95% CI)": format_metric_display(mean, lo, hi, n, digits=digits),
                }
            )
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.caption("No flow count / wait metrics in this summary.")

    if n_reps <= 1:
        st.caption("Use **n_reps > 1** for 95% CI on the metrics above.")


def render_run1_outcome_strip(
    *,
    t_star: float,
    matched: bool,
    mape: float,
    elapsed_s: float,
    n_steps: int | str,
    target_label: str,
    target_display: float,
) -> None:
    from helpers import format_duration

    match_txt = "matched ✓" if matched else "best MAPE (no exact match)"
    st.success(
        f"**T\\*** = {t_star:.0f} days ({t_star / DAYS_PER_YEAR:.1f} years) · "
        f"target **{target_label}** = {target_display:g} · **{match_txt}** · "
        f"MAPE = {mape:.3f} · runtime {format_duration(elapsed_s)} · {n_steps} horizon step(s)"
    )


def render_run3_decision_strip(result: dict[str, Any]) -> None:
    n_reps = int(result.get("n_reps", 1))
    comp = result.get("comparison") or {}
    comp_summary = result.get("comparison_summary")
    if not comp and (comp_summary is None or comp_summary.empty):
        st.info("No baseline comparison — enable **Include baseline** or inspect policy arm only.")
        return

    st.markdown("**Policy vs baseline (paired replications)**")
    metrics = (
        ("delta_backlog_at_end", 0),
        ("delta_backlog_decay", 0),
        ("delta_backlog_decay_per_month", 1),
    )

    def _delta_display(key: str, digits: int) -> str:
        if comp_summary is not None and not comp_summary.empty and "metric" in comp_summary.columns:
            row = comp_summary.set_index("metric")
            if key in row.index:
                r = row.loc[key]
                return format_metric_display(
                    float(r["mean"]),
                    float(r.get("ci_lower", r["mean"])),
                    float(r.get("ci_upper", r["mean"])),
                    int(r.get("n", n_reps)),
                    digits=digits,
                )
        val = comp.get(key)
        if val is None:
            return "—"
        return f"{float(val):.{digits}f}"

    c1, c2, c3 = st.columns(3)
    for col, (key, digits) in zip((c1, c2, c3), metrics):
        with col:
            st.metric(
                streamlit_kpi_label(key),
                _delta_display(key, digits),
                help="Policy − baseline (positive reduction = more backlog shrinkage)",
            )
    if n_reps <= 1:
        st.caption("Single replication — deltas are pairwise for rep 0 only; use **n_reps > 1** for CI.")


def render_end_of_decay_core_compare(result: dict[str, Any]) -> None:
    """Baseline vs policy core KPIs at end of decay (from arm summaries)."""
    fw = float(result.get("flow_window_days", 365))
    decay_yr = int(round(float(result.get("decay_period_days", 365)) / 365))
    horizon = f"end of {decay_yr} yr decay"

    arms: list[tuple[str, dict | None]] = [
        ("Baseline", result.get("control_summary")),
        ("Policy", result.get("policy_summary")),
    ]
    rows: list[dict[str, Any]] = []
    for title, summary in arms:
        if summary is None:
            continue
        snap = summary.get("snapshots")
        if snap is None or snap.empty:
            continue
        stats_row: dict[str, Any] = {"Arm": title}
        for key, scale, digits, _cat in CORE_KPI_SPECS:
            col_label = streamlit_kpi_label(key)
            if key not in snap.columns:
                stats_row[col_label] = "—"
                continue
            stt = _scalar_rep_summary(snap[key])
            stats_row[col_label] = format_metric_display(
                stt["mean"] * scale,
                stt["ci_lower"] * scale,
                stt["ci_upper"] * scale,
                int(stt["n"]),
                digits=digits,
            )
        rows.append(stats_row)
    if not rows:
        return
    st.markdown(f"**Core KPIs at {horizon}** (stock + flow; waits in years where applicable)")
    st.caption(stock_flow_footnote(horizon_label=horizon, flow_window_days=fw))
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
