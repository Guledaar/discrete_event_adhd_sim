"""Run 2 — stochastic baseline at T*."""

from typing import Any

import pandas as pd
import streamlit as st

from helpers import (
    create_experiment,
    format_duration,
    init_session_state,
    replication_wait_summary_rows,
    replication_wait_summary_to_years,
    require_t_star,
    run_report_tables_in_years,
    dataframe_wait_days_to_years,
)

from des.run_report import run_report_summary
from des.runners import run2
from kpi_reporting import (
    planner_question,
    render_run2_baseline_headline_kpis,
    render_session_status_sidebar,
)


def make_run2_progress_ui(status, progress_bar):
    log = status.empty()

    def on_progress(event: dict[str, Any]) -> None:
        et = event.get("event")
        if et == "start":
            progress_bar.progress(0.0)
        elif et == "rep_done":
            progress_bar.progress(event["rep"] / event["n_reps"])
            backlog = event.get("backlog")
            log.markdown(f"- Rep {event['rep']}/{event['n_reps']} · backlog {backlog or '—'}")
        elif et == "complete":
            progress_bar.progress(1.0)
            status.update(
                label=f"Run 2 complete · {format_duration(event['elapsed_s'])}",
                state="complete",
            )

    return on_progress


init_session_state()
render_session_status_sidebar()

st.title("Run 2 — Stochastic Baseline")
st.markdown(
    "Run **multiple replications** at calibrated **T\\*** to quantify uncertainty "
    "in baseline KPIs (mean, SD, 95% CI). Reports include **stock** waits at horizon "
    "and **flow-window** event counts with mean/median wait times."
)

t_star = require_t_star()
if t_star is None:
    st.stop()

params = st.session_state.get("experiment_params")
if params is None:
    st.error("Model parameters not set. Go to Run 1 and configure parameters first.")
    st.stop()

st.markdown("---")
st.subheader("Run 2 settings")

c1, c2, c3 = st.columns(3)
with c1:
    n_reps = st.number_input("Number of replications", min_value=1, max_value=20, value=5, step=1)
with c2:
    flow_window = st.number_input("Flow window (days)", 30, 730, 365, 30, key="run2_flow")
with c3:
    n_jobs = st.selectbox("Parallel jobs", [-1, 1, 2, 4], index=0)
st.caption(
    "Live rep-by-rep progress is shown when **Parallel jobs = 1**. "
    "Higher parallelism is faster but only shows a summary when finished."
)

st.markdown("---")

if st.button("Run Run 2 — baseline at T*", type="primary", use_container_width=True):
    experiment = create_experiment(params)
    show_rep_progress = int(n_jobs) == 1
    if show_rep_progress:
        with st.status(
            f"Run 2 — starting {n_reps} replication(s) at T*={t_star:.0f} d…",
            expanded=True,
        ) as status:
            progress_bar = st.progress(0.0)
            on_progress = make_run2_progress_ui(status, progress_bar)
            result = run2(
                experiment,
                matching_period_days=t_star,
                n_reps=int(n_reps),
                warm_up=0,
                flow_window_days=float(flow_window),
                n_jobs=1,
                on_progress=on_progress,
            )
    else:
        with st.spinner(f"Running {n_reps} replications in parallel at T*={t_star:.0f} d…"):
            result = run2(
                experiment,
                matching_period_days=t_star,
                n_reps=int(n_reps),
                warm_up=0,
                flow_window_days=float(flow_window),
                n_jobs=int(n_jobs),
            )
    st.session_state["run2_result"] = result
    st.rerun()

result = st.session_state.get("run2_result")
if result is None:
    st.info("Click **Run Run 2** to execute the baseline analysis.")
    st.stop()

summary = result["summary"]
snapshots = result["kpi_snapshots"]
flow_window_days = float(result.get("flow_window_days", 365))
SUMMARY_COLS = ["stat", "n", "mean", "sd", "ci_lower", "ci_upper"]


def _display_wait_summary(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    return replication_wait_summary_to_years(replication_wait_summary_rows(df, group_col))

st.success(
    f"Completed **{result['n_reps']}** replications at T* = {t_star:.0f} d · "
    f"runtime {format_duration(result.get('elapsed_seconds', 0))}"
)

st.markdown(planner_question(2))
st.subheader("Headline KPIs at T* (baseline uncertainty)")
render_run2_baseline_headline_kpis(
    snapshots,
    result.get("flow_kpi_summary"),
    n_reps=int(result["n_reps"]),
    flow_window_days=flow_window_days,
)

st.markdown("---")
with st.expander("Analyst detail — summarised tables (mean / SD / 95% CI)", expanded=False):
    tab0, tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        [
            "Backlog / PTL — RTT waits",
            "RTT waits at horizon",
            "18 / 52-week breaches",
            "Waits at horizon (by stage)",
            "Waits for recent completions",
            "Pathway activity (flow window)",
            "Flow counts and waits (rep 0)",
        ]
    )

    with tab0:
        st.caption("Backlog cohort RTT wait — mean and median (years) across replications.")
        backlog_rtt = summary.rtt_waits_stock.copy()
        if "cohort" in backlog_rtt.columns:
            backlog_rtt = backlog_rtt[backlog_rtt["cohort"].astype(str) == "backlog"]
        st.dataframe(_display_wait_summary(backlog_rtt, "cohort").round(3))

    with tab1:
        st.caption("Mean and median RTT wait (years) across replications.")
        st.dataframe(_display_wait_summary(summary.rtt_waits_stock, "cohort").round(3))

    with tab2:
        cols = ["cohort", *SUMMARY_COLS]
        st.dataframe(
            summary.rtt_breaches_stock[[c for c in cols if c in summary.rtt_breaches_stock.columns]].round(1)
        )

    with tab3:
        st.caption("Stock (horizon) stage waits — completed and still waiting mean / median (years).")
        st.dataframe(_display_wait_summary(summary.waits_stock_by_stage, "stage").round(3))

    with tab4:
        st.caption("Completions in the flow window — mean and median wait (years).")
        st.dataframe(_display_wait_summary(summary.waits_flow_by_stage, "stage").round(3))

    with tab5:
        cols = ["metric", *SUMMARY_COLS]
        st.dataframe(summary.activity_flow[[c for c in cols if c in summary.activity_flow.columns]].round(1))

    with tab6:
        if result["results"]:
            combined = run_report_tables_in_years(run_report_summary(result["results"][0][3]))[
                "flow_counts_and_waits"
            ]
            st.caption(
                f"Labeled flow table for replication 0 · flow window {flow_window_days:.0f} d "
                "ending at T* (waits in years)."
            )
            st.dataframe(combined.round(3), use_container_width=True)
        else:
            st.info("No replication data.")

    st.markdown("**Headline KPI snapshots (all replications)**")
    st.dataframe(dataframe_wait_days_to_years(snapshots).round(3), use_container_width=True)
