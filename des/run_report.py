
"""KPI reporting for the referral -> assessment -> workshop pathway simulation.

Naming convention
-----------------
* **stock** — snapshot at simulation horizon (``sim_end``)
* **flow**  — activity / completions in the rolling ``flow_window_days``
* **backlog** — accepted active patients still on the pathway at horizon (PTL)

Canonical **headline** KPI keys live in :data:`KPI_LABELS` (``backlog_patients_at_horizon``,
``backlog_mean_wait_days``, ``capacity_used_pct``, …). :func:`headline_kpis` and
:func:`kpi_snapshot` flatten a :class:`RunReport`; :func:`normalize_kpi_key` maps legacy
target names. **Model parameters** use :meth:`~des.experiment.Experiment.to_kwargs` names
(``iat``, ``pct_diagnosis``, ``workforce_hours_per_day``, …); UI ``monthly_referrals`` maps to ``iat``.

Built directly against audit tables from :class:`~des.audit.Audit`.

Human-readable definitions: see ``GLOSSARY.md`` at the repository root (Streamlit **Glossary** page).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

import numpy as np
import pandas as pd

RTT_18_WEEKS_DAYS = 18 * 7
RTT_52_WEEKS_DAYS = 52 * 7

# ---------------------------------------------------------------------------
# Display labels (code key -> plain English)
# ---------------------------------------------------------------------------

KPI_LABELS: dict[str, str] = {
    # Report sections
    "pathway_funnel": "Pathway funnel",
    "pathway_exits": "Pathway exits",
    "waits_stock_by_stage": "Waits at horizon (by stage)",
    "waits_flow_by_stage": "Waits for recent completions (by stage)",
    "rtt_waits_stock": "RTT waits at horizon",
    "rtt_breaches_stock": "18 / 52-week breaches at horizon",
    "capacity_utilisation": "Clinician capacity utilisation",
    "assessment_adherence": "Assessment appointment adherence",
    "workshop_group_stats": "Workshop group statistics",
    "activity_flow": "Pathway activity (flow window)",
    # Funnel stages
    "referrals_received": "Referrals received",
    "accepted": "Accepted at triage",
    "rejected": "Rejected at triage",
    "admin_removed": "Removed administratively",
    "referrals_active": "Active referrals",
    "started_assessment": "Started assessment",
    "finished_assessment": "Finished assessment",
    "diagnosed_yes": "Diagnosed (positive)",
    "diagnosed_no": "Diagnosed (negative)",
    "sent_to_workshops": "Sent to workshops",
    "sent_to_virtual_support": "Sent to virtual support",
    "workshop_joined": "Joined workshop queue",
    "workshop_started": "Workshop started",
    "workshop_completed": "Workshop completed",
    "still_on_pathway_all": "Still on pathway (all, incl. pre-triage)",
    "completed_pathway": "Completed pathway",
    "rejected_at_triage": "Rejected — RTT nullified",
    # Stage waits
    "wait_referral_to_first_assessment": "Referral → first assessment",
    "wait_referral_to_diagnosis": "Referral → diagnosis decision",
    "wait_referral_to_workshop_queue": "Referral → workshop queue",
    "wait_referral_to_workshop_start": "Referral → workshop start",
    "wait_referral_to_workshop_finish": "Referral → workshop finish",
    "wait_referral_to_virtual_exit": "Referral → virtual support exit",
    # RTT cohorts
    "backlog": "Backlog / PTL (on pathway)",
    "completed_all": "Completed (all exits)",
    "completed_clinical": "Completed (excl. admin removal)",
    # Headline KPIs (stock at horizon)
    "backlog_patients_at_horizon": "Backlog / PTL — count at horizon",
    "backlog_mean_wait_days": "Backlog / PTL — mean RTT wait",
    "backlog_median_wait_days": "Backlog / PTL — median RTT wait",
    "completed_mean_rtt_days": "Completed pathway — mean RTT wait",
    "backlog_over_18_weeks_pct": "Backlog / PTL — over 18 weeks (%)",
    "backlog_over_52_weeks_pct": "Backlog / PTL — over 52 weeks (%)",
    "capacity_used_pct": "Clinician utilisation (%)",
    "assessments_per_month": "Flow — rate: assessments finished (/ month)",
    "diagnoses_per_month": "Flow — rate: diagnoses (/ month)",
    # Activity flow metrics
    "referrals_in_window": "Referrals in period",
    "referrals_accepted_in_window": "Referrals accepted in period",
    "assessments_started_in_window": "Assessments started in period",
    "assessments_finished_in_window": "Assessments finished in period",
    "diagnoses_in_window": "Positive diagnoses in period",
    "workshops_joined_in_window": "Joined workshop queue in period",
    "workshops_started_in_window": "Workshops started in period",
    "workshops_finished_in_window": "Workshops finished in period",
    "virtual_completed_in_window": "Virtual support completed in period",
    "all_exits_in_window": "All pathway exits in period",
    # Run 3 arm scalars
    "backlog_at_switch": "Backlog / PTL — count at T* (policy switch)",
    "backlog_at_end": "Backlog / PTL — count at end of decay",
    "backlog_decay": "Backlog / PTL — reduction (T* → end)",
    "backlog_decay_per_month": "Backlog / PTL — reduction per month",
    "delta_backlog_at_end": "Policy − baseline: backlog at end of decay",
    "delta_backlog_decay": "Policy − baseline: backlog reduction",
    "delta_backlog_decay_per_month": "Policy − baseline: reduction per month",
}

# Plain names for flow-window activity slugs (see :func:`flow_kpi_history_field_names`).
_FLOW_ACTIVITY_DISPLAY: dict[str, str] = {
    "referrals": "Referrals received",
    "assessments_started": "Assessments started",
    "assessments_finished": "Assessments finished",
    "diagnoses": "Diagnoses (positive)",
    "workshops_finished": "Workshops finished",
    "virtual_completed": "Virtual support completed",
}

# Map calibration / notebook target keys → canonical :func:`headline_kpis` keys.
KPI_TARGET_ALIASES: dict[str, str] = {
    "waiting_list_size": "backlog_patients_at_horizon",
    "waiting_list": "backlog_patients_at_horizon",
    "waiting_list_size_all_in_system": "backlog_patients_at_horizon",
    "rtt_incomplete_mean_days": "backlog_mean_wait_days",
    "rtt_incomplete_median_days": "backlog_median_wait_days",
    "rtt_incomplete": "backlog_mean_wait_days",
    "rtt_completed_mean_days": "completed_mean_rtt_days",
    "overall_clinician_utilisation": "capacity_used_pct",
    "workshop_utilisation": "workshop_hours_share_pct",
    "ptl_over_18_weeks_pct": "backlog_over_18_weeks_pct",
    "ptl_over_52_weeks_pct": "backlog_over_52_weeks_pct",
    # Run 3 legacy arm / comparison keys
    "waiting_list_at_switch": "backlog_at_switch",
    "waiting_list_at_end": "backlog_at_end",
    "delta_waiting_list_end": "delta_backlog_at_end",
}

# Deprecated snapshot field names emitted by :func:`kpi_snapshot` for old notebooks.
LEGACY_KPI_FIELD_ALIASES: dict[str, str] = {
    "waiting_list_size": "backlog_patients_at_horizon",
    "waiting_list_size_all_in_system": "backlog_patients_at_horizon",
    "rtt_incomplete_mean_days": "backlog_mean_wait_days",
    "rtt_incomplete_median_days": "backlog_median_wait_days",
    "rtt_completed_mean_days": "completed_mean_rtt_days",
    "ptl_over_18_weeks": "backlog_over_18_weeks",
    "ptl_over_52_weeks": "backlog_over_52_weeks",
    "ptl_over_18_weeks_pct": "backlog_over_18_weeks_pct",
    "ptl_over_52_weeks_pct": "backlog_over_52_weeks_pct",
    "overall_clinician_utilisation": "capacity_used_pct",
    "workshop_utilisation": "workshop_hours_share_pct",
}


def kpi_label(key: str) -> str:
    """
    Return a plain-English label for a KPI code key.

    Parameters
    ----------
    key : str
        Internal metric or stage identifier (e.g. ``"backlog_patients_at_horizon"``).

    Returns
    -------
    str
        Display label from :data:`KPI_LABELS`, flow/history patterns, or a title-cased
        fallback derived from *key*.
    """
    if key in KPI_LABELS:
        return KPI_LABELS[key]
    if key.startswith("flow_count_"):
        slug = key.removeprefix("flow_count_")
        name = _FLOW_ACTIVITY_DISPLAY.get(slug, slug.replace("_", " "))
        return f"Flow — count: {name}"
    if key.startswith("flow_per_month_"):
        slug = key.removeprefix("flow_per_month_")
        name = _FLOW_ACTIVITY_DISPLAY.get(slug, slug.replace("_", " "))
        return f"Flow — rate: {name} (/ month)"
    if key.startswith("flow_wait_mean_days_"):
        slug = key.removeprefix("flow_wait_mean_days_")
        return f"Flow — mean wait: {_flow_wait_milestone_label(slug)}"
    if key.startswith("flow_wait_median_days_"):
        slug = key.removeprefix("flow_wait_median_days_")
        return f"Flow — median wait: {_flow_wait_milestone_label(slug)}"
    if key.startswith("flow_wait_count_"):
        slug = key.removeprefix("flow_wait_count_")
        return f"Flow — wait sample size: {_flow_wait_milestone_label(slug)}"
    return key.replace("_", " ").title()


def _flow_wait_milestone_label(slug: str) -> str:
    """Link a flow activity slug to its pathway stage wait label."""
    for metric, stage in _ACTIVITY_TO_WAIT_STAGE.items():
        if _activity_slug(metric) == slug:
            return KPI_LABELS.get(stage, stage.replace("_", " "))
    return slug.replace("_", " ")


def normalize_kpi_key(key: str) -> str:
    """Return the canonical headline KPI key for *key* (targets, metrics, columns)."""
    return KPI_TARGET_ALIASES.get(key, key)


def normalize_kpi_target(name: str, value: float) -> tuple[str, float]:
    """Map a calibration target name/value to canonical key and units."""
    key = normalize_kpi_key(name)
    val = float(value)
    if name in ("overall_clinician_utilisation", "workshop_utilisation") and abs(val) <= 1.0:
        return key, val * 100.0
    return key, val


def _report_value(report: "RunReport", table: str, query: str, col: str, default=np.nan):
    df = getattr(report, table)
    if df.empty:
        return default
    part = df.query(query) if query else df
    if part.empty or col not in part.columns:
        return default
    return part[col].iloc[0]


def headline_kpis(report: "RunReport") -> dict[str, Any]:
    """Canonical flat headline metrics from one :class:`RunReport`."""
    util = report.capacity_utilisation.iloc[0].to_dict() if not report.capacity_utilisation.empty else {}
    months = max(report.flow_window_days / 30.4375, 1e-9)

    def flow_rate(metric: str) -> float:
        if metric not in report.activity_flow.index:
            return np.nan
        return float(report.activity_flow.loc[metric, "count_in_window"]) / months

    metrics = dict(report.summary())
    metrics.update(
        {
            "referral_to_first_assessment_mean_days": float(
                _report_value(
                    report,
                    "waits_stock_by_stage",
                    'stage == "wait_referral_to_first_assessment"',
                    "still_waiting_mean_days",
                )
            ),
            "backlog_over_18_weeks": int(
                _report_value(report, "rtt_breaches_stock", 'cohort == "backlog"', "over_18_weeks", 0)
            ),
            "backlog_over_52_weeks": int(
                _report_value(report, "rtt_breaches_stock", 'cohort == "backlog"', "over_52_weeks", 0)
            ),
            "assessments_per_month": flow_rate("assessments_finished_in_window"),
            "diagnoses_per_month": flow_rate("diagnoses_in_window"),
            "workshop_hours_share_pct": float(util.get("workshop_pct_of_released", np.nan)),
            "horizon_days": report.sim_end,
            "flow_window_days": report.flow_window_days,
        }
    )
    return metrics


def apply_legacy_kpi_aliases(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """Add deprecated field names pointing at canonical headline KPI values."""
    out = dict(metrics)

    def _scale(legacy: str, canonical: str, factor: float) -> None:
        if canonical not in out or legacy in out:
            return
        val = out[canonical]
        if val is None or (isinstance(val, float) and np.isnan(val)):
            out[legacy] = val
        else:
            out[legacy] = float(val) * factor

    for legacy, canonical in LEGACY_KPI_FIELD_ALIASES.items():
        if canonical not in out:
            continue
        if legacy in ("overall_clinician_utilisation", "workshop_utilisation"):
            _scale(legacy, canonical, 1.0 / 100.0)
        elif legacy not in out:
            out[legacy] = out[canonical]
    return out


def kpi_snapshot(report: "RunReport") -> dict[str, Any]:
    """
    Flat headline KPI dict with deprecated aliases for older notebooks.

    Prefer keys documented in :data:`KPI_LABELS` (``backlog_*``, ``capacity_used_pct``, …).
    """
    return apply_legacy_kpi_aliases(headline_kpis(report))


# ============================================================================
# Report container
# ============================================================================


@dataclass
class RunReport:
    """
    Structured KPI bundle for one simulation replication.

    Attributes
    ----------
    sim_end : float
        Simulation horizon in days (end of the run).
    flow_window_days : float
        Rolling window length for flow / throughput KPIs.
    pathway_funnel : pandas.DataFrame
        Counts at each pathway stage at horizon.
    pathway_exits : pandas.DataFrame
        Exit-route counts (all-time and within the flow window).
    waits_stock_by_stage : pandas.DataFrame
        Wait-time statistics at horizon, split by pathway stage.
    waits_flow_by_stage : pandas.DataFrame
        Wait-time statistics for milestones completed in the flow window.
    rtt_waits_stock : pandas.DataFrame
        RTT wait summaries by cohort (backlog, completed, etc.) at horizon.
    rtt_breaches_stock : pandas.DataFrame
        18- and 52-week breach counts and percentages by RTT cohort.
    capacity_utilisation : pandas.DataFrame
        Clinician-hour release and usage totals.
    assessment_adherence : pandas.DataFrame
        Assessment appointment completion rates.
    workshop_group_stats : pandas.DataFrame
        Per-group workshop timing and size statistics.
    activity_flow : pandas.DataFrame
        Throughput counts and per-month rates in the flow window.
    model_params : dict
        Experiment parameters used to produce this report.
    """

    sim_end: float
    flow_window_days: float

    pathway_funnel: pd.DataFrame
    pathway_exits: pd.DataFrame

    waits_stock_by_stage: pd.DataFrame
    waits_flow_by_stage: pd.DataFrame
    rtt_waits_stock: pd.DataFrame
    rtt_breaches_stock: pd.DataFrame

    capacity_utilisation: pd.DataFrame
    assessment_adherence: pd.DataFrame
    workshop_group_stats: pd.DataFrame
    activity_flow: pd.DataFrame

    model_params: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """
        Serialise the report tables to a plain dictionary.

        Returns
        -------
        dict
            Keys match :class:`RunReport` field names; values are scalars or
            :class:`pandas.DataFrame` objects.
        """
        return {
            "sim_end": self.sim_end,
            "flow_window_days": self.flow_window_days,
            "pathway_funnel": self.pathway_funnel,
            "pathway_exits": self.pathway_exits,
            "waits_stock_by_stage": self.waits_stock_by_stage,
            "waits_flow_by_stage": self.waits_flow_by_stage,
            "rtt_waits_stock": self.rtt_waits_stock,
            "rtt_breaches_stock": self.rtt_breaches_stock,
            "capacity_utilisation": self.capacity_utilisation,
            "assessment_adherence": self.assessment_adherence,
            "workshop_group_stats": self.workshop_group_stats,
            "activity_flow": self.activity_flow,
            "model_params": self.model_params,
        }

    def summary(self) -> dict[str, Any]:
        """
        Extract headline KPIs as a flat dictionary.

        Returns
        -------
        dict
            Scalar summary fields such as backlog size, mean waits, breach
            percentages, and capacity utilisation suitable for dashboards and
            calibration targets.
        """
        util = self.capacity_utilisation.iloc[0].to_dict() if not self.capacity_utilisation.empty else {}
        backlog = self.rtt_waits_stock.loc[self.rtt_waits_stock["cohort"] == "backlog"]
        completed = self.rtt_waits_stock.loc[self.rtt_waits_stock["cohort"] == "completed_clinical"]
        breach = self.rtt_breaches_stock.loc[self.rtt_breaches_stock["cohort"] == "backlog"]
        adherence = self.assessment_adherence.iloc[0].to_dict() if not self.assessment_adherence.empty else {}

        return {
            "referrals_total": int(self.pathway_funnel.loc["referrals_received", "count"]),
            "referrals_accepted_pct": _safe_pct(self.pathway_funnel, "accepted", "referrals_received"),
            "backlog_patients_at_horizon": int(backlog["n"].iloc[0]) if len(backlog) else 0,
            "backlog_mean_wait_days": float(backlog["mean"].iloc[0]) if len(backlog) else None,
            "backlog_median_wait_days": float(backlog["median"].iloc[0]) if len(backlog) else None,
            "completed_mean_rtt_days": float(completed["mean"].iloc[0]) if len(completed) else None,
            "backlog_over_18_weeks_pct": float(breach["over_18_weeks_pct"].iloc[0]) if len(breach) else None,
            "backlog_over_52_weeks_pct": float(breach["over_52_weeks_pct"].iloc[0]) if len(breach) else None,
            "capacity_used_pct": util.get("hours_used_pct"),
            "assessment_completion_pct": adherence.get("completion_pct"),
        }


def _safe_pct(counts: pd.DataFrame, part: str, whole: str) -> float | None:
    if part not in counts.index or whole not in counts.index:
        return None
    denom = counts.loc[whole, "count"]
    return 100.0 * counts.loc[part, "count"] / denom if denom else None


# ============================================================================
# Cohort helpers
# ============================================================================


def _accepted_active(df: pd.DataFrame) -> pd.Series:
    return (df["triage_outcome"] == "accepted") & (df["admin_removal"] != True)  # noqa: E712


def _diagnosed(df: pd.DataFrame, positive: bool) -> pd.Series:
    return _accepted_active(df) & (df["diagnosis"] == positive)


def _clinical(df: pd.DataFrame) -> pd.Series:
    return _diagnosed(df, True) & (df["support_type"] == "clinical")


def _virtual(df: pd.DataFrame) -> pd.Series:
    return _diagnosed(df, True) & (df["support_type"] == "virtual")


def _rtt_eligible(df: pd.DataFrame) -> pd.Series:
    return _accepted_active(df)


# ============================================================================
# Stat helpers
# ============================================================================


def _wait_stats(days: pd.Series) -> dict[str, float | int]:
    values = pd.to_numeric(days, errors="coerce").dropna()
    if values.empty:
        return {"n": 0, "mean": np.nan, "median": np.nan, "p25": np.nan, "p95": np.nan}
    return {
        "n": int(len(values)),
        "mean": float(values.mean()),
        "median": float(values.median()),
        "p25": float(values.quantile(0.25)),
        "p95": float(values.quantile(0.95)),
    }


def _breach_stats(days: pd.Series, *, prefix: str = "") -> dict[str, float | int]:
    values = pd.to_numeric(days, errors="coerce").dropna()
    p = f"{prefix}_" if prefix else ""
    if values.empty:
        return {
            f"{p}over_18_weeks": 0,
            f"{p}over_52_weeks": 0,
            f"{p}over_18_weeks_pct": np.nan,
            f"{p}over_52_weeks_pct": np.nan,
        }
    n = len(values)
    over_18 = int((values > RTT_18_WEEKS_DAYS).sum())
    over_52 = int((values > RTT_52_WEEKS_DAYS).sum())
    return {
        f"{p}over_18_weeks": over_18,
        f"{p}over_52_weeks": over_52,
        f"{p}over_18_weeks_pct": 100.0 * over_18 / n,
        f"{p}over_52_weeks_pct": 100.0 * over_52 / n,
    }


def _in_window(times: pd.Series, *, sim_end: float, window_days: float) -> pd.Series:
    t = pd.to_numeric(times, errors="coerce")
    start = sim_end - float(window_days)
    return t.notna() & (t >= start) & (t < sim_end)


# ============================================================================
# RTT clock
# ============================================================================


def enrich_rtt(patients: pd.DataFrame, sim_end: float) -> pd.DataFrame:
    """
    Attach NHS RTT clock columns to a patient table.

    Parameters
    ----------
    patients : pandas.DataFrame
        Patient audit table with ``arrival_time``, ``exit_time``, and triage fields.
    sim_end : float
        Simulation horizon used to compute incomplete waits.

    Returns
    -------
    pandas.DataFrame
        Copy of *patients* with ``rtt_status`` (``completed`` / ``incomplete`` /
        ``nullified``), ``rtt_clock_stop``, and ``rtt_wait_days`` added.
    """
    df = patients.copy()
    rejected = df["triage_outcome"] == "rejected"
    exit_t = pd.to_numeric(df["exit_time"], errors="coerce")
    arrival = df["arrival_time"].astype(float)

    still_open = exit_t.isna() | (exit_t >= sim_end)
    status = np.select(
        [rejected, still_open],
        ["nullified", "incomplete"],
        default="completed",
    )
    df["rtt_status"] = status
    df["rtt_clock_stop"] = np.where(status == "completed", exit_t, np.nan)
    df["rtt_wait_days"] = np.select(
        [status == "nullified", status == "incomplete"],
        [np.nan, sim_end - arrival],
        default=exit_t - arrival,
    )
    return df


# ============================================================================
# Pathway funnel & exits
# ============================================================================


def pathway_funnel(df: pd.DataFrame, sim_end: float) -> pd.DataFrame:
    """
    Count patients at each pathway stage at the simulation horizon.

    Parameters
    ----------
    df : pandas.DataFrame
        Finalised patient audit table.
    sim_end : float
        Simulation end time in days.

    Returns
    -------
    pandas.DataFrame
        Indexed by stage code with ``count`` and human-readable ``label`` columns.
    """
    active = df.loc[_accepted_active(df)]
    clinical = df.loc[_clinical(df)]
    virtual = df.loc[_virtual(df)]
    rtt = enrich_rtt(df, sim_end)

    rows = [
        ("referrals_received", len(df)),
        ("accepted", int((df["triage_outcome"] == "accepted").sum())),
        ("rejected", int((df["triage_outcome"] == "rejected").sum())),
        ("admin_removed", int(((df["triage_outcome"] == "accepted") & (df["admin_removal"] == True)).sum())),  # noqa: E712
        ("referrals_active", len(active)),
        ("started_assessment", int(active["assessment_start"].notna().sum())),
        ("finished_assessment", int(active["assessment_completion"].notna().sum())),
        ("diagnosed_yes", int((active["diagnosis"] == True).sum())),  # noqa: E712
        ("diagnosed_no", int((active["diagnosis"] == False).sum())),  # noqa: E712
        ("sent_to_workshops", len(clinical)),
        ("sent_to_virtual_support", len(virtual)),
        ("workshop_joined", int(clinical["workshop_join_time"].notna().sum())),
        ("workshop_started", int(clinical["workshop_start_time"].notna().sum())),
        ("workshop_completed", int(clinical["workshop_completion"].notna().sum())),
        ("still_on_pathway_all", int((rtt["rtt_status"] == "incomplete").sum())),
        ("completed_pathway", int((rtt["rtt_status"] == "completed").sum())),
        ("rejected_at_triage", int((rtt["rtt_status"] == "nullified").sum())),
    ]
    out = pd.DataFrame(rows, columns=["stage", "count"]).set_index("stage")
    out["label"] = [kpi_label(s) for s in out.index]
    return out


def pathway_exits(df: pd.DataFrame, *, sim_end: float, window_days: float) -> pd.DataFrame:
    """
    Tabulate pathway exit routes (all-time and within a flow window).

    Parameters
    ----------
    df : pandas.DataFrame
        Finalised patient audit table.
    sim_end : float
        Simulation end time in days.
    window_days : float
        Rolling look-back for the ``in_flow_window`` column.

    Returns
    -------
    pandas.DataFrame
        One row per ``exit_route`` with ``all_time`` and ``in_flow_window`` counts.
    """
    exited = df.loc[df["exit_time"].notna()]
    in_window = _in_window(df["exit_time"], sim_end=sim_end, window_days=window_days)
    all_time = exited.groupby("exit_route", dropna=False).size()
    windowed = exited.loc[in_window].groupby("exit_route", dropna=False).size()
    routes = sorted(set(all_time.index) | set(windowed.index), key=str)
    return pd.DataFrame({
        "exit_route": routes,
        "all_time": [int(all_time.get(r, 0)) for r in routes],
        "in_flow_window": [int(windowed.get(r, 0)) for r in routes],
    })


# ============================================================================
# Waits: stock and flow
# ============================================================================

_STAGES = [
    ("wait_referral_to_first_assessment", _accepted_active, "assessment_start"),
    ("wait_referral_to_diagnosis", _accepted_active, "assessment_completion"),
    ("wait_referral_to_workshop_queue", _clinical, "workshop_join_time"),
    ("wait_referral_to_workshop_start", _clinical, "workshop_start_time"),
    ("wait_referral_to_workshop_finish", _clinical, "workshop_completion"),
    ("wait_referral_to_virtual_exit", _virtual, "exit_time"),
]


def waits_stock_by_stage(df: pd.DataFrame, sim_end: float) -> pd.DataFrame:
    """
    Stage wait statistics at horizon (completed and still-waiting cohorts).

    Parameters
    ----------
    df : pandas.DataFrame
        Finalised patient audit table.
    sim_end : float
        Simulation end time in days.

    Returns
    -------
    pandas.DataFrame
        One row per pathway stage with mean/median waits and breach counts for
        patients still waiting at horizon.
    """
    rows = []
    for stage, eligible_fn, milestone_col in _STAGES:
        cohort = df.loc[eligible_fn(df)]
        arrival = cohort["arrival_time"].astype(float)
        milestone = pd.to_numeric(cohort[milestone_col], errors="coerce")
        reached = milestone.notna()

        complete_wait = milestone[reached] - arrival[reached]
        incomplete_wait = sim_end - arrival[~reached]

        c, i = _wait_stats(complete_wait), _wait_stats(incomplete_wait)
        rows.append({
            "stage": stage,
            "label": kpi_label(stage),
            "eligible_n": int(len(cohort)),
            "complete_n": c["n"],
            "still_waiting_n": i["n"],
            "completed_mean_days": c["mean"],
            "completed_median_days": c["median"],
            "still_waiting_mean_days": i["mean"],
            "still_waiting_median_days": i["median"],
            "still_waiting_p25_days": i["p25"],
            "still_waiting_p95_days": i["p95"],
            **_breach_stats(incomplete_wait, prefix="still_waiting"),
        })
    return pd.DataFrame(rows)


def waits_flow_by_stage(df: pd.DataFrame, *, sim_end: float, window_days: float) -> pd.DataFrame:
    """
    Stage wait statistics for milestones completed in the flow window.

    Parameters
    ----------
    df : pandas.DataFrame
        Finalised patient audit table.
    sim_end : float
        Simulation end time in days.
    window_days : float
        Rolling look-back ending at *sim_end*.

    Returns
    -------
    pandas.DataFrame
        One row per pathway stage with wait distribution stats and breach counts
        for completions in the window.
    """
    rows = []
    for stage, eligible_fn, milestone_col in _STAGES:
        eligible = eligible_fn(df)
        in_window = _in_window(df[milestone_col], sim_end=sim_end, window_days=window_days)
        cohort = df.loc[eligible & in_window]
        wait = pd.to_numeric(cohort[milestone_col], errors="coerce") - cohort["arrival_time"].astype(float)
        stats = _wait_stats(wait)
        rows.append({
            "stage": stage,
            "label": kpi_label(stage),
            "window_days": float(window_days),
            **stats,
            **_breach_stats(wait),
        })
    return pd.DataFrame(rows)


def rtt_waits_stock(df: pd.DataFrame, sim_end: float) -> pd.DataFrame:
    """
    RTT wait-time summaries by cohort at horizon.

    Parameters
    ----------
    df : pandas.DataFrame
        Finalised patient audit table.
    sim_end : float
        Simulation end time in days.

    Returns
    -------
    pandas.DataFrame
        Rows for ``backlog``, ``completed_all``, and ``completed_clinical``
        with ``n``, mean, median, and percentile wait statistics.
    """
    rtt = enrich_rtt(df, sim_end)
    backlog = rtt.loc[(rtt["rtt_status"] == "incomplete") & _rtt_eligible(rtt)]
    completed = rtt.loc[rtt["rtt_status"] == "completed"]
    completed_clinical = completed.loc[completed["exit_route"] != "admin_removal"]

    rows = [
        ("backlog", backlog["rtt_wait_days"]),
        ("completed_all", completed["rtt_wait_days"]),
        ("completed_clinical", completed_clinical["rtt_wait_days"]),
    ]
    return pd.DataFrame([
        {"cohort": name, "label": kpi_label(name), **_wait_stats(waits)}
        for name, waits in rows
    ])


def rtt_breaches_stock(df: pd.DataFrame, sim_end: float) -> pd.DataFrame:
    """
    18- and 52-week RTT breach counts and percentages by cohort.

    Parameters
    ----------
    df : pandas.DataFrame
        Finalised patient audit table.
    sim_end : float
        Simulation end time in days.

    Returns
    -------
    pandas.DataFrame
        One row per RTT cohort with breach counts and percentages.
    """
    rtt = enrich_rtt(df, sim_end)
    backlog = rtt.loc[(rtt["rtt_status"] == "incomplete") & _rtt_eligible(rtt)]
    completed = rtt.loc[rtt["rtt_status"] == "completed"]
    completed_clinical = completed.loc[completed["exit_route"] != "admin_removal"]

    rows = []
    for cohort, waits in [
        ("backlog", backlog["rtt_wait_days"]),
        ("completed_all", completed["rtt_wait_days"]),
        ("completed_clinical", completed_clinical["rtt_wait_days"]),
    ]:
        stats = _wait_stats(waits)
        rows.append({
            "cohort": cohort,
            "label": kpi_label(cohort),
            "n": stats["n"],
            **_breach_stats(waits),
        })
    return pd.DataFrame(rows)


# ============================================================================
# Capacity, adherence, workshops
# ============================================================================


def capacity_utilisation_summary(capacity: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate clinician-hour capacity usage across the simulation.

    Parameters
    ----------
    capacity : pandas.DataFrame
        Per-day capacity rows from :class:`~des.audit.Audit`.

    Returns
    -------
    pandas.DataFrame
        Single-row summary with released, used, and unused hours and split by
        assessment vs workshop activity.
    """
    if capacity.empty:
        return pd.DataFrame([{
            "days": 0, "hours_released": 0.0, "hours_used": 0.0, "hours_unused": 0.0,
            "hours_used_pct": np.nan, "assessment_hours_used": 0.0, "workshop_hours_used": 0.0,
            "assessment_pct_of_released": np.nan, "workshop_pct_of_released": np.nan,
        }])
    released = float(capacity["hours_released"].sum())
    used = float(capacity["hours_used"].sum())
    unused = float(capacity["hours_unused"].sum())
    assessment = float(capacity["assessment_hours_used"].sum())
    workshop = float(capacity["workshop_hours_used"].sum())

    def pct(x: float) -> float:
        return 100.0 * x / released if released else np.nan

    return pd.DataFrame([{
        "days": int(len(capacity)),
        "hours_released": released,
        "hours_used": used,
        "hours_unused": unused,
        "hours_used_pct": pct(used),
        "assessment_hours_used": assessment,
        "workshop_hours_used": workshop,
        "assessment_pct_of_released": pct(assessment),
        "workshop_pct_of_released": pct(workshop),
    }])


def assessment_adherence(df: pd.DataFrame) -> pd.DataFrame:
    """
    Summarise assessment appointment completion for accepted patients.

    Parameters
    ----------
    df : pandas.DataFrame
        Finalised patient audit table.

    Returns
    -------
    pandas.DataFrame
        Single-row summary with required vs completed appointments and mean
        clinician hours per patient.
    """
    cohort = df.loc[_accepted_active(df) & df["appointments_required"].notna()]
    required = pd.to_numeric(cohort["appointments_required"], errors="coerce")
    completed = pd.to_numeric(cohort["appointments_completed"], errors="coerce")
    fully_completed = (completed >= required) & required.notna()

    return pd.DataFrame([{
        "n_patients": int(len(cohort)),
        "total_required": float(required.sum()),
        "total_completed": float(completed.sum()),
        "completion_pct": 100.0 * completed.sum() / required.sum() if required.sum() else np.nan,
        "pct_patients_fully_completed": 100.0 * fully_completed.sum() / len(cohort) if len(cohort) else np.nan,
        "mean_clinician_hours_per_patient": float(
            pd.to_numeric(cohort["clinician_hours_consumed"], errors="coerce").mean()
        ),
        "mean_assessment_hours_per_patient": float(
            pd.to_numeric(cohort["assessment_hours_consumed"], errors="coerce").mean()
        ),
        "mean_workshop_hours_per_patient": float(
            pd.to_numeric(cohort["workshop_hours_consumed"], errors="coerce").mean()
        ),
    }])


def workshop_group_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-group workshop timing statistics for the clinical support pathway.

    Parameters
    ----------
    df : pandas.DataFrame
        Finalised patient audit table.

    Returns
    -------
    pandas.DataFrame
        One row per ``workshop_group_id`` with group size and mean join-to-start
        and start-to-complete durations in days.
    """
    clinical = df.loc[_clinical(df) & df["workshop_group_id"].notna()].copy()
    if clinical.empty:
        return pd.DataFrame(columns=[
            "workshop_group_id", "group_size", "mean_join_to_start_days", "mean_start_to_complete_days",
        ])

    join = pd.to_numeric(clinical["workshop_join_time"], errors="coerce")
    start = pd.to_numeric(clinical["workshop_start_time"], errors="coerce")
    complete = pd.to_numeric(clinical["workshop_completion"], errors="coerce")
    clinical["_join_to_start"] = start - join
    clinical["_start_to_complete"] = complete - start

    return clinical.groupby("workshop_group_id").agg(
        group_size=("patient_id", "count"),
        mean_join_to_start_days=("_join_to_start", "mean"),
        mean_start_to_complete_days=("_start_to_complete", "mean"),
    ).reset_index()


# ============================================================================
# Activity flow (throughputs)
# ============================================================================


def activity_flow_counts(df: pd.DataFrame, *, sim_end: float, window_days: float) -> pd.DataFrame:
    """
    Count pathway events occurring in the rolling flow window.

    Parameters
    ----------
    df : pandas.DataFrame
        Finalised patient audit table.
    sim_end : float
        Simulation end time in days.
    window_days : float
        Rolling look-back ending at *sim_end*.

    Returns
    -------
    pandas.DataFrame
        Indexed by metric code with ``count_in_window`` and ``per_month`` rate.
    """
    active = _accepted_active(df)
    clinical = _clinical(df)
    virtual = _virtual(df)
    kw = {"sim_end": sim_end, "window_days": window_days}

    events = [
        ("referrals_in_window", _in_window(df["arrival_time"], **kw)),
        ("referrals_accepted_in_window", _in_window(df["arrival_time"], **kw) & (df["triage_outcome"] == "accepted")),
        ("assessments_started_in_window", _in_window(df["assessment_start"], **kw) & active),
        ("assessments_finished_in_window", _in_window(df["assessment_completion"], **kw) & active),
        ("diagnoses_in_window", _in_window(df["assessment_completion"], **kw) & active & (df["diagnosis"] == True)),  # noqa: E712
        ("workshops_joined_in_window", _in_window(df["workshop_join_time"], **kw) & clinical),
        ("workshops_started_in_window", _in_window(df["workshop_start_time"], **kw) & clinical),
        ("workshops_finished_in_window", _in_window(df["workshop_completion"], **kw) & clinical),
        ("virtual_completed_in_window", _in_window(df["exit_time"], **kw) & virtual),
        ("all_exits_in_window", _in_window(df["exit_time"], **kw)),
    ]

    months = window_days / 30.4375
    rows = []
    for metric, mask in events:
        n = int(mask.sum())
        rows.append({
            "metric": metric,
            "label": kpi_label(metric),
            "count_in_window": n,
            "per_month": (n / months) if months else np.nan,
        })
    return pd.DataFrame(rows).set_index("metric")


# ============================================================================
# Entry point
# ============================================================================


def build_run_report(
    patients: pd.DataFrame,
    capacity: pd.DataFrame,
    *,
    sim_end: float,
    flow_window_days: float = 365.0,
    model_params: Optional[Mapping[str, Any]] = None,
) -> RunReport:
    """
    Build a full :class:`RunReport` from audit tables.

    Parameters
    ----------
    patients : pandas.DataFrame
        Finalised patient table from :meth:`~des.audit.Audit.finalize`.
    capacity : pandas.DataFrame
        Capacity-day records from the audit.
    sim_end : float
        Simulation horizon in days.
    flow_window_days : float, default 365.0
        Rolling window for flow KPIs (throughputs and flow waits).
    model_params : mapping, optional
        Experiment parameters to store on the report for traceability.

    Returns
    -------
    RunReport
        Complete KPI bundle for one replication.
    """
    sim_end = float(sim_end)
    flow_window_days = float(flow_window_days)

    return RunReport(
        sim_end=sim_end,
        flow_window_days=flow_window_days,
        pathway_funnel=pathway_funnel(patients, sim_end),
        pathway_exits=pathway_exits(patients, sim_end=sim_end, window_days=flow_window_days),
        waits_stock_by_stage=waits_stock_by_stage(patients, sim_end),
        waits_flow_by_stage=waits_flow_by_stage(patients, sim_end=sim_end, window_days=flow_window_days),
        rtt_waits_stock=rtt_waits_stock(patients, sim_end),
        rtt_breaches_stock=rtt_breaches_stock(patients, sim_end),
        capacity_utilisation=capacity_utilisation_summary(capacity),
        assessment_adherence=assessment_adherence(patients),
        workshop_group_stats=workshop_group_stats(patients),
        activity_flow=activity_flow_counts(patients, sim_end=sim_end, window_days=flow_window_days),
        model_params=dict(model_params or {}),
    )


# Backward-compatible aliases (deprecated — prefer new names)
utilisation_summary = capacity_utilisation_summary
throughput_counts = activity_flow_counts


# ============================================================================
# Compact summary for UI / notebooks
# ============================================================================

# Activity-flow metrics included in Run 1 / Run 3 checkpoint history (counts + waits).
_FLOW_HISTORY_ACTIVITIES: tuple[str, ...] = (
    "referrals_in_window",
    "assessments_started_in_window",
    "assessments_finished_in_window",
    "diagnoses_in_window",
    "workshops_finished_in_window",
    "virtual_completed_in_window",
)

# Activity-flow metric → stage wait row in ``waits_flow_by_stage`` (for combined reporting).
_ACTIVITY_TO_WAIT_STAGE: dict[str, str] = {
    "assessments_started_in_window": "wait_referral_to_first_assessment",
    "assessments_finished_in_window": "wait_referral_to_diagnosis",
    "workshops_joined_in_window": "wait_referral_to_workshop_queue",
    "workshops_started_in_window": "wait_referral_to_workshop_start",
    "workshops_finished_in_window": "wait_referral_to_workshop_finish",
    "virtual_completed_in_window": "wait_referral_to_virtual_exit",
}


def _activity_slug(metric: str) -> str:
    return str(metric).removesuffix("_in_window")


def flow_kpi_history_field_names() -> tuple[str, ...]:
    """Column names produced by :func:`flow_kpi_history_fields` (for time-series aggregation)."""
    names: list[str] = []
    for metric in _FLOW_HISTORY_ACTIVITIES:
        slug = _activity_slug(metric)
        names.append(f"flow_count_{slug}")
        names.append(f"flow_per_month_{slug}")
        if metric in _ACTIVITY_TO_WAIT_STAGE:
            names.extend(
                [
                    f"flow_wait_count_{slug}",
                    f"flow_wait_mean_days_{slug}",
                    f"flow_wait_median_days_{slug}",
                ]
            )
    return tuple(names)


FLOW_KPI_HISTORY_KEYS: tuple[str, ...] = flow_kpi_history_field_names()


def flow_kpi_history_fields(report: "RunReport") -> dict[str, Any]:
    """
    Flat flow-window counts and linked stage wait stats (mean / median days).

    Used in Run 1 calibration history and Run 3 policy KPI time series.
    """
    out: dict[str, Any] = {}
    flow = report.activity_flow
    flow_w = report.waits_flow_by_stage

    for metric in _FLOW_HISTORY_ACTIVITIES:
        slug = _activity_slug(metric)
        if metric in flow.index:
            out[f"flow_count_{slug}"] = int(flow.loc[metric, "count_in_window"])
            out[f"flow_per_month_{slug}"] = float(flow.loc[metric, "per_month"])
        else:
            out[f"flow_count_{slug}"] = 0
            out[f"flow_per_month_{slug}"] = float("nan")

        stage = _ACTIVITY_TO_WAIT_STAGE.get(metric)
        if stage is None or flow_w.empty:
            continue
        row = flow_w.loc[flow_w["stage"] == stage]
        if row.empty:
            out[f"flow_wait_count_{slug}"] = 0
            out[f"flow_wait_mean_days_{slug}"] = float("nan")
            out[f"flow_wait_median_days_{slug}"] = float("nan")
            continue
        r = row.iloc[0]
        out[f"flow_wait_count_{slug}"] = int(r.get("n", 0))
        out[f"flow_wait_mean_days_{slug}"] = float(r.get("mean", np.nan))
        out[f"flow_wait_median_days_{slug}"] = float(r.get("median", np.nan))

    return out


_KEY_WAIT_STAGES = (
    "wait_referral_to_first_assessment",
    "wait_referral_to_diagnosis",
)


def waits_stock_mean_median_table(stock: pd.DataFrame) -> pd.DataFrame:
    """Horizon waits by stage — counts plus mean and median (completed and still waiting)."""
    cols = [
        "stage",
        "label",
        "eligible_n",
        "complete_n",
        "still_waiting_n",
        "completed_mean_days",
        "completed_median_days",
        "still_waiting_mean_days",
        "still_waiting_median_days",
    ]
    present = [c for c in cols if c in stock.columns]
    return stock[present].copy()


def waits_flow_mean_median_table(flow_w: pd.DataFrame) -> pd.DataFrame:
    """Flow-window completions per stage with mean and median wait (days)."""
    if flow_w.empty:
        return pd.DataFrame(
            columns=[
                "stage",
                "label",
                "window_days",
                "completions_in_window",
                "mean_wait_days",
                "median_wait_days",
            ]
        )
    out = flow_w.copy()
    if "n" in out.columns:
        out = out.rename(columns={"n": "completions_in_window"})
    rename = {"mean": "mean_wait_days", "median": "median_wait_days"}
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})
    cols = [
        "stage",
        "label",
        "window_days",
        "completions_in_window",
        "mean_wait_days",
        "median_wait_days",
    ]
    return out[[c for c in cols if c in out.columns]]


def rtt_waits_mean_median_table(rtt_waits: pd.DataFrame) -> pd.DataFrame:
    """RTT waits at horizon — cohort size, mean and median days."""
    cols = ["cohort", "label", "n", "mean", "median"]
    present = [c for c in cols if c in rtt_waits.columns]
    out = rtt_waits[present].copy()
    return out.rename(columns={"mean": "mean_wait_days", "median": "median_wait_days"})


def backlog_waiting_time_report(rtt_waits_stock: pd.DataFrame) -> pd.DataFrame:
    """Backlog / PTL waiting-time report at horizon (count, mean and median RTT wait)."""
    if rtt_waits_stock.empty or "cohort" not in rtt_waits_stock.columns:
        return pd.DataFrame(
            columns=["cohort", "label", "n", "mean_wait_days", "median_wait_days"]
        )
    backlog = rtt_waits_stock.loc[rtt_waits_stock["cohort"] == "backlog"]
    if backlog.empty:
        return pd.DataFrame(
            columns=["cohort", "label", "n", "mean_wait_days", "median_wait_days"]
        )
    return rtt_waits_mean_median_table(backlog.reset_index(drop=True))


def flow_counts_with_waits_table(
    activity_flow: pd.DataFrame,
    flow_waits: pd.DataFrame,
) -> pd.DataFrame:
    """
    Flow event counts with mean/median wait for milestones completed in the window.

    Rows follow ``activity_flow`` metrics; wait columns come from the linked stage in
    ``waits_flow_by_stage`` when a mapping exists.
    """
    if activity_flow.empty:
        return pd.DataFrame()

    flow = activity_flow.reset_index()
    wait_by_stage = (
        flow_waits.set_index("stage") if not flow_waits.empty and "stage" in flow_waits.columns else None
    )
    rows: list[dict[str, Any]] = []
    for _, row in flow.iterrows():
        metric = row["metric"]
        entry: dict[str, Any] = {
            "metric": metric,
            "label": row.get("label", kpi_label(str(metric))),
            "count_in_window": int(row.get("count_in_window", 0)),
            "per_month": float(row.get("per_month", np.nan)),
            "wait_stage": _ACTIVITY_TO_WAIT_STAGE.get(str(metric)),
            "completions_in_window": np.nan,
            "mean_wait_days": np.nan,
            "median_wait_days": np.nan,
        }
        stage = entry["wait_stage"]
        if wait_by_stage is not None and stage in wait_by_stage.index:
            w = wait_by_stage.loc[stage]
            entry["completions_in_window"] = int(w.get("n", w.get("completions_in_window", 0)))
            entry["mean_wait_days"] = float(w.get("mean", w.get("mean_wait_days", np.nan)))
            entry["median_wait_days"] = float(w.get("median", w.get("median_wait_days", np.nan)))
        rows.append(entry)
    return pd.DataFrame(rows)


def run_report_summary(report: RunReport) -> dict[str, pd.DataFrame]:
    """Extract compact labelled KPI tables from a :class:`RunReport`."""
    util = report.capacity_utilisation.iloc[0] if not report.capacity_utilisation.empty else {}
    months = max(report.flow_window_days / 30.4375, 1e-9)
    flow = report.activity_flow

    def flow_count(metric: str) -> int:
        if metric not in flow.index:
            return 0
        return int(flow.loc[metric, "count_in_window"])

    assessments = flow_count("assessments_finished_in_window")
    diagnoses = flow_count("diagnoses_in_window")
    first_assess = flow_count("assessments_started_in_window")

    stock = report.waits_stock_by_stage.copy()
    flow_w = report.waits_flow_by_stage.copy()
    key_stock = stock.loc[stock["stage"].isin(_KEY_WAIT_STAGES)].copy()
    key_flow = flow_w.loc[flow_w["stage"].isin(_KEY_WAIT_STAGES)].copy()

    breach_cols = [
        c for c in ["cohort", "label", "n", "over_18_weeks", "over_52_weeks", "over_18_weeks_pct", "over_52_weeks_pct"]
        if c in report.rtt_breaches_stock.columns
    ]

    waits_at_horizon = waits_stock_mean_median_table(stock)
    waits_in_flow_window = waits_flow_mean_median_table(flow_w)
    rtt_waits = rtt_waits_mean_median_table(report.rtt_waits_stock)
    backlog_waiting_time = backlog_waiting_time_report(report.rtt_waits_stock)
    flow_counts_and_waits = flow_counts_with_waits_table(report.activity_flow, flow_w)

    return {
        "pathway_funnel": report.pathway_funnel.reset_index(),
        "waits_stock_by_stage": stock,
        "waits_stock_key_stages": key_stock,
        "waits_at_horizon": waits_at_horizon,
        "waits_flow_by_stage": flow_w,
        "waits_flow_key_stages": key_flow,
        "waits_in_flow_window": waits_in_flow_window,
        "rtt_waits": rtt_waits,
        "backlog_waiting_time_report": backlog_waiting_time,
        "flow_counts_and_waits": flow_counts_and_waits,
        "activity_flow": report.activity_flow.reset_index(),
        "rates": pd.DataFrame([{
            "flow_window_days": report.flow_window_days,
            "first_assessments_per_month": first_assess / months,
            "assessments_per_month": assessments / months,
            "diagnoses_per_month": diagnoses / months,
            "diagnosis_rate_pct": 100.0 * diagnoses / assessments if assessments else np.nan,
            "capacity_used_pct": float(util.get("hours_used_pct", np.nan)),
        }]),
        "breaches": report.rtt_breaches_stock[breach_cols].copy(),
        "headline": pd.DataFrame([report.summary()]),
    }
