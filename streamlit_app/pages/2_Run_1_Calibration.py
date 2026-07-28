"""Run 1 — calibration and model parameters."""

from typing import Any

import pandas as pd
import streamlit as st

from helpers import (
    DEFAULT_DURATION_ASSESSMENT,
    DEFAULT_DURATION_WORKSHOP_SESSION,
    DEFAULT_MONTHLY_REFERRALS,
    DEFAULT_WORKFORCE_HOURS_WORKSHOP_SESSION,
    DEFAULT_WORKSHOP_NUM_SESSIONS,
    DEFAULT_WORKSHOP_SESSION_INTERVAL_WEEKS,
    DAYS_PER_YEAR,
    WAIT_CALIBRATION_TARGET_KEYS,
    build_experiment_params,
    backlog_wait_snapshots_table,
    calibration_target_days_to_ui,
    calibration_target_ui_to_days,
    create_experiment,
    dataframe_wait_days_to_years,
    default_assessment_appointment_table,
    flow_kpi_columns,
    format_duration,
    init_session_state,
    is_wait_duration_column,
    parse_assessment_appointment_table,
    render_flow_kpi_history,
)

from kpi_display import calibration_target_label
from des.run_report import normalize_kpi_key
from des.runners import run1
from kpi_reporting import (
    planner_question,
    render_core_kpi_strip_from_row,
    render_run1_outcome_strip,
    render_session_status_sidebar,
)
from bottleneck_reporting import render_bottleneck_dashboard

RUN1_FLOW_INDEX = ("horizon_days", "years")

_WAIT_YR_DEFAULTS = {
    "backlog_mean_wait_days": 1600.0 / DAYS_PER_YEAR,
    "backlog_median_wait_days": 1500.0 / DAYS_PER_YEAR,
    "flow_wait_mean_days_assessments_started": 365.0 / DAYS_PER_YEAR,
    "flow_wait_median_days_assessments_started": 330.0 / DAYS_PER_YEAR,
    "flow_wait_mean_days_assessments_finished": 500.0 / DAYS_PER_YEAR,
    "flow_wait_median_days_assessments_finished": 450.0 / DAYS_PER_YEAR,
}

CALIBRATION_TARGET_DEFS: dict[str, dict[str, Any]] = {
    "backlog_patients_at_horizon": {
        "history_column": "backlog_patients_at_horizon",
        "kind": "stock",
        "definition": "Count of incomplete RTT pathways (backlog / PTL) at the horizon.",
        "default": 2800.0,
        "min": 100.0,
        "max": 10000.0,
        "step": 100.0,
    },
    "backlog_mean_wait_days": {
        "history_column": "backlog_mean_wait_days",
        "kind": "stock",
        "definition": "Mean RTT wait (referral → now) among the **backlog cohort** at the horizon.",
        "default": _WAIT_YR_DEFAULTS["backlog_mean_wait_days"],
        "min": 50.0 / DAYS_PER_YEAR,
        "max": 5000.0 / DAYS_PER_YEAR,
        "step": 0.05,
    },
    "backlog_median_wait_days": {
        "history_column": "backlog_median_wait_days",
        "kind": "stock",
        "definition": "Median RTT wait among the **backlog cohort** at the horizon.",
        "default": _WAIT_YR_DEFAULTS["backlog_median_wait_days"],
        "min": 50.0 / DAYS_PER_YEAR,
        "max": 5000.0 / DAYS_PER_YEAR,
        "step": 0.05,
    },
    "flow_wait_mean_days_assessments_started": {
        "history_column": "flow_wait_mean_days_assessments_started",
        "kind": "flow",
        "definition": "Mean wait referral → first assessment for patients **starting assessment** in the flow window.",
        "default": _WAIT_YR_DEFAULTS["flow_wait_mean_days_assessments_started"],
        "min": 30.0 / DAYS_PER_YEAR,
        "max": 2000.0 / DAYS_PER_YEAR,
        "step": 0.05,
    },
    "flow_wait_median_days_assessments_started": {
        "history_column": "flow_wait_median_days_assessments_started",
        "kind": "flow",
        "definition": "Median wait referral → first assessment for that **flow-window** cohort.",
        "default": _WAIT_YR_DEFAULTS["flow_wait_median_days_assessments_started"],
        "min": 30.0 / DAYS_PER_YEAR,
        "max": 2000.0 / DAYS_PER_YEAR,
        "step": 0.05,
    },
    "flow_wait_mean_days_assessments_finished": {
        "history_column": "flow_wait_mean_days_assessments_finished",
        "kind": "flow",
        "definition": "Mean wait referral → diagnosis for patients **finishing assessment** in the flow window.",
        "default": _WAIT_YR_DEFAULTS["flow_wait_mean_days_assessments_finished"],
        "min": 30.0 / DAYS_PER_YEAR,
        "max": 2500.0 / DAYS_PER_YEAR,
        "step": 0.05,
    },
    "flow_wait_median_days_assessments_finished": {
        "history_column": "flow_wait_median_days_assessments_finished",
        "kind": "flow",
        "definition": "Median wait referral → diagnosis for that **flow-window** cohort.",
        "default": _WAIT_YR_DEFAULTS["flow_wait_median_days_assessments_finished"],
        "min": 30.0 / DAYS_PER_YEAR,
        "max": 2500.0 / DAYS_PER_YEAR,
        "step": 0.05,
    },
}

for _cal_key, _cal_meta in CALIBRATION_TARGET_DEFS.items():
    _cal_meta["label"] = calibration_target_label(_cal_key, kind=_cal_meta["kind"])


def render_calibration_matching_kpi_guide() -> None:
    """Explain stock vs flow populations and list allowed matching targets."""
    st.markdown(
        "Choose **one KPI** as the **matching target**. Run 1 increases the simulation horizon in steps "
        "until that KPI is within **MAPE tolerance** of your provider value; that horizon becomes **T\\***."
    )
    with st.expander("Matching KPIs — stock vs flow (definitions)", expanded=True):
        st.markdown(
            """
**Stock KPI** — snapshot at the **horizon** (end of each calibration run)

| | |
|---|---|
| **Population** | Patients on an **incomplete RTT pathway** at the horizon — the **backlog / PTL** cohort (accepted referrals still in the system). |
| **Question answered** | “How big is the waiting list **right now** at this simulated year, and how long have those people waited **so far**?” |
| **Matching targets** | Backlog count; backlog **mean** or **median** RTT wait (shown in **years** in the UI). |

**Flow KPI** — **rolling window** ending at the horizon (**Flow window (days)** below)

| | |
|---|---|
| **Population** | Patients who **completed a milestone** during the window (e.g. **started assessment**, **finished assessment / diagnosis**) — not the whole backlog. |
| **Question answered** | “Among people who **recently** hit this step, what were **mean/median waits** referral → assessment or referral → diagnosis?” |
| **Matching targets** | Referral → assessment (mean/median); referral → diagnosis (mean/median) — **years** in the UI. |

Waits in tables and plots use **years** (÷ 365.25).
            """
        )
        st.markdown("**Allowed matching targets**")
        for meta in CALIBRATION_TARGET_DEFS.values():
            st.markdown(f"- **{meta['label']}** — {meta['definition']}")
        st.caption("Full KPI glossary: sidebar **Glossary** page.")


def render_calibration_history_data_dictionary(
    *,
    target_key: str,
    target_label: str,
    flow_window_days: float,
) -> None:
    """Column and row definitions for calibration history tables."""
    st.markdown(
        """
**What each row is:** one **calibration checkpoint** — a full simulation from day 0 to **horizon_days**
(**years**), with KPIs computed at that end date. Run 1 repeats with a longer horizon each step until the
**selected target** matches or the max search horizon is reached. **T\\*** is the chosen checkpoint (matched,
or lowest **mape** if none matched).
        """
    )
    st.markdown(
        f"""
**Your matching target for this run:** {target_label}

**Flow window for this run:** **{flow_window_days:.0f} days** (applies to all **flow** columns in the tables below).
        """
    )
    st.markdown(
        """
**Headline history table — columns**

| Column | Meaning |
|--------|---------|
| **horizon_days** | Simulation end for this checkpoint (days from t = 0). |
| **years** | Same horizon in years (horizon_days ÷ 365.25). |
| **mape** | Mean absolute percentage error vs your **single** matching target at this checkpoint. |
| **matched** | `True` if mape ≤ tolerance at this horizon. |
| **step_elapsed_s** / **elapsed_s** | Wall-clock time for this step / cumulative Run 1 time. |
| **Target column** | Simulated value of your selected matching KPI at this horizon. |
| **mape_…** | Percentage error for that target alone. |
| **backlog_patients_at_horizon** | **Stock** — PTL count at horizon. |
| **backlog_mean_wait_days** / **backlog_median_wait_days** | **Stock** — RTT wait among backlog cohort (table shows **years**). |
| **flow_wait_mean_days_assessments_started** / **…_median_…** | **Flow** — waits for assessment starts in the window (**years**). |
| **flow_wait_mean_days_assessments_finished** / **…_median_…** | **Flow** — waits referral → diagnosis for assessment completions in the window (**years**). |

**Flow counts & waits tab:** event **counts** in the window plus linked **mean/median** waits (wide format per checkpoint). Index columns **horizon_days** / **years** identify the row’s checkpoint.
        """
    )


def make_run1_progress_ui(status: st.delta_generator.DeltaGenerator):
    log = status.empty()

    def on_progress(event: dict[str, Any]) -> None:
        if event.get("event") == "step_start":
            status.update(
                label=(
                    f"Run 1 — horizon {event['horizon_days']:.0f} d "
                    f"({event['years']:.1f} yr) · {format_duration(event['elapsed_s'])}"
                )
            )
        elif event.get("event") == "step_done":
            backlog = event.get("backlog")
            backlog_txt = f"{backlog:.0f}" if backlog is not None else "—"
            matched = "✓ matched" if event.get("matched") else "continuing"
            log.markdown(
                f"- Step {event['step']} · {event['years']:.1f} yr · backlog **{backlog_txt}** · "
                f"MAPE **{event['mape']:.3f}** · {matched}"
            )
        elif event.get("event") == "complete":
            status.update(
                label=(
                    f"Run 1 complete — T*={event['t_star']:.0f} d · "
                    f"{format_duration(event['elapsed_s'])}"
                ),
                state="complete",
            )

    return on_progress


def render_calibration_convergence_plot(
    history: pd.DataFrame,
    *,
    target_key: str,
    target_value: float,
    t_star_days: float,
    matched: bool,
    tolerance: float,
) -> None:
    import plotly.graph_objects as go

    meta = CALIBRATION_TARGET_DEFS.get(target_key)
    if meta is None or meta["history_column"] not in history.columns:
        st.warning(f"Cannot plot calibration target `{target_key}`.")
        return

    col = meta["history_column"]
    plot_df = history.sort_values("years")
    t_star_years = t_star_days / 365.25
    y_series = plot_df[col].astype(float)
    target_y = float(target_value)
    y_label = meta["label"]
    if is_wait_duration_column(col):
        y_series = y_series / DAYS_PER_YEAR
        target_y = calibration_target_days_to_ui(target_key, target_value)
    fig = go.Figure()
    fig.add_hrect(
        y0=target_y * (1 - tolerance),
        y1=target_y * (1 + tolerance),
        fillcolor="rgba(46, 204, 113, 0.12)",
        line_width=0,
    )
    fig.add_hline(y=target_y, line_dash="dash", line_color="#e74c3c")
    fig.add_trace(
        go.Scatter(x=plot_df["years"], y=y_series, mode="lines+markers", name=y_label)
    )
    fig.add_vline(x=t_star_years, line_dash="dot", line_color="#27ae60")
    fig.update_layout(
        title=f"Calibration — {meta['label']} ({'matched' if matched else 'best MAPE'})",
        xaxis_title="Simulation horizon (years)",
        yaxis_title=meta["label"],
        height=480,
    )
    st.plotly_chart(fig, use_container_width=True)


init_session_state()
render_session_status_sidebar()

st.title("Run 1 — Calibration")
st.markdown(
    "Set **all model parameters**, choose a **calibration target KPI**, and find matching "
    "period **T\\*** — the horizon where that KPI matches the provider target. "
    "**Stock** targets use the PTL snapshot at the horizon; **flow** targets use mean/median waits "
    "in the **flow window** (referral → assessment or referral → diagnosis)."
)

st.markdown("---")
st.subheader("Model parameters")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("**Demand & triage**")
    monthly_referrals = st.number_input(
        "Monthly referrals",
        min_value=1.0,
        max_value=200.0,
        value=float(DEFAULT_MONTHLY_REFERRALS),
        step=1.0,
    )
    pct_referral_rejected = st.slider("Referral rejected (triage) %", 0.0, 0.95, 0.369)
    pct_admin_removal = st.slider("Admin removal %", 0.0, 0.95, 0.10)

with col2:
    st.markdown("**Capacity**")
    workforce_hours = st.number_input(
        "Clinician hours / weekday",
        min_value=1.0,
        max_value=50.0,
        value=7.0,
        step=1.0,
    )
    workforce_hours_workshop = st.number_input(
        "Clinician hours per workshop session",
        min_value=0.5,
        max_value=8.0,
        value=float(DEFAULT_WORKFORCE_HOURS_WORKSHOP_SESSION),
        step=0.5,
    )

with col3:
    st.markdown("**Pathway probabilities**")
    pct_diagnosis = st.slider("Diagnosis rate %", 0.0, 1.0, 0.75)
    pct_virtual = st.slider("Virtual support route %", 0.0, 1.0, 0.30)

st.markdown("---")
st.subheader("Assessment programme")

assess_col1, assess_col2 = st.columns(2)

with assess_col1:
    assessment_gap = st.number_input(
        "Days between assessment appointments",
        min_value=1,
        max_value=28,
        value=7,
        step=1,
    )
    st.caption("Triangular distribution for each appointment duration (hours)")
    dur_a1, dur_a2, dur_a3 = st.columns(3)
    with dur_a1:
        duration_assess_low = st.number_input(
            "Min hours", min_value=0.5, max_value=8.0, value=DEFAULT_DURATION_ASSESSMENT[0], step=0.5
        )
    with dur_a2:
        duration_assess_mode = st.number_input(
            "Mode hours", min_value=0.5, max_value=8.0, value=DEFAULT_DURATION_ASSESSMENT[1], step=0.5
        )
    with dur_a3:
        duration_assess_high = st.number_input(
            "Max hours", min_value=0.5, max_value=8.0, value=DEFAULT_DURATION_ASSESSMENT[2], step=0.5
        )

with assess_col2:
    st.markdown("**Assessment appointment mix**")
    st.caption(
        "Add or remove rows — each row is an appointment count and its probability. "
        "Probabilities are normalised to sum to 1.0."
    )
    appt_table = st.data_editor(
        default_assessment_appointment_table(),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="assessment_appt_editor",
        column_config={
            "appointments": st.column_config.NumberColumn(
                "Appointments",
                help="Number of assessment visits for this pathway variant",
                min_value=1,
                max_value=12,
                step=1,
                format="%d",
            ),
            "probability": st.column_config.NumberColumn(
                "Probability",
                help="Relative weight — normalised to sum to 1.0",
                min_value=0.0,
                max_value=1.0,
                step=0.01,
                format="%.2f",
            ),
        },
    )
    assessment_counts, assessment_probs, appt_messages = parse_assessment_appointment_table(
        appt_table
    )
    for msg in appt_messages:
        if "normalised" in msg.lower():
            st.info(msg)
        else:
            st.error(msg)

st.markdown("---")
st.subheader("Workshop programme")

ws_col1, ws_col2, ws_col3 = st.columns(3)

with ws_col1:
    workshop_group_size = st.number_input(
        "Workshop group size",
        min_value=2,
        max_value=20,
        value=8,
        step=1,
    )
    workshop_num_sessions = st.number_input(
        "Sessions per programme",
        min_value=1,
        max_value=12,
        value=DEFAULT_WORKSHOP_NUM_SESSIONS,
        step=1,
    )

with ws_col2:
    workshop_session_interval = st.number_input(
        "Weeks between sessions",
        min_value=1,
        max_value=4,
        value=DEFAULT_WORKSHOP_SESSION_INTERVAL_WEEKS,
        step=1,
    )
    workshop_max_wait = st.number_input(
        "Max days to form workshop group",
        min_value=7,
        max_value=90,
        value=28,
        step=1,
    )

with ws_col3:
    st.caption("Triangular distribution for workshop session duration (hours)")
    dur_w1, dur_w2, dur_w3 = st.columns(3)
    with dur_w1:
        duration_workshop_low = st.number_input(
            "Min", min_value=0.5, max_value=8.0, value=DEFAULT_DURATION_WORKSHOP_SESSION[0], step=0.5
        )
    with dur_w2:
        duration_workshop_mode = st.number_input(
            "Mode", min_value=0.5, max_value=8.0, value=DEFAULT_DURATION_WORKSHOP_SESSION[1], step=0.5
        )
    with dur_w3:
        duration_workshop_high = st.number_input(
            "Max", min_value=0.5, max_value=8.0, value=DEFAULT_DURATION_WORKSHOP_SESSION[2], step=0.5
        )

st.markdown("---")
st.subheader("Run 1 — calibration settings")
render_calibration_matching_kpi_guide()
st.markdown("")

target_keys = list(CALIBRATION_TARGET_DEFS.keys())
target_labels = [CALIBRATION_TARGET_DEFS[k]["label"] for k in target_keys]
default_target_key = "backlog_patients_at_horizon"
saved_target_key = normalize_kpi_key(
    st.session_state.get("run1_target_key", default_target_key)
)
if saved_target_key not in target_keys:
    saved_target_key = default_target_key
default_index = target_keys.index(saved_target_key)

c1, c2, c3, c4 = st.columns(4)
with c1:
    selected_index = st.selectbox(
        "Calibration target KPI",
        options=range(len(target_keys)),
        index=default_index,
        format_func=lambda i: target_labels[i],
        help=(
            "**Stock:** backlog count or backlog mean/median wait at horizon. "
            "**Flow:** mean/median wait for completions in the flow window below."
        ),
    )
    target_key = target_keys[selected_index]
    target_meta = CALIBRATION_TARGET_DEFS[target_key]
    if target_meta.get("kind") == "flow":
        st.caption("Flow target — uses **Flow window (days)** at each calibration step.")
with c2:
    _stored_target = st.session_state.get("run1_target_value")
    if _stored_target is not None:
        if target_key in WAIT_CALIBRATION_TARGET_KEYS:
            _target_ui_default = (
                float(_stored_target) / DAYS_PER_YEAR
                if float(_stored_target) > 100
                else float(_stored_target)
            )
        else:
            _target_ui_default = float(_stored_target)
    else:
        _target_ui_default = float(target_meta["default"])
    target_value = st.number_input(
        "Target value",
        min_value=float(target_meta["min"]),
        max_value=float(target_meta["max"]),
        value=float(_target_ui_default),
        step=float(target_meta["step"]),
    )
with c3:
    match_tolerance = st.slider("Match tolerance (MAPE)", 0.01, 0.20, 0.05, 0.01)
with c4:
    max_years = st.number_input("Max search horizon (years)", 5, 30, 20, 1)

step_days = st.selectbox("Horizon step (days)", [365, 182, 730], index=0)
flow_window = st.number_input("Flow window (days)", 30, 730, 365, 30)

appt_valid = assessment_counts is not None and assessment_probs is not None

if appt_valid:
    params = build_experiment_params(
        monthly_referrals=monthly_referrals,
        pct_referral_rejected=pct_referral_rejected,
        pct_admin_removal=pct_admin_removal,
        pct_diagnosis=pct_diagnosis,
        pct_virtual_support=pct_virtual,
        workforce_hours_per_day=workforce_hours,
        workforce_hours_workshop_session=workforce_hours_workshop,
        assessment_appointment_counts=assessment_counts,
        assessment_appointment_probs=assessment_probs,
        assessment_gap_days=assessment_gap,
        duration_assessment=[duration_assess_low, duration_assess_mode, duration_assess_high],
        workshop_group_size=workshop_group_size,
        workshop_num_sessions=workshop_num_sessions,
        workshop_session_interval_weeks=workshop_session_interval,
        workshop_max_wait_days=workshop_max_wait,
        duration_workshop_session=[duration_workshop_low, duration_workshop_mode, duration_workshop_high],
    )
    st.session_state["experiment_params"] = params
else:
    params = st.session_state.get("experiment_params")

st.markdown("---")

if st.button(
    "Run Run 1 — find T*",
    type="primary",
    use_container_width=True,
    disabled=not appt_valid,
):
    experiment = create_experiment(params)
    with st.status("Run 1 — calibration starting…", expanded=True) as status:
        on_progress = make_run1_progress_ui(status)
        target_days = calibration_target_ui_to_days(target_key, float(target_value))
        result = run1(
            experiment,
            targets={target_key: target_days},
            max_period_days=float(max_years * 365),
            step_days=float(step_days),
            min_period_days=365.0,
            match_tolerance=float(match_tolerance),
            flow_window_days=float(flow_window),
            rep=0,
            on_progress=on_progress,
        )

    st.session_state["run1_result"] = result
    st.session_state["run1_target_key"] = target_key
    st.session_state["run1_target_value"] = target_days
    st.session_state["t_star"] = result["optimal_matching_period_days"]
    st.rerun()

result = st.session_state.get("run1_result")
if result is not None:
    t_star = result["optimal_matching_period_days"]
    target_key = normalize_kpi_key(
        st.session_state.get("run1_target_key", default_target_key)
    )
    if target_key not in CALIBRATION_TARGET_DEFS:
        target_key = default_target_key
    target_label = CALIBRATION_TARGET_DEFS[target_key]["label"]
    raw_target = float(
        st.session_state.get("run1_target_value", CALIBRATION_TARGET_DEFS[target_key]["default"])
    )
    if target_key in WAIT_CALIBRATION_TARGET_KEYS:
        if raw_target > 100:
            target_value_days = raw_target
        else:
            target_value_days = raw_target * DAYS_PER_YEAR
        target_display = target_value_days / DAYS_PER_YEAR
    else:
        target_value_days = raw_target
        target_display = raw_target

    st.markdown(planner_question(1))
    render_run1_outcome_strip(
        t_star=t_star,
        matched=bool(result["matched"]),
        mape=float(result["minimum_mape"]),
        elapsed_s=float(result.get("elapsed_seconds", 0)),
        n_steps=result.get("n_steps", "?"),
        target_label=target_label,
        target_display=target_display,
    )

    history = result["history"]
    t_star_row = history.loc[history["horizon_days"] == t_star]
    if t_star_row.empty and result.get("best_checkpoint"):
        row = pd.DataFrame([result["best_checkpoint"]])
    elif not t_star_row.empty:
        row = t_star_row.tail(1)
    else:
        row = pd.DataFrame()

    if not row.empty:
        st.subheader("Core KPIs at T*")
        render_core_kpi_strip_from_row(
            row.iloc[0],
            horizon_label="T*",
            flow_window_days=float(result.get("flow_window_days", flow_window)),
        )

    report_at_t = result.get("report_at_t_star")
    if report_at_t is not None:
        st.markdown("---")
        render_bottleneck_dashboard(
            report_at_t,
            horizon_label=f"T* ({t_star:.0f} d)",
            flow_window_days=float(result.get("flow_window_days", flow_window)),
            replication_note="Single replication used for Run 1 calibration.",
        )
    elif not row.empty:
        st.info(
            "Re-run **Run 1 — find T\\*** to refresh the bottleneck panel "
            "(stage queues and assessment/workshop utilisation)."
        )

    backlog_at_t = backlog_wait_snapshots_table(row)
    if not backlog_at_t.empty:
        st.markdown("**Backlog waiting-time at T\\* (headline — years)**")
        st.caption(
            "Single row at **T\\***: **stock** backlog cohort — patient count and mean/median RTT wait "
            "(same population as stock matching targets)."
        )
        st.dataframe(backlog_at_t.round(3), use_container_width=True, hide_index=True)

    if not flow_kpi_columns(history):
        st.warning(
            "This calibration result has **no flow KPI columns**. "
            "Click **Run Run 1 — find T\\*** below to refresh. If it persists after re-running, "
            "restart Streamlit from the project repo so the app loads `des` from source, "
            "not an outdated install."
        )

    st.markdown("**Calibration convergence**")
    render_calibration_convergence_plot(
        history,
        target_key=target_key,
        target_value=target_value_days,
        t_star_days=t_star,
        matched=bool(result["matched"]),
        tolerance=float(result["match_tolerance"]),
    )

    target_col = CALIBRATION_TARGET_DEFS[target_key]["history_column"]
    hist_cols = [
        "horizon_days",
        "years",
        "mape",
        "matched",
        "step_elapsed_s",
        "elapsed_s",
        target_col,
        f"mape_{target_key}",
        "backlog_patients_at_horizon",
        "backlog_mean_wait_days",
        "backlog_median_wait_days",
        "flow_wait_mean_days_assessments_started",
        "flow_wait_median_days_assessments_started",
        "flow_wait_mean_days_assessments_finished",
        "flow_wait_median_days_assessments_finished",
    ]
    display_cols = list(dict.fromkeys(c for c in hist_cols if c in history.columns))

    with st.expander("Analyst detail — calibration history", expanded=False):
        render_calibration_history_data_dictionary(
            target_key=target_key,
            target_label=target_label,
            flow_window_days=float(result.get("flow_window_days", flow_window)),
        )
        tab_headline, tab_flow = st.tabs(["Headline KPIs", "Flow counts & waits"])
        with tab_headline:
            st.markdown("**Calibration history (yearly checkpoints)**")
            headline = dataframe_wait_days_to_years(history[display_cols])
            st.dataframe(headline.round(3), use_container_width=True)
        with tab_flow:
            st.markdown(
                "At each calibration **run** (0 → horizon), KPIs use the **flow window (days)** "
                "set above — event counts plus mean/median waits for linked stages."
            )
            render_flow_kpi_history(
                history,
                index_cols=RUN1_FLOW_INDEX,
                flow_window_days=float(result.get("flow_window_days", flow_window)),
                wide_only=True,
            )

    if not result["matched"]:
        st.warning("No exact match within tolerance — using best MAPE checkpoint as T*.")
