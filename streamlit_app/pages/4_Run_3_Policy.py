"""Run 3 — policy switch and backlog decay."""

from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st

from helpers import (
    DEFAULT_DURATION_ASSESSMENT,
    DEFAULT_WORKING_DAYS_PER_MONTH,
    create_experiment,
    flow_kpi_columns,
    format_duration,
    init_session_state,
    parse_assessment_appointment_table,
    render_backlog_waiting_time_from_run_report,
    render_flow_kpi_history,
    require_t_star,
    run3_for_streamlit,
    run_report_tables_in_years,
    dataframe_wait_days_to_years,
)

from run3_decay_charts import decay_scenario_runs_from_result, render_run3_decay_period_charts
from kpi_display import streamlit_kpi_label
from kpi_reporting import (
    planner_question,
    render_end_of_decay_core_compare,
    render_run3_decision_strip,
    render_session_status_sidebar,
)
from bottleneck_reporting import render_bottleneck_dashboard, render_bottleneck_pair

from des.run_report import run_report_summary


POLICY_COLORS = ["#2980b9", "#e74c3c", "#9b59b6", "#f39c12", "#1abc9c", "#e67e22"]

POLICY_PARAMETER_DEFS: dict[str, dict[str, Any]] = {
    "monthly_referrals": {
        "label": "Monthly referrals (demand)",
        "group": "Demand / triage",
        "type": "float",
        "min": 1.0,
        "max": 200.0,
        "step": 1.0,
        "to_override": lambda v: {"iat": 1.0 / (v / DEFAULT_WORKING_DAYS_PER_MONTH)},
        "from_baseline": lambda p: (1.0 / p["iat"]) * DEFAULT_WORKING_DAYS_PER_MONTH,
    },
    "workforce_hours_per_day": {
        "label": "Clinician hours per weekday",
        "group": "Capacity",
        "type": "float",
        "min": 0.0,
        "max": 50.0,
        "step": 1.0,
        "to_override": lambda v: {"workforce_hours_per_day": float(v)},
        "from_baseline": lambda p: p["workforce_hours_per_day"],
    },
    "workforce_hours_workshop_session": {
        "label": "Workshop session hours",
        "group": "Capacity",
        "type": "float",
        "min": 0.5,
        "max": 8.0,
        "step": 0.5,
        "to_override": lambda v: {"workforce_hours_workshop_session": float(v)},
        "from_baseline": lambda p: p["workforce_hours_workshop_session"],
    },
    "pct_referral_rejected": {
        "label": "Referral rejected at triage",
        "group": "Demand / triage",
        "type": "float",
        "min": 0.0,
        "max": 0.95,
        "step": 0.01,
        "to_override": lambda v: {"pct_referral_rejected": float(v)},
        "from_baseline": lambda p: p["pct_referral_rejected"],
    },
    "pct_admin_removal": {
        "label": "Admin removal rate",
        "group": "Demand / triage",
        "type": "float",
        "min": 0.0,
        "max": 0.95,
        "step": 0.01,
        "to_override": lambda v: {"pct_admin_removal": float(v)},
        "from_baseline": lambda p: p["pct_admin_removal"],
    },
    "pct_diagnosis": {
        "label": "Diagnosis rate",
        "group": "Pathway",
        "type": "float",
        "min": 0.0,
        "max": 1.0,
        "step": 0.01,
        "to_override": lambda v: {"pct_diagnosis": float(v)},
        "from_baseline": lambda p: p["pct_diagnosis"],
    },
    "pct_virtual_support": {
        "label": "Virtual support route",
        "group": "Pathway",
        "type": "float",
        "min": 0.0,
        "max": 1.0,
        "step": 0.01,
        "to_override": lambda v: {"pct_virtual_support": float(v)},
        "from_baseline": lambda p: p["pct_virtual_support"],
    },
    "assessment_gap_days": {
        "label": "Days between assessment appointments",
        "group": "Assessment",
        "type": "int",
        "min": 1,
        "max": 28,
        "step": 1,
        "to_override": lambda v: {"assessment_gap_days": int(v)},
        "from_baseline": lambda p: p["assessment_gap_days"],
    },
    "assessment_programme": {
        "label": "Assessment programme (appointment mix, probabilities, duration)",
        "group": "Assessment",
        "type": "assessment_programme",
        "duration_step": 0.5,
        "duration_bounds": (0.5, 8.0),
        "from_baseline": lambda p: {
            "counts": list(p["assessment_appointment_counts"]),
            "probs": list(p["assessment_appointment_probs"]),
            "duration": list(p["duration_assessment"]),
        },
        "to_override": lambda v: {
            "assessment_appointment_counts": v["counts"],
            "assessment_appointment_probs": v["probs"],
            "duration_assessment": [float(v["duration"][0]), float(v["duration"][1]), float(v["duration"][2])],
        },
    },
    "workshop_group_size": {
        "label": "Workshop group size",
        "group": "Workshops",
        "type": "int",
        "min": 2,
        "max": 20,
        "step": 1,
        "to_override": lambda v: {"workshop_group_size": int(v)},
        "from_baseline": lambda p: p["workshop_group_size"],
    },
    "workshop_num_sessions": {
        "label": "Workshop sessions per programme",
        "group": "Workshops",
        "type": "int",
        "min": 1,
        "max": 12,
        "step": 1,
        "to_override": lambda v: {"workshop_num_sessions": int(v)},
        "from_baseline": lambda p: p["workshop_num_sessions"],
    },
    "workshop_session_interval_weeks": {
        "label": "Weeks between workshop sessions",
        "group": "Workshops",
        "type": "int",
        "min": 1,
        "max": 4,
        "step": 1,
        "to_override": lambda v: {"workshop_session_interval_weeks": int(v)},
        "from_baseline": lambda p: p["workshop_session_interval_weeks"],
    },
    "workshop_max_wait_days": {
        "label": "Max wait to form workshop group (days)",
        "group": "Workshops",
        "type": "int",
        "min": 7,
        "max": 90,
        "step": 1,
        "to_override": lambda v: {"workshop_max_wait_days": int(v)},
        "from_baseline": lambda p: p["workshop_max_wait_days"],
    },
}


def _assessment_appt_table_from_params(params: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "appointments": params["assessment_appointment_counts"],
            "probability": params["assessment_appointment_probs"],
        }
    )


def make_run3_progress_ui(status):
    log = status.empty()

    def on_progress(event: dict[str, Any]) -> None:
        et = event.get("event")
        n_reps = event.get("n_reps", 1)
        if et == "rep_start":
            arm = "Baseline" if event.get("arm") == "baseline_control" else "Policy"
            log.markdown(f"**{arm}** rep {event['rep']}/{event['n_reps']}")
        elif et == "rep_done":
            log.markdown(
                f"- rep {event['rep']}/{event['n_reps']} · decay {event.get('backlog_decay', 0):+.0f}"
            )
        elif et == "complete":
            status.update(
                label=f"Run 3 complete · {format_duration(event['elapsed_s'])} · {n_reps} rep(s)/arm",
                state="complete",
            )

    return on_progress


def baseline_policy_table(params: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for k, m in POLICY_PARAMETER_DEFS.items():
        raw = m["from_baseline"](params)
        if m.get("type") == "assessment_programme":
            display = (
                f"counts {raw['counts']}, probs {[round(float(p), 2) for p in raw['probs']]}; "
                f"duration (min/mode/max h) {raw['duration']}"
            )
        elif m.get("type") == "triangular_hours":
            display = f"{raw[0]:g}, {raw[1]:g}, {raw[2]:g} (triangular h)"
        else:
            display = raw
        rows.append(
            {
                "parameter": k,
                "label": m["label"],
                "group": m["group"],
                "baseline_value": display,
            }
        )
    return pd.DataFrame(rows)


def render_policy_parameter_inputs(params: dict[str, Any], selected_keys: list[str]) -> None:
    if not selected_keys:
        return
    for key in selected_keys:
        meta = POLICY_PARAMETER_DEFS[key]
        if meta.get("type") == "assessment_programme":
            st.markdown(f"**{meta['label']}**")
            st.caption(
                "Edit appointment counts and probabilities (normalised to sum to 1). "
                "Set triangular **duration** (hours) per appointment — applied at T*."
            )
            appt_table = st.data_editor(
                _assessment_appt_table_from_params(params),
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                key="policy_assessment_appt_editor",
                column_config={
                    "appointments": st.column_config.NumberColumn(
                        "Appointments",
                        min_value=1,
                        max_value=12,
                        step=1,
                        format="%d",
                    ),
                    "probability": st.column_config.NumberColumn(
                        "Probability",
                        min_value=0.0,
                        max_value=1.0,
                        step=0.01,
                        format="%.2f",
                    ),
                },
            )
            _counts, _probs, appt_msgs = parse_assessment_appointment_table(appt_table)
            st.session_state["policy_assessment_appt_table_df"] = appt_table
            for msg in appt_msgs:
                if "normalised" in msg.lower():
                    st.info(msg)
                else:
                    st.error(msg)
            base = meta["from_baseline"](params)
            dur = base["duration"] if len(base.get("duration", [])) >= 3 else DEFAULT_DURATION_ASSESSMENT
            lo, hi = meta["duration_bounds"]
            step = float(meta["duration_step"])
            st.caption("Triangular duration per assessment visit (clinician-hours)")
            d1, d2, d3 = st.columns(3)
            with d1:
                st.number_input(
                    "Min (hours)",
                    min_value=lo,
                    max_value=hi,
                    value=float(dur[0]),
                    step=step,
                    key="policy_val_assessment_programme_d0",
                )
            with d2:
                st.number_input(
                    "Mode (hours)",
                    min_value=lo,
                    max_value=hi,
                    value=float(dur[1]),
                    step=step,
                    key="policy_val_assessment_programme_d1",
                )
            with d3:
                st.number_input(
                    "Max (hours)",
                    min_value=lo,
                    max_value=hi,
                    value=float(dur[2]),
                    step=step,
                    key="policy_val_assessment_programme_d2",
                )
            continue
        if meta.get("type") == "triangular_hours":
            da = meta["from_baseline"](params)
            if len(da) < 3:
                da = list(DEFAULT_DURATION_ASSESSMENT)
            st.markdown(f"**{meta['label']}**")
            c1, c2, c3 = st.columns(3)
            step = float(meta["step"])
            with c1:
                lo, hi = meta["bounds"]["min"]
                st.number_input(
                    "Min (hours)",
                    min_value=lo,
                    max_value=hi,
                    value=float(da[0]),
                    step=step,
                    key=f"policy_val_{key}_0",
                )
            with c2:
                lo, hi = meta["bounds"]["mode"]
                st.number_input(
                    "Mode (hours)",
                    min_value=lo,
                    max_value=hi,
                    value=float(da[1]),
                    step=step,
                    key=f"policy_val_{key}_1",
                )
            with c3:
                lo, hi = meta["bounds"]["max"]
                st.number_input(
                    "Max (hours)",
                    min_value=lo,
                    max_value=hi,
                    value=float(da[2]),
                    step=step,
                    key=f"policy_val_{key}_2",
                )
            continue
        baseline = float(meta["from_baseline"](params))
        st.number_input(
            meta["label"],
            min_value=int(meta["min"]) if meta["type"] == "int" else float(meta["min"]),
            max_value=int(meta["max"]) if meta["type"] == "int" else float(meta["max"]),
            value=int(round(baseline)) if meta["type"] == "int" else baseline,
            step=int(meta["step"]) if meta["type"] == "int" else float(meta["step"]),
            key=f"policy_val_{key}",
        )


def build_policy_overrides_from_ui(params: dict[str, Any], selected_keys: list[str]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for key in selected_keys:
        meta = POLICY_PARAMETER_DEFS[key]
        if meta.get("type") == "assessment_programme":
            table = st.session_state.get("policy_assessment_appt_table_df")
            if table is None:
                table = st.session_state.get("policy_assessment_appt_editor")
            if table is None:
                table = _assessment_appt_table_from_params(params)
            counts, probs, _msgs = parse_assessment_appointment_table(table)
            if counts is None or probs is None:
                continue
            base = meta["from_baseline"](params)
            dur = base["duration"] if len(base.get("duration", [])) >= 3 else DEFAULT_DURATION_ASSESSMENT
            duration = [
                st.session_state.get("policy_val_assessment_programme_d0", dur[0]),
                st.session_state.get("policy_val_assessment_programme_d1", dur[1]),
                st.session_state.get("policy_val_assessment_programme_d2", dur[2]),
            ]
            overrides.update(
                meta["to_override"]({"counts": counts, "probs": probs, "duration": duration})
            )
            continue
        if meta.get("type") == "triangular_hours":
            da = meta["from_baseline"](params)
            if len(da) < 3:
                da = list(DEFAULT_DURATION_ASSESSMENT)
            val = [
                st.session_state.get(f"policy_val_{key}_0", da[0]),
                st.session_state.get(f"policy_val_{key}_1", da[1]),
                st.session_state.get(f"policy_val_{key}_2", da[2]),
            ]
            overrides.update(meta["to_override"](val))
            continue
        val = st.session_state.get(f"policy_val_{key}", meta["from_baseline"](params))
        overrides.update(meta["to_override"](val))
    return overrides


def _metric_ci(
    ms: pd.DataFrame | None,
    metric: str,
    digits: int = 0,
    *,
    scale: float = 1.0,
) -> str:
    if ms is None or ms.empty or "metric" not in ms.columns:
        return "—"
    idx = ms.set_index("metric")
    if metric not in idx.index:
        return "—"
    row = idx.loc[metric]
    if "mean" not in row.index:
        return "—"
    mean = float(row["mean"]) * scale
    if int(row.get("n", 0)) <= 1:
        return f"{mean:.{digits}f}"
    if "ci_lower" not in row.index or "ci_upper" not in row.index:
        return f"{mean:.{digits}f}"
    lo = float(row["ci_lower"]) * scale
    hi = float(row["ci_upper"]) * scale
    return f"{mean:.{digits}f} ({lo:.{digits}f}–{hi:.{digits}f})"


def reset_all_run3_scenarios() -> None:
    """Clear scenario library, comparison selection, and last run (fresh planning session)."""
    st.session_state["run3_scenario_runs"] = []
    st.session_state["run3_compare_ids"] = []
    st.session_state["run3_recorded_run_uids"] = []
    st.session_state["run3_result"] = None
    st.session_state.pop("run3_last_policy_label", None)
    st.session_state.pop("run3_overrides", None)
    st.session_state.pop("run3_elapsed", None)


def _scenario_library() -> list[dict[str, Any]]:
    runs = st.session_state.setdefault("run3_scenario_runs", [])
    for r in runs:
        if "scenario_id" not in r:
            r["scenario_id"] = f"legacy_{uuid4().hex[:8]}"
    return runs


def _sync_compare_ids_with_library() -> None:
    valid = {r["scenario_id"] for r in _scenario_library()}
    selected = st.session_state.get("run3_compare_ids") or []
    st.session_state["run3_compare_ids"] = [i for i in selected if i in valid]


def record_run3_scenarios(
    result: dict[str, Any],
    *,
    policy_label: str,
    decay_years: int,
    run_uid: str,
) -> list[str]:
    """Append baseline (if any) and policy from one Run 3 result. Returns new scenario ids."""
    runs = _scenario_library()
    decay_tag = f"{decay_years}yr"
    decay_days = float(result["decay_period_days"])
    n_reps = int(result.get("n_reps", 1))
    labels = [r["label"] for r in runs]
    new_ids: list[str] = []

    if result.get("control_summary"):
        cs = result["control_summary"]
        runs[:] = [r for r in runs if not r.get("is_baseline")]
        baseline_id = f"baseline_{uuid4().hex[:8]}"
        runs.insert(
            0,
            {
                "scenario_id": baseline_id,
                "source_run_uid": run_uid,
                "label": f"Baseline (no change, {decay_tag})",
                "is_baseline": True,
                "n_reps": int(result.get("control_n_reps", n_reps)),
                "decay_days": decay_days,
                "decay_years": decay_years,
                "metrics_summary": cs["metrics_summary"],
                "series": cs["kpi_time_series"],
            },
        )
        new_ids.append(baseline_id)
        labels = [r["label"] for r in runs]

    ps = result["policy_summary"]
    label = policy_label if policy_label not in labels else f"{policy_label}_{len(runs)}"
    policy_id = f"policy_{uuid4().hex[:8]}"
    runs.append(
        {
            "scenario_id": policy_id,
            "source_run_uid": run_uid,
            "label": f"{label} ({decay_tag})",
            "is_baseline": False,
            "n_reps": n_reps,
            "decay_days": decay_days,
            "decay_years": decay_years,
            "metrics_summary": ps["metrics_summary"],
            "series": ps["kpi_time_series"],
        }
    )
    new_ids.append(policy_id)

    recorded = st.session_state.setdefault("run3_recorded_run_uids", [])
    if run_uid not in recorded:
        recorded.append(run_uid)

    compare = st.session_state.setdefault("run3_compare_ids", [])
    for sid in new_ids:
        if sid not in compare:
            compare.append(sid)
    return new_ids


def remove_run3_scenario(scenario_id: str) -> None:
    runs = _scenario_library()
    st.session_state["run3_scenario_runs"] = [r for r in runs if r.get("scenario_id") != scenario_id]
    _sync_compare_ids_with_library()


def scenarios_for_compare() -> list[dict[str, Any]]:
    runs = _scenario_library()
    selected: list[str] = st.session_state.get("run3_compare_ids") or []
    if not selected:
        return runs
    by_id = {r["scenario_id"]: r for r in runs}
    return [by_id[i] for i in selected if i in by_id]


def render_scenario_library_controls() -> None:
    runs = _scenario_library()
    st.subheader("Scenario library")
    st.caption(
        "After a simulation finishes, use **Record scenario** to save it here. "
        "Pick which saved scenarios appear in comparison charts and tables below."
    )

    c_reset, c_record = st.columns([1, 1])
    with c_reset:
        if st.button(
            "Reset all scenarios",
            type="secondary",
            use_container_width=True,
            help="Clears the library, comparison selection, and last run summary.",
        ):
            reset_all_run3_scenarios()
            st.rerun()

    last_result = st.session_state.get("run3_result")
    run_uid = (last_result or {}).get("_run_uid")
    recorded_uids = st.session_state.get("run3_recorded_run_uids") or []
    already_recorded = run_uid is not None and run_uid in recorded_uids
    with c_record:
        if last_result is None:
            st.button("Record last run to library", disabled=True, use_container_width=True)
        elif already_recorded:
            st.button("Recorded ✓", disabled=True, use_container_width=True)
        elif st.button("Record last run to library", type="primary", use_container_width=True):
            policy_label = st.session_state.get("run3_last_policy_label", "Policy")
            decay_years = int(round(float(last_result.get("decay_period_days", 365)) / 365))
            record_run3_scenarios(
                last_result,
                policy_label=policy_label,
                decay_years=decay_years,
                run_uid=str(run_uid),
            )
            st.rerun()

    if not runs:
        st.info("No scenarios recorded yet. Run a policy, then click **Record last run to library**.")
        return

    id_to_label = {r["scenario_id"]: r["label"] for r in runs}
    _sync_compare_ids_with_library()
    if not st.session_state.get("run3_compare_ids") and id_to_label:
        st.session_state["run3_compare_ids"] = list(id_to_label.keys())
    st.multiselect(
        "Scenarios to compare (charts & table)",
        options=list(id_to_label.keys()),
        format_func=lambda sid: id_to_label.get(sid, sid),
        key="run3_compare_ids",
        help="Always include **Baseline** when comparing policies. Dashed line = baseline on charts.",
    )

    lib_rows = []
    for r in runs:
        lib_rows.append(
            {
                "Label": r["label"],
                "Type": "Baseline" if r.get("is_baseline") else "Policy",
                "Reps": r.get("n_reps", 1),
                "Decay (yr)": r.get("decay_years"),
                "In comparison": r["scenario_id"] in (st.session_state.get("run3_compare_ids") or []),
            }
        )
    st.dataframe(pd.DataFrame(lib_rows), use_container_width=True, hide_index=True)

    with st.expander("Remove individual scenarios", expanded=False):
        for r in runs:
            col_label, col_btn = st.columns([4, 1])
            with col_label:
                st.text(r["label"])
            with col_btn:
                sid = r["scenario_id"]
                if st.button("Remove", key=f"run3_rm_{sid}"):
                    remove_run3_scenario(sid)
                    st.rerun()


def render_run3_kpi_comparison_charts(scenario_runs: list[dict]) -> None:
    render_run3_decay_period_charts(scenario_runs)


def render_run3_scenario_comparison_table(scenario_runs: list[dict]) -> None:
    metric_specs: tuple[tuple[str, int, float | None], ...] = (
        ("backlog_decay", 0, None),
        ("backlog_at_end", 0, None),
        ("backlog_mean_wait_days", 2, 1 / 365.25),
        ("backlog_median_wait_days", 2, 1 / 365.25),
        ("flow_count_assessments_finished", 0, None),
        ("flow_wait_mean_days_assessments_finished", 2, 1 / 365.25),
        ("flow_wait_median_days_assessments_finished", 2, 1 / 365.25),
    )
    rows = []
    for run in scenario_runs:
        ms = run.get("metrics_summary")
        row: dict[str, Any] = {
            "Scenario": run["label"],
            "Reps": run.get("n_reps", 1),
            "Decay (yr)": run.get("decay_years"),
        }
        for key, digits, scale in metric_specs:
            row[streamlit_kpi_label(key)] = _metric_ci(
                ms, key, digits, scale=scale if scale is not None else 1.0
            )
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_run3_last_run_summary(result: dict[str, Any]) -> None:
    n_reps = int(result.get("n_reps", 1))
    st.subheader("Last run — operational summary")
    if result.get("elapsed_seconds") is not None:
        d = float(result.get("decay_period_days", 0))
        st.caption(
            f"{format_duration(result['elapsed_seconds'])} · "
            f"decay {int(round(d / 365))} yr · {n_reps} rep(s)/arm"
        )
    st.markdown(planner_question(3))
    render_run3_decision_strip(result)
    render_end_of_decay_core_compare(result)

    ctrl = (result.get("control_replications") or [{}])[0]
    pol = (result.get("policy_replications") or [{}])[0]
    ctrl_report = ctrl.get("report")
    pol_report = pol.get("report")
    end_horizon = float(result.get("matching_period_days", 0)) + float(
        result.get("decay_period_days", 0)
    )
    fw = float(result.get("flow_window_days", 365))
    if ctrl_report is not None and pol_report is not None:
        st.markdown("---")
        render_bottleneck_pair(
            ctrl_report,
            pol_report,
            horizon_label=f"end of decay ({end_horizon:.0f} d)",
            flow_window_days=fw,
        )
    elif pol_report is not None:
        st.markdown("---")
        render_bottleneck_dashboard(
            pol_report,
            horizon_label=f"end of decay ({end_horizon:.0f} d)",
            flow_window_days=fw,
        )

    with st.expander("Analyst detail — arm snapshots, backlog report, flow tables", expanded=False):
        for title, key in [("Baseline", "control_summary"), ("Policy", "policy_summary")]:
            summary = result.get(key)
            if summary is not None and not summary["snapshots"].empty:
                snap = summary["snapshots"]
                fw = float(result.get("flow_window_days", 365))
                st.markdown(f"**{title} — headline snapshots**")
                headline_cols = [c for c in snap.columns if not str(c).startswith("flow_")]
                st.dataframe(dataframe_wait_days_to_years(snap[headline_cols]).round(3), use_container_width=True)
                if flow_kpi_columns(snap):
                    st.markdown(f"**{title} — flow window at end of decay**")
                    render_flow_kpi_history(
                        snap,
                        index_cols=("rep",) if "rep" in snap.columns else (),
                        flow_window_days=fw,
                    )
        for arm_title, reps_key in [
            ("Baseline", "control_replications"),
            ("Policy", "policy_replications"),
        ]:
            arm_list = result.get(reps_key) or []
            if not arm_list:
                continue
            report = arm_list[0].get("report")
            if report is None:
                continue
            render_backlog_waiting_time_from_run_report(
                report,
                title=f"**{arm_title} — backlog waiting-time at end of decay (years)**",
            )
        comp = result.get("comparison_summary")
        if comp is not None and not comp.empty:
            st.markdown("**Paired comparison (full)**")
            st.dataframe(comp.round(2), use_container_width=True)
        elif result.get("comparison"):
            st.dataframe(pd.Series(result["comparison"], name="delta").round(1).to_frame())

        reps = result.get("policy_replications") or []
        ctrl_reps = result.get("control_replications") or []
        pairs = [("Policy (rep 0)", reps), ("Baseline (rep 0)", ctrl_reps)]
        for label, arm_list in pairs:
            if not arm_list:
                continue
            report = arm_list[0].get("report")
            if report is None:
                continue
            rs = run_report_tables_in_years(run_report_summary(report))
            fw = float(result.get("flow_window_days", 365))
            st.markdown(f"**Flow at end of decay — {label}** (window {fw:.0f} d; waits in years)")
            st.dataframe(rs["flow_counts_and_waits"].round(3), use_container_width=True)


init_session_state()
render_session_status_sidebar()

st.title("Run 3 — Policy Analysis")
st.markdown(
    """
Run continuously to **T\\***, apply a **policy switch**, continue for a **decay period**,
and compare backlog change against a **baseline** (no policy change at T*).

| Arm | Replications | Purpose |
|-----|--------------|---------|
| **Baseline (control)** | **Same as policy** (`n_reps`) | No parameter change at T*; paired with policy reps |
| **Policy** | **You choose** (`n_reps`) | Policy switch at T*; mean ± 95% CI when `n_reps > 1` |

Both arms use the **same replication count** and matched random seeds (rep 0 vs rep 0, etc.).
Policy−baseline deltas are computed **pairwise** per replication.

Each policy simulation can be **recorded** into a scenario library and compared side-by-side.
Use **Reset all scenarios** to clear the library and start a new planning batch.

Charts use **years since T\\*** on the x-axis. Backlog and flow **wait** charts plot **median** wait in
**years**; baseline arms use dashed lines, policy arms solid lines.
"""
)

t_star = require_t_star()
if t_star is None:
    st.stop()

params = st.session_state.get("experiment_params")
if params is None:
    st.error("Model parameters not set. Go to **Run 1 — Calibration** first.")
    st.stop()

st.markdown("---")
st.subheader("Baseline values (from Run 1)")

baseline_df = baseline_policy_table(params)
st.dataframe(
    baseline_df[["group", "label", "baseline_value"]].rename(
        columns={"label": "parameter", "baseline_value": "value_at_T*"}
    ),
    use_container_width=True,
    hide_index=True,
)

st.markdown("---")
st.subheader("Policy switch — select parameters to change")

param_options = {
    meta["label"]: key for key, meta in POLICY_PARAMETER_DEFS.items()
}

selected_labels = st.multiselect(
    "Parameters to override at T*",
    options=list(param_options.keys()),
    default=[],
    help="Pick any combination. Only selected parameters change after the switch.",
)

selected_keys = [param_options[label] for label in selected_labels]

render_policy_parameter_inputs(params, selected_keys)

policy_overrides = build_policy_overrides_from_ui(params, selected_keys)

if policy_overrides:
    st.markdown("**Override dict sent to the model**")
    st.json(policy_overrides)
else:
    st.info(
        "No parameters selected — policy arm will behave like **baseline** "
        "(no change at T*)."
    )

default_policy_name = (
    "policy_"
    + "_".join(selected_keys[:3])
    + ("_etc" if len(selected_keys) > 3 else "")
    if selected_keys
    else "no_change"
)

st.markdown("---")
st.subheader("Decay window & replications")

DECAY_YEAR_OPTIONS = [1, 2, 3, 4, 5]
if "run3_decay_years" not in st.session_state:
    st.session_state["run3_decay_years"] = 2

c1, c2, c3 = st.columns(3)
with c1:
    decay_years = st.selectbox(
        "Decay period (years)",
        options=DECAY_YEAR_OPTIONS,
        key="run3_decay_years",
        help="How long to simulate **after** the policy switch at T*.",
    )
    decay_days = int(decay_years) * 365
    st.caption(f"= **{decay_days}** simulation days after T*")

# Keep flow window aligned when decay changes (stale session state showed wrong duration).
if st.session_state.get("_run3_last_decay_days") != decay_days:
    st.session_state["run3_flow"] = decay_days
    st.session_state["_run3_last_decay_days"] = decay_days
elif st.session_state.get("run3_flow", decay_days) > decay_days:
    st.session_state["run3_flow"] = decay_days

with c2:
    flow_window = st.number_input(
        "Flow window (days)",
        min_value=30,
        max_value=int(decay_days),
        step=30,
        key="run3_flow",
        help="Rolling window for throughput/wait KPIs at each checkpoint. "
        "Cannot exceed the decay window above.",
    )
with c3:
    ts_step_days = st.selectbox(
        "KPI chart step",
        options=[("Monthly", 30.4375), ("Quarterly", 91.3125), ("Yearly", 365.25)],
        index=0,
        format_func=lambda x: x[0],
    )[1]

run2 = st.session_state.get("run2_result")
default_reps = int(run2["n_reps"]) if run2 else 5

c4, c5, c6 = st.columns(3)
with c4:
    include_control = st.checkbox(
        "Include baseline arm (no policy change)",
        value=True,
        help="Runs control simulations with no overrides at T* (same n_reps as policy).",
    )
with c5:
    n_reps = st.number_input(
        "Replications (each arm)",
        min_value=1,
        max_value=20,
        value=default_reps,
        step=1,
        help="Stochastic replications for **both** baseline and policy arms.",
        key="run3_n_reps",
    )
with c6:
    total_sims = int(n_reps) * (2 if include_control else 1)
    st.metric("Simulations per run", str(total_sims))

scenario_name = st.text_input(
    "Scenario name",
    value="",
    placeholder=default_policy_name,
    help="Label for this policy on the charts and scenario comparison table.",
    key="run3_scenario_name",
)

st.markdown("---")

if st.button("Run Run 3 — policy switch", type="primary", use_container_width=True):
    display_name = (scenario_name.strip() or default_policy_name)
    experiment = create_experiment(params)
    sims = f"{n_reps} baseline + {n_reps} policy" if include_control else f"{n_reps} policy"
    with st.status(
        f"Run 3 — **{display_name}** · T*={t_star:.0f} d · {sims} sim(s)…",
        expanded=True,
    ) as status:
        on_progress = make_run3_progress_ui(status)
        result = run3_for_streamlit(
            experiment=experiment,
            matching_period_days=t_star,
            decay_period_days=float(decay_days),
            policy_overrides=policy_overrides,
            flow_window_days=float(flow_window),
            kpi_step_days=float(ts_step_days),
            n_reps=int(n_reps),
            include_control=include_control,
            policy_name=display_name.replace(" ", "_"),
            on_progress=on_progress,
        )
    result["_run_uid"] = uuid4().hex
    st.session_state["run3_result"] = result
    st.session_state["run3_overrides"] = policy_overrides
    st.session_state["run3_elapsed"] = result.get("elapsed_seconds")
    st.session_state["run3_last_policy_label"] = display_name
    st.rerun()

last_result = st.session_state.get("run3_result")
library_runs = _scenario_library()

if last_result is None and not library_runs:
    st.info("Click **Run Run 3** to execute a policy scenario.")
    st.stop()

if last_result is not None:
    render_run3_last_run_summary(last_result)
    st.markdown("---")
    st.subheader("Policy effect over decay period (this run)")
    this_run_charts = decay_scenario_runs_from_result(
        last_result,
        policy_label=st.session_state.get("run3_last_policy_label", "Policy"),
    )
    render_run3_decay_period_charts(this_run_charts)
    st.markdown("---")

render_scenario_library_controls()

compare_runs = scenarios_for_compare()
if compare_runs:
    st.subheader("Scenario comparison (selected)")
    if len(compare_runs) < len(library_runs):
        st.caption(f"Showing **{len(compare_runs)}** of **{len(library_runs)}** recorded scenario(s).")
    render_run3_kpi_comparison_charts(compare_runs)
    render_run3_scenario_comparison_table(compare_runs)
elif library_runs:
    st.info("Select at least one scenario under **Scenarios to compare** to view charts.")
