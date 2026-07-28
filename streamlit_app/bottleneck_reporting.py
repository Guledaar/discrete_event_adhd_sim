"""Bottleneck view: waiting queues by stage, waits, and clinician utilisation (Run 1–3)."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd
import streamlit as st

from helpers import DAYS_PER_YEAR
from kpi_display import streamlit_kpi_label

_FUNNEL_STOCK_STAGES: tuple[str, ...] = (
    "referrals_active",
    "started_assessment",
    "finished_assessment",
    "sent_to_workshops",
    "workshop_joined",
    "workshop_started",
    "still_on_pathway_all",
)


def _capacity_row(report: Any) -> dict[str, float]:
    util = getattr(report, "capacity_utilisation", None)
    if util is None or util.empty:
        return {}
    row = util.iloc[0]
    overall = float(row.get("hours_used_pct", np.nan))
    assessment = float(row.get("assessment_pct_of_released", np.nan))
    workshop = float(row.get("workshop_pct_of_released", np.nan))
    released = float(row.get("hours_released", np.nan))
    used = float(row.get("hours_used", np.nan))
    assess_h = float(row.get("assessment_hours_used", np.nan))
    work_h = float(row.get("workshop_hours_used", np.nan))
    assess_of_used = 100.0 * assess_h / used if used else np.nan
    work_of_used = 100.0 * work_h / used if used else np.nan
    return {
        "overall_pct": overall,
        "assessment_pct_released": assessment,
        "workshop_pct_released": workshop,
        "assessment_pct_of_used": assess_of_used,
        "workshop_pct_of_used": work_of_used,
        "hours_released": released,
        "hours_used": used,
        "hours_unused": float(row.get("hours_unused", np.nan)),
    }


def _waiting_stage_table(stock: pd.DataFrame) -> pd.DataFrame:
    if stock is None or stock.empty:
        return pd.DataFrame()
    out = stock.copy()
    if "label" not in out.columns and "stage" in out.columns:
        from des.run_report import kpi_label

        out["label"] = out["stage"].map(kpi_label)
    for col in ("still_waiting_median_days", "still_waiting_mean_days"):
        if col in out.columns:
            out[col.replace("_days", "_years")] = pd.to_numeric(out[col], errors="coerce") / DAYS_PER_YEAR
    out = out.sort_values("still_waiting_n", ascending=False, na_position="last")
    return out


def _funnel_stock_table(funnel: pd.DataFrame) -> pd.DataFrame:
    if funnel is None or funnel.empty:
        return pd.DataFrame()
    if "stage" in funnel.columns:
        idx = funnel.set_index("stage")
    else:
        idx = funnel
    rows = []
    for stage in _FUNNEL_STOCK_STAGES:
        if stage not in idx.index:
            continue
        row = idx.loc[stage]
        rows.append(
            {
                "stage": stage,
                "label": row.get("label", stage),
                "count": int(row.get("count", 0)),
            }
        )
    return pd.DataFrame(rows)


def _bottleneck_insight(waiting: pd.DataFrame, capacity: Mapping[str, float]) -> str | None:
    if waiting.empty or "still_waiting_n" not in waiting.columns:
        return None
    n = pd.to_numeric(waiting["still_waiting_n"], errors="coerce").fillna(0)
    if n.max() <= 0:
        return "No patients counted as still waiting for a pathway milestone at this horizon."
    top = waiting.loc[n.idxmax()]
    label = str(top.get("label", top.get("stage", "—")))
    count = int(top.get("still_waiting_n", 0))
    med_yr = float(top.get("still_waiting_median_years", np.nan))
    med_txt = f"{med_yr:.2f} yr" if not np.isnan(med_yr) else "—"
    overall = capacity.get("overall_pct", np.nan)
    cap_txt = ""
    if not np.isnan(overall):
        cap_txt = f" Clinician pool **{overall:.0f}%** utilised (released weekday hours)."
        if overall >= 85:
            cap_txt += " High utilisation — **capacity is likely binding** for throughput."
    return (
        f"Largest queue at horizon: **{label}** — **{count}** patients still waiting "
        f"(median wait **{med_txt}** among those still waiting).{cap_txt}"
    )


def render_capacity_utilisation_metrics(capacity: Mapping[str, float]) -> None:
    """Three headline utilisation metrics + optional detail."""
    if not capacity:
        st.warning("No capacity utilisation data for this run.")
        return
    c1, c2, c3 = st.columns(3)
    overall = capacity.get("overall_pct", np.nan)
    assess_r = capacity.get("assessment_pct_released", np.nan)
    work_r = capacity.get("workshop_pct_released", np.nan)
    with c1:
        st.metric(
            streamlit_kpi_label("capacity_used_pct"),
            "—" if np.isnan(overall) else f"{overall:.1f}%",
            help="Used clinician-hours ÷ released weekday hours (whole run to horizon).",
        )
    with c2:
        st.metric(
            "Assessment hours (% of released capacity)",
            "—" if np.isnan(assess_r) else f"{assess_r:.1f}%",
            help="Assessment activity as a share of all weekday hours released.",
        )
    with c3:
        st.metric(
            "Workshop hours (% of released capacity)",
            "—" if np.isnan(work_r) else f"{work_r:.1f}%",
            help="Workshop activity as a share of all weekday hours released.",
        )
    assess_u = capacity.get("assessment_pct_of_used", np.nan)
    work_u = capacity.get("workshop_pct_of_used", np.nan)
    if not np.isnan(assess_u) and not np.isnan(work_u):
        st.caption(
            f"Of **used** hours: assessment **{assess_u:.1f}%**, workshop **{work_u:.1f}%**. "
            f"Unused released hours: **{100.0 - overall:.1f}%** of capacity"
            if not np.isnan(overall)
            else f"Of used hours: assessment {assess_u:.1f}%, workshop {work_u:.1f}%."
        )


def render_bottleneck_dashboard(
    report: Any,
    *,
    horizon_label: str = "horizon",
    flow_window_days: float | None = None,
    replication_note: str | None = None,
) -> None:
    """
    Show capacity split, waiting counts by stage, waits, and pathway stock.

    Parameters
    ----------
    report : RunReport
        Full KPI bundle from one replication.
    """
    fw = f"{flow_window_days:.0f} d" if flow_window_days is not None else "—"
    st.markdown("### Bottleneck — queues, waits & clinician capacity")
    st.caption(
        f"**Stock** at {horizon_label}: who is still waiting for each milestone, and how long. "
        f"**Capacity** is the shared weekday clinician-hour pool (assessment + workshop). "
        f"Flow window for throughput KPIs elsewhere: **{fw}**."
        + (f" {replication_note}" if replication_note else "")
    )

    capacity = _capacity_row(report)
    render_capacity_utilisation_metrics(capacity)

    waiting = _waiting_stage_table(report.waits_stock_by_stage)
    insight = _bottleneck_insight(waiting, capacity)
    if insight:
        st.markdown(insight)

    if waiting.empty:
        st.info("No stage wait table on this report.")
        return

    active = waiting.loc[waiting["still_waiting_n"].fillna(0).astype(int) > 0].copy()
    col_chart, col_table = st.columns([1, 1])
    with col_chart:
        st.markdown("**Patients still waiting (by stage)**")
        if active.empty:
            st.caption("All milestone cohorts have reached the next step at this horizon.")
        else:
            chart = active.set_index("label")[["still_waiting_n"]].sort_values(
                "still_waiting_n", ascending=True
            )
            st.bar_chart(chart, height=min(420, 80 + 36 * len(chart)))

    with col_table:
        st.markdown("**Wait times among those still waiting**")
        if active.empty:
            st.caption("—")
        else:
            med = active.set_index("label")[["still_waiting_median_years"]].sort_values(
                "still_waiting_median_years", ascending=True
            )
            med.columns = ["Median wait (yr)"]
            st.bar_chart(med, height=min(420, 80 + 36 * len(med)))

    display_cols = [
        c
        for c in (
            "label",
            "still_waiting_n",
            "still_waiting_median_years",
            "still_waiting_mean_years",
            "eligible_n",
            "complete_n",
        )
        if c in waiting.columns
    ]
    st.markdown("**Stage detail (sorted by queue size)**")
    st.dataframe(
        waiting[display_cols].round(3),
        use_container_width=True,
        hide_index=True,
    )

    funnel_df = _funnel_stock_table(report.pathway_funnel)
    if not funnel_df.empty:
        st.markdown("**Pathway stock counts at horizon**")
        st.caption("Headline funnel stages — complements the waiting queues above.")
        fchart = funnel_df.set_index("label")[["count"]]
        st.bar_chart(fchart, height=min(360, 80 + 32 * len(fchart)))


def waiting_by_stage_replication_means(summary: Any) -> pd.DataFrame:
    """Mean still_waiting_n and still_waiting_median across Run 2 replications."""
    df = getattr(summary, "waits_stock_by_stage", None)
    if df is None or df.empty or "stat" not in df.columns:
        return pd.DataFrame()
    rows = []
    group_col = "stage" if "stage" in df.columns else "label"
    for key, stat_col in (("still_waiting_n", "mean"), ("still_waiting_median_days", "mean")):
        part = df.loc[df["stat"].astype(str) == key].copy()
        if part.empty:
            continue
        for _, r in part.iterrows():
            stage = r.get(group_col)
            label = r.get("label", stage)
            val = float(r.get("mean", np.nan))
            if key.endswith("_days"):
                val = val / DAYS_PER_YEAR
                metric = "still_waiting_median_years"
            else:
                metric = "still_waiting_n"
            rows.append({"stage": stage, "label": label, "metric": metric, "mean": val})
    if not rows:
        return pd.DataFrame()
    wide = pd.DataFrame(rows)
    pivot = wide.pivot_table(index=["stage", "label"], columns="metric", values="mean", aggfunc="first")
    return pivot.reset_index().sort_values("still_waiting_n", ascending=False, na_position="last")


def render_bottleneck_replication_summary(summary: Any, *, n_reps: int) -> None:
    """Run 2+: mean queue sizes across replications."""
    if n_reps <= 1:
        return
    table = waiting_by_stage_replication_means(summary)
    if table.empty:
        return
    st.markdown(f"**Mean queues across {n_reps} replications**")
    st.dataframe(table.round(3), use_container_width=True, hide_index=True)


def render_bottleneck_pair(
    baseline_report: Any,
    policy_report: Any,
    *,
    horizon_label: str,
    flow_window_days: float | None,
) -> None:
    """Run 3: baseline vs policy capacity and queues (rep 0, end of decay)."""
    st.markdown("### Bottleneck — baseline vs policy")
    st.caption(f"End of decay window · stock at **{horizon_label}** · replication **0** paired arms.")
    col_b, col_p = st.columns(2)
    with col_b:
        st.markdown("**Baseline (control)**")
        render_capacity_utilisation_metrics(_capacity_row(baseline_report))
        insight = _bottleneck_insight(
            _waiting_stage_table(baseline_report.waits_stock_by_stage),
            _capacity_row(baseline_report),
        )
        if insight:
            st.markdown(insight)
        w = _waiting_stage_table(baseline_report.waits_stock_by_stage)
        if not w.empty:
            st.dataframe(
                w[
                    [c for c in ("label", "still_waiting_n", "still_waiting_median_years") if c in w.columns]
                ].head(8).round(3),
                use_container_width=True,
                hide_index=True,
            )
    with col_p:
        st.markdown("**Policy**")
        render_capacity_utilisation_metrics(_capacity_row(policy_report))
        insight = _bottleneck_insight(
            _waiting_stage_table(policy_report.waits_stock_by_stage),
            _capacity_row(policy_report),
        )
        if insight:
            st.markdown(insight)
        w = _waiting_stage_table(policy_report.waits_stock_by_stage)
        if not w.empty:
            st.dataframe(
                w[
                    [c for c in ("label", "still_waiting_n", "still_waiting_median_years") if c in w.columns]
                ].head(8).round(3),
                use_container_width=True,
                hide_index=True,
            )
