"""Shared Streamlit helpers — experiment params, session state, T*."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

try:
    import numpy  # noqa: F401
except ImportError:
    st.set_page_config(page_title="NHS Pathway DES — setup error")
    st.error("Wrong Python environment — NumPy could not be loaded.")
    st.markdown(f"Streamlit is running with `{sys.executable}`. Use the project venv:")
    st.code(f"cd {_ROOT}\n./run_streamlit.sh", language="bash")
    st.stop()

import pandas as pd

from des.audit import Audit
from des.experiment import Experiment
from des.run_report import flow_kpi_history_field_names

DEFAULT_MONTHLY_REFERRALS = 41
DEFAULT_WORKING_DAYS_PER_MONTH = (52 * 5) / 12
DEFAULT_ASSESSMENT_COUNTS = [2, 3, 4, 5]
DEFAULT_ASSESSMENT_PROBS = [0.40, 0.30, 0.20, 0.10]
DEFAULT_DURATION_ASSESSMENT = [2.0, 2.5, 3.0]
DEFAULT_DURATION_WORKSHOP_SESSION = [2.0, 3.0, 4.0]
DEFAULT_WORKSHOP_NUM_SESSIONS = 6
DEFAULT_WORKSHOP_SESSION_INTERVAL_WEEKS = 1
DEFAULT_WORKFORCE_HOURS_WORKSHOP_SESSION = 2.0

DAYS_PER_YEAR = 365.25

WAIT_CALIBRATION_TARGET_KEYS = frozenset(
    {
        "backlog_mean_wait_days",
        "backlog_median_wait_days",
        "flow_wait_mean_days_assessments_started",
        "flow_wait_median_days_assessments_started",
        "flow_wait_mean_days_assessments_finished",
        "flow_wait_median_days_assessments_finished",
    }
)

_REPLICATION_WAIT_STATS = frozenset({"mean", "median", "sd", "ci_lower", "ci_upper", "p25", "p95"})

BACKLOG_WAIT_HEADLINE_KEYS: tuple[str, ...] = (
    "backlog_patients_at_horizon",
    "backlog_mean_wait_days",
    "backlog_median_wait_days",
)


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def init_session_state() -> None:
    for key, value in {
        "experiment_params": None,
        "run1_result": None,
        "t_star": None,
        "run2_result": None,
        "run3_result": None,
        "run3_scenario_runs": [],
        "run3_compare_ids": [],
        "run3_recorded_run_uids": [],
    }.items():
        if key not in st.session_state:
            st.session_state[key] = value


def require_t_star() -> float | None:
    t_star = st.session_state.get("t_star")
    if t_star is None:
        st.warning("Run **Run 1 — Calibration** first to find matching period T*.")
        return None
    st.info(f"Using T* = **{t_star:.0f} days** ({t_star / 365.25:.1f} years) from Run 1.")
    return float(t_star)


def create_experiment(params: dict[str, Any]) -> Experiment:
    return Experiment(
        audit=Audit(),
        random_number_set=42,
        n_streams=15,
        use_fixed_seed=True,
        scenario_name="streamlit",
        **params,
    )


def build_experiment_params(
    *,
    monthly_referrals: float,
    pct_referral_rejected: float,
    pct_admin_removal: float,
    pct_diagnosis: float,
    pct_virtual_support: float,
    workforce_hours_per_day: float,
    workforce_hours_workshop_session: float,
    assessment_appointment_counts: list[int],
    assessment_appointment_probs: list[float],
    assessment_gap_days: int,
    duration_assessment: list[float],
    workshop_group_size: int,
    workshop_num_sessions: int,
    workshop_session_interval_weeks: int,
    workshop_max_wait_days: int,
    duration_workshop_session: list[float],
) -> dict[str, Any]:
    iat = 1.0 / (monthly_referrals / DEFAULT_WORKING_DAYS_PER_MONTH)
    # UI label ``monthly_referrals``; model parameter is ``iat`` (mean inter-arrival days).
    return {
        "iat": iat,
        "pct_referral_rejected": pct_referral_rejected,
        "pct_admin_removal": pct_admin_removal,
        "assessment_appointment_counts": assessment_appointment_counts,
        "assessment_appointment_probs": assessment_appointment_probs,
        "assessment_gap_days": assessment_gap_days,
        "duration_assessment": duration_assessment,
        "pct_diagnosis": pct_diagnosis,
        "pct_virtual_support": pct_virtual_support,
        "workshop_group_size": workshop_group_size,
        "workshop_num_sessions": workshop_num_sessions,
        "workshop_session_interval_weeks": workshop_session_interval_weeks,
        "workshop_max_wait_days": workshop_max_wait_days,
        "duration_workshop_session": duration_workshop_session,
        "workforce_hours_workshop_session": workforce_hours_workshop_session,
        "workforce_hours_per_day": workforce_hours_per_day,
    }


def default_assessment_appointment_table() -> pd.DataFrame:
    return pd.DataFrame(
        {"appointments": DEFAULT_ASSESSMENT_COUNTS, "probability": DEFAULT_ASSESSMENT_PROBS}
    )


def _coerce_assessment_appointment_table(table: Any) -> pd.DataFrame:
    """Normalise ``st.data_editor`` return value or session state to a DataFrame."""
    if table is None:
        return pd.DataFrame(columns=["appointments", "probability"])
    if isinstance(table, pd.DataFrame):
        return table
    if isinstance(table, dict):
        if "appointments" in table and "probability" in table:
            return pd.DataFrame(table)
        if "data" in table:
            return pd.DataFrame(table["data"])
    return pd.DataFrame(columns=["appointments", "probability"])


def parse_assessment_appointment_table(
    table: pd.DataFrame | Any,
) -> tuple[list[int] | None, list[float] | None, list[str]]:
    table = _coerce_assessment_appointment_table(table)
    if table.empty:
        return None, None, ["Add at least one appointment count and probability."]

    cleaned = table.dropna(subset=["appointments"]).copy()
    cleaned = cleaned[cleaned["appointments"] >= 1]
    cleaned["appointments"] = cleaned["appointments"].astype(int)
    if cleaned.empty:
        return None, None, ["Add at least one valid appointment count (≥ 1)."]

    dupes = cleaned["appointments"][cleaned["appointments"].duplicated()].unique().tolist()
    if dupes:
        return None, None, [f"Each appointment count must be unique (duplicates: {dupes})."]

    cleaned = cleaned.sort_values("appointments")
    counts = cleaned["appointments"].tolist()
    raw_probs = cleaned["probability"].fillna(0.0).astype(float).tolist()
    if any(p < 0 for p in raw_probs):
        return None, None, ["Probabilities must be ≥ 0."]
    prob_sum = sum(raw_probs)
    if prob_sum <= 0:
        return None, None, ["Probabilities must sum to more than 0."]

    messages: list[str] = []
    if abs(prob_sum - 1.0) > 0.001:
        messages.append(f"Probabilities sum to {prob_sum:.3f} — normalised to 1.0.")
    norm = [p / prob_sum for p in raw_probs]
    return counts, norm, messages


_FLOW_KPI_PREFIXES = ("flow_count_", "flow_per_month_", "flow_wait_")


def is_wait_duration_column(col: str) -> bool:
    """True if column values are wait lengths in simulation days (not horizons/windows)."""
    c = str(col)
    cl = c.lower()
    if cl in ("horizon_days", "window_days", "flow_window_days", "sim_day", "days_since_switch"):
        return False
    if cl.endswith("_pct") or "elapsed" in cl:
        return False
    markers = (
        "flow_wait_mean_days",
        "flow_wait_median_days",
        "mean_wait_days",
        "median_wait_days",
        "completed_mean_days",
        "completed_median_days",
        "still_waiting_mean_days",
        "still_waiting_median_days",
        "still_waiting_p25_days",
        "still_waiting_p95_days",
        "backlog_mean_wait_days",
        "backlog_median_wait_days",
    )
    if any(m in cl for m in markers):
        return True
    if cl.endswith("_mean_days") or cl.endswith("_median_days") or cl.endswith("_p25_days") or cl.endswith("_p95_days"):
        return any(
            x in cl
            for x in ("wait", "rtt", "referral", "backlog", "assessment", "diagnosis", "completed", "still_waiting")
        )
    return False


def is_replication_wait_stat_name(stat: str) -> bool:
    """Whether a summarised ``stat`` row from Run 2 replication tables is a wait duration."""
    s = str(stat)
    if s in ("n", "eligible_n", "complete_n", "still_waiting_n", "count_in_window", "per_month"):
        return False
    if s in ("mean", "median", "p25", "p95"):
        return True
    return is_wait_duration_column(s)


def wait_duration_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if is_wait_duration_column(c)]


def _rename_wait_columns_to_years(df: pd.DataFrame) -> pd.DataFrame:
    rename: dict[str, str] = {}
    for c in df.columns:
        if not is_wait_duration_column(c):
            continue
        nc = (
            str(c)
            .replace("flow_wait_mean_days", "flow_wait_mean_years")
            .replace("flow_wait_median_days", "flow_wait_median_years")
            .replace("mean_wait_days", "mean_wait_years")
            .replace("median_wait_days", "median_wait_years")
            .replace("_days", "_years")
        )
        rename[c] = nc
    return df.rename(columns=rename) if rename else df


def dataframe_wait_days_to_years(df: pd.DataFrame) -> pd.DataFrame:
    """Copy for display: wait-duration columns days → years."""
    if df is None or df.empty:
        return df
    out = df.copy()
    for c in wait_duration_columns(out):
        if pd.api.types.is_numeric_dtype(out[c]):
            out[c] = out[c] / DAYS_PER_YEAR
    return _rename_wait_columns_to_years(out)


def replication_wait_summary_to_years(df: pd.DataFrame) -> pd.DataFrame:
    """Run 2/3 replication summaries — convert wait-duration ``stat`` rows to years."""
    if df is None or df.empty:
        return df
    if "stat" not in df.columns:
        return dataframe_wait_days_to_years(df)
    out = df.copy()
    is_wait = out["stat"].astype(str).apply(is_replication_wait_stat_name)
    for c in _REPLICATION_WAIT_STATS:
        if c in out.columns and pd.api.types.is_numeric_dtype(out[c]):
            out.loc[is_wait, c] = out.loc[is_wait, c] / DAYS_PER_YEAR
    out.loc[is_wait, "stat"] = (
        out.loc[is_wait, "stat"]
        .astype(str)
        .str.replace("_days", "_years", regex=False)
        .str.replace("mean_days", "mean_years", regex=False)
        .str.replace("median_days", "median_years", regex=False)
    )
    return out


def replication_wait_summary_rows(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """Filter replication summary to wait mean/median (and stock p25/p95) stats."""
    if df.empty or "stat" not in df.columns:
        return df
    mask = df["stat"].astype(str).apply(is_replication_wait_stat_name)
    cols = [group_col, "stat", "n", "mean", "sd", "ci_lower", "ci_upper"]
    cols = [c for c in cols if c in df.columns]
    return df.loc[mask, cols].copy()


def flow_kpi_summary_to_years(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "metric" not in df.columns:
        return dataframe_wait_days_to_years(df)
    out = df.copy()
    is_wait = out["metric"].astype(str).str.contains(
        r"wait_mean_days|wait_median_days|mean_wait|median_wait|_mean_days|_median_days",
        regex=True,
        case=False,
    )
    for c in ("mean", "sd", "ci_lower", "ci_upper"):
        if c in out.columns:
            out.loc[is_wait, c] = out.loc[is_wait, c] / DAYS_PER_YEAR
    out.loc[is_wait, "metric"] = (
        out.loc[is_wait, "metric"]
        .astype(str)
        .str.replace("_days", "_years", regex=False)
        .str.replace("mean_days", "mean_years", regex=False)
        .str.replace("median_days", "median_years", regex=False)
    )
    return out


def _ensure_backlog_waiting_time_table(tables: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """Build backlog PTL wait row if older ``run_report_summary`` omits the key."""
    if "backlog_waiting_time_report" in tables:
        frame = tables["backlog_waiting_time_report"]
        if frame is not None and not frame.empty:
            return frame.copy()
    rtt = tables.get("rtt_waits")
    if rtt is not None and not rtt.empty and "cohort" in rtt.columns:
        backlog = rtt.loc[rtt["cohort"].astype(str) == "backlog"]
        if not backlog.empty:
            return backlog.copy()
    return pd.DataFrame(columns=["cohort", "label", "n", "mean_wait_days", "median_wait_days"])


def run_report_tables_in_years(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Convert wait fields in :func:`run_report_summary` tables for UI."""
    tables = dict(tables)
    if "backlog_waiting_time_report" not in tables:
        tables["backlog_waiting_time_report"] = _ensure_backlog_waiting_time_table(tables)

    wait_keys = {
        "rtt_waits",
        "backlog_waiting_time_report",
        "waits_at_horizon",
        "waits_in_flow_window",
        "flow_counts_and_waits",
        "waits_stock_by_stage",
        "waits_flow_by_stage",
    }
    out: dict[str, pd.DataFrame] = {}
    for key, frame in tables.items():
        if key in wait_keys:
            if key == "rtt_waits":
                converted = frame.copy()
                for c in ("mean", "median", "mean_wait_days", "median_wait_days"):
                    if c in converted.columns and pd.api.types.is_numeric_dtype(converted[c]):
                        converted[c] = converted[c] / DAYS_PER_YEAR
                rename = {
                    "mean": "mean_years",
                    "median": "median_years",
                    "mean_wait_days": "mean_wait_years",
                    "median_wait_days": "median_wait_years",
                }
                converted = converted.rename(
                    columns={k: v for k, v in rename.items() if k in converted.columns}
                )
                out[key] = converted
            else:
                out[key] = dataframe_wait_days_to_years(frame)
        else:
            out[key] = frame
    return out


def calibration_target_ui_to_days(key: str, ui_value: float) -> float:
    if key in WAIT_CALIBRATION_TARGET_KEYS:
        return float(ui_value) * DAYS_PER_YEAR
    return float(ui_value)


def calibration_target_days_to_ui(key: str, days_value: float) -> float:
    if key in WAIT_CALIBRATION_TARGET_KEYS:
        return float(days_value) / DAYS_PER_YEAR
    return float(days_value)


def backlog_wait_snapshots_table(
    snapshots: pd.DataFrame,
    *,
    include_median: bool = True,
) -> pd.DataFrame:
    """Per-replication backlog PTL count and mean/median wait (display units: years for waits)."""
    if snapshots is None or snapshots.empty:
        return pd.DataFrame()
    wait_keys: tuple[str, ...] = BACKLOG_WAIT_HEADLINE_KEYS if include_median else (
        "backlog_patients_at_horizon",
        "backlog_mean_wait_days",
    )
    cols = [c for c in ("rep", *wait_keys) if c in snapshots.columns]
    if len(cols) <= 1:
        cols = [c for c in wait_keys if c in snapshots.columns]
    if not cols:
        return pd.DataFrame()
    return dataframe_wait_days_to_years(snapshots[cols])


def render_backlog_waiting_time_report_df(df: pd.DataFrame, *, title: str | None = None) -> None:
    if df is None or df.empty:
        st.caption("No backlog waiting-time data — re-run to refresh KPI snapshots.")
        return
    st.markdown(title or "**Backlog waiting-time report (PTL at horizon — years)**")
    st.dataframe(df.round(3), use_container_width=True, hide_index=True)


def render_backlog_waiting_time_from_run_report(report: Any, *, title: str | None = None) -> None:
    import des.run_report as run_report_mod
    from des.run_report import run_report_summary

    raw = run_report_summary(report)
    tables = run_report_tables_in_years(raw)
    df = tables.get("backlog_waiting_time_report")
    if df is None or df.empty:
        builder = getattr(run_report_mod, "backlog_waiting_time_report", None)
        if callable(builder):
            df = dataframe_wait_days_to_years(builder(report.rtt_waits_stock))
        else:
            df = dataframe_wait_days_to_years(_ensure_backlog_waiting_time_table(raw))
    render_backlog_waiting_time_report_df(df, title=title)


def flow_kpi_columns(df: pd.DataFrame) -> list[str]:
    if df is None or df.empty:
        return []
    return [c for c in df.columns if str(c).startswith(_FLOW_KPI_PREFIXES)]


def flow_count_decay_keys() -> tuple[str, ...]:
    return tuple(k for k in flow_kpi_history_field_names() if k.startswith("flow_count_"))


def flow_wait_mean_median_pairs() -> list[tuple[str, str, str]]:
    """(chart title, mean column, median column) for flow waits over decay."""
    from des.run_report import kpi_label

    pairs: list[tuple[str, str, str]] = []
    for key in flow_kpi_history_field_names():
        if not key.startswith("flow_wait_mean_days_"):
            continue
        slug = key.removeprefix("flow_wait_mean_days_")
        median_col = f"flow_wait_median_days_{slug}"
        title = kpi_label(median_col)
        if title.startswith("Flow — median wait: "):
            title = title.removeprefix("Flow — median wait: ")
        pairs.append((title, key, median_col))
    return pairs


def decay_kpi_y_scale(column: str) -> float:
    return 1.0 / DAYS_PER_YEAR if is_wait_duration_column(column) else 1.0


def flow_kpi_count_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if str(c).startswith(("flow_count_", "flow_per_month_"))]


def flow_kpi_wait_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if str(c).startswith("flow_wait_")]


def _flow_activity_slugs(df: pd.DataFrame) -> list[str]:
    slugs: list[str] = []
    for col in df.columns:
        name = str(col)
        if name.startswith("flow_count_"):
            slugs.append(name.removeprefix("flow_count_"))
    return sorted(set(slugs))


def _flow_slug_label(slug: str) -> str:
    from des.run_report import kpi_label

    return kpi_label(f"flow_count_{slug}")


def flow_kpi_table_from_wide(
    df: pd.DataFrame,
    *,
    index_cols: tuple[str, ...] = (),
) -> pd.DataFrame:
    """
    Long table: one row per run/checkpoint and pathway activity — count, rate, mean/median wait.
    """
    if df is None or df.empty or not flow_kpi_columns(df):
        return pd.DataFrame()
    slugs = _flow_activity_slugs(df)
    rows: list[dict[str, Any]] = []
    idx = [c for c in index_cols if c in df.columns]
    for _, row in df.iterrows():
        base = {c: row[c] for c in idx}
        for slug in slugs:
            rows.append(
                {
                    **base,
                    "activity": _flow_slug_label(slug),
                    "count_in_window": row.get(f"flow_count_{slug}"),
                    "per_month": row.get(f"flow_per_month_{slug}"),
                    "wait_sample_n": row.get(f"flow_wait_count_{slug}"),
                    "mean_wait_days": row.get(f"flow_wait_mean_days_{slug}"),
                    "median_wait_days": row.get(f"flow_wait_median_days_{slug}"),
                }
            )
    return pd.DataFrame(rows)


def render_flow_kpi_history(
    df: pd.DataFrame,
    *,
    index_cols: tuple[str, ...] = ("years",),
    flow_window_days: float | None = None,
    stale_hint: str | None = None,
    wide_only: bool = False,
) -> None:
    """Show flow-window counts and mean/median waits for each run/checkpoint."""
    if df is None or df.empty:
        st.caption("No data.")
        return
    if not flow_kpi_columns(df):
        st.info(
            stale_hint
            or (
                "No **flow_\\*** columns in this table. Re-run this step after updating the app, "
                "or restart Streamlit from the project repo."
            )
        )
        return
    if flow_window_days is not None:
        st.caption(
            f"Rolling **flow window = {flow_window_days:.0f} days** ending at each run horizon "
            "(event counts and mean/median waits for linked stages)."
        )
    base = [c for c in index_cols if c in df.columns]
    count_cols = list(dict.fromkeys(base + flow_kpi_count_columns(df)))
    wait_cols = list(dict.fromkeys(base + flow_kpi_wait_columns(df)))

    def _wide_tables() -> None:
        wait_display = dataframe_wait_days_to_years(df[wait_cols])
        left, right = st.columns(2)
        with left:
            st.markdown("**Event counts (rolling flow window)**")
            st.dataframe(df[count_cols].round(2), use_container_width=True)
        with right:
            st.markdown("**Linked wait times — mean / median (years)**")
            st.dataframe(wait_display.round(3), use_container_width=True)

    if wide_only:
        _wide_tables()
        return

    combined = dataframe_wait_days_to_years(flow_kpi_table_from_wide(df, index_cols=index_cols))
    st.markdown("**Flow window — counts & waits (each run)**")
    st.dataframe(combined.round(3), use_container_width=True, hide_index=True)
    with st.expander("Raw flow columns (wide format)", expanded=False):
        _wide_tables()


def _reload_des_runners():
    """Reload reporting + runners so Streamlit picks up ``des/`` edits without a full restart."""
    import importlib

    import des.run_report as run_report_mod
    importlib.reload(run_report_mod)
    from des import runners as runners_mod

    return importlib.reload(runners_mod)


def run3_for_streamlit(
    experiment: Experiment,
    *,
    matching_period_days: float,
    decay_period_days: float,
    policy_overrides: dict[str, Any] | None = None,
    flow_window_days: float | None = None,
    kpi_step_days: float = 30.4375,
    n_reps: int = 1,
    include_control: bool = True,
    policy_name: str = "policy",
    on_progress: Any = None,
) -> dict[str, Any]:
    runners = _reload_des_runners()
    return runners.run3(
        experiment,
        matching_period_days=matching_period_days,
        decay_period_days=decay_period_days,
        policy_overrides=policy_overrides,
        flow_window_days=flow_window_days,
        kpi_step_days=kpi_step_days,
        n_reps=n_reps,
        include_control=include_control,
        policy_name=policy_name,
        on_progress=on_progress,
    )
