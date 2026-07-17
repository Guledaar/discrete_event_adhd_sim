"""NHS KPI and reporting from finalized patient state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

import numpy as np
import pandas as pd

from des.audit import RTT_18_WEEKS_DAYS
from des.collection_window import CollectionWindow
from des.experiment import Experiment
from des.runs.confidence import ConfidenceIntervalCalculator
from des.system import AutismPathwaySystem

RTT_52_WEEKS_DAYS = 52 * 7
TREATMENT_ROUTES = frozenset({"virtual_support", "workshop_complete"})
_STOP = {
    "referral_rejected": "nullified_referral",
    "admin_removal": "administrative_removal",
    "no_diagnosis": "clinical_decision_not_to_treat",
    "virtual_support": "first_definitive_treatment",
    "workshop_complete": "first_definitive_treatment",
}
_NAN = float("nan")
ValidationStatus = Literal["PASS", "WARNING", "FAIL"]

# Lazy re-exports so notebooks can still `from des.kpi import KPI_GLOSSARY`, etc.
_DOCS = {
    "KPI_GLOSSARY",
    "KPI_CALCULATIONS",
    "kpi_glossary_table",
    "rtt_kpi_definitions_table",
    "display_rtt_kpi_definitions",
    "kpi_results_reference",
    "display_kpi_results_reference",
}


@dataclass
class RunResult:
    """
    Structured output from one simulation run.

    Attributes
    ----------
    summary : dict[str, Any]
        KPI summary dictionary (flat key-value pairs).
    patients : pandas.DataFrame
        One row per patient with RTT milestones and pathway flags.
    appointments : pandas.DataFrame
        One row per completed assessment appointment.
    workshops : pandas.DataFrame
        One row per workshop session delivered.
    resource_days : pandas.DataFrame
        Per-weekday clinician-hour balance.
    queue_snapshots : pandas.DataFrame
        End-of-run resource-queue snapshot (assessment/workshop/total queue
        lengths at the collection horizon).  Empty when no live ``system`` is
        supplied to :func:`compute_kpis`.
    waiting_list : pandas.DataFrame
        End-of-run NHS waiting-list snapshot (one row: ``time`` = horizon,
        ``waiting_list_size`` = incomplete pathways among the collection cohort).
    verified : bool
        ``True`` when internal consistency checks passed.
    validation_report : pandas.DataFrame
        One row per validation rule with ``category``, ``rule``, ``status``,
        and ``message`` columns.  ``verified`` is true exactly when this table
        contains no ``FAIL`` rows.
    export_paths : dict[str, str]
        Paths written by the runner's automatic reporting step.  Empty when
        KPIs are computed directly without runner-managed exports.
    """
    summary: Dict[str, Any]
    patients: pd.DataFrame
    appointments: pd.DataFrame
    workshops: pd.DataFrame
    resource_days: pd.DataFrame
    queue_snapshots: pd.DataFrame
    waiting_list: pd.DataFrame
    verified: bool = True
    validation_report: pd.DataFrame = field(default_factory=pd.DataFrame)
    export_paths: Dict[str, str] = field(default_factory=dict)


class KPIValidationError(RuntimeError):
    """
    Raised when one or more KPI input-validation rules fail.

    Parameters
    ----------
    report : pandas.DataFrame
        Complete structured validation report.  The report is retained on the
        exception so callers can inspect every rule rather than only the first
        failure.
    """

    def __init__(self, report: pd.DataFrame) -> None:
        failed = report.loc[report["status"] == "FAIL"]
        detail = "; ".join(
            f"{row.rule}: {row.message}" for row in failed.itertuples(index=False)
        )
        super().__init__(f"KPI validation failed ({len(failed)} rule(s)): {detail}")
        self.report = report


def _col(df: pd.DataFrame, name: str) -> np.ndarray:
    return df[name].to_numpy(copy=False) if name in df.columns else np.array([])


def _fcol(df: pd.DataFrame, name: str) -> np.ndarray:
    return df[name].to_numpy(dtype=float, copy=False) if name in df.columns else np.full(len(df), np.nan)


def _n(mask: np.ndarray) -> int:
    return int(np.sum(mask))


def _wait_stats(values, prefix: str) -> Dict[str, float]:
    """
    Compute patient-level descriptive waits and a 95% mean interval.

    This interval summarizes patient observations within one simulation run.
    It is not a simulation replication confidence interval and must not be
    interpreted as between-run stochastic uncertainty.  Replication-level
    intervals are computed in :mod:`des.runs.confidence`.

    Parameters
    ----------
    values : array-like
        Wait times in days (``NaN`` values are excluded).
    prefix : str
        Key prefix for the returned dictionary (e.g. ``'rtt_completed'``).

    Returns
    -------
    dict[str, float]
        Dictionary with keys ``{prefix}_mean_days``, ``{prefix}_mode_days``,
        ``{prefix}_median_days``, ``{prefix}_p90_days``, ``{prefix}_max_days``,
        ``{prefix}_ci95_low_days``, ``{prefix}_ci95_high_days``, ``{prefix}_n``.
        Returns an empty dict when *values* contains no valid observations.
    """
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    if v.size == 0:
        return {}
    mean = float(v.mean())
    mode_vals, mode_counts = np.unique(np.round(v), return_counts=True)
    if v.size >= 2:
        ci = ConfidenceIntervalCalculator(0.95).summarise_series(v, kpi=prefix)
        lo, hi = float(ci.ci_low), float(ci.ci_high)
    else:
        lo = hi = mean
    return {
        f"{prefix}_mean_days": mean,
        f"{prefix}_mode_days": float(mode_vals[mode_counts.argmax()]),
        f"{prefix}_median_days": float(np.median(v)),
        f"{prefix}_p90_days": float(np.quantile(v, 0.9)),
        f"{prefix}_max_days": float(v.max()),
        f"{prefix}_ci95_low_days": lo,
        f"{prefix}_ci95_high_days": hi,
        f"{prefix}_n": float(v.size),
    }


def _cohort(patients: pd.DataFrame, start: float, end: float) -> pd.DataFrame:
    if patients.empty:
        return patients.copy()
    t = _fcol(patients, "arrival_time")
    return patients.loc[(t >= start) & (t < end)].copy()


def _enrich_rtt(patients: pd.DataFrame, end: float) -> pd.DataFrame:
    """
    Attach RTT clock start/stop, wait, status, and pathway segment columns.

    Adds the following columns to a copy of *patients*:
    ``rtt_clock_start``, ``rtt_clock_stop``, ``rtt_clock_stop_reason``,
    ``rtt_pathway_status`` (``'nullified'``, ``'completed'``, or
    ``'incomplete'``), ``rtt_wait_days``, ``rtt_first_treatment_start``,
    ``referral_to_assessment``, ``referral_to_exit``, ``workshop_waiting``.

    Parameters
    ----------
    patients : pandas.DataFrame
        Cohort of patients from :meth:`~des.audit.Audit.finalize`.
    end : float
        Collection window end time (used to classify incomplete pathways).

    Returns
    -------
    pandas.DataFrame
        Enriched copy of *patients* with RTT columns added.
    """
    if patients.empty:
        return patients
    df = patients.copy()
    route = _col(df, "exit_route")
    arrival, exit_t = _fcol(df, "arrival_time"), _fcol(df, "exit_time")
    assess_done, ws_start = _fcol(df, "assessment_completion"), _fcol(df, "workshop_start_time")

    # Clock stop depends on how the pathway ended.
    stop = np.select(
        [
            np.isin(route, ["admin_removal", "virtual_support"]),
            route == "no_diagnosis",
            route == "workshop_complete",
        ],
        [exit_t, assess_done, ws_start],
        default=np.nan,
    )
    nullified = route == "referral_rejected"
    incomplete = (~nullified) & (pd.isna(route) | np.isnan(stop) | (stop >= end))
    completed = ~(nullified | incomplete)

    status = np.where(nullified, "nullified", np.where(completed, "completed", "incomplete"))
    reason = np.full(len(df), "incomplete", dtype=object)
    reason[nullified] = "nullified_referral"
    for key, label in _STOP.items():
        if key != "referral_rejected":
            reason[completed & (route == key)] = label

    df["rtt_clock_start"] = np.where(nullified, np.nan, arrival)
    df["rtt_clock_stop"] = np.where(nullified, np.nan, stop)
    df["rtt_clock_stop_reason"] = reason
    df["rtt_pathway_status"] = status
    df["rtt_wait_days"] = np.where(nullified, np.nan, np.where(incomplete, end - arrival, stop - arrival))
    df["rtt_first_treatment_start"] = np.select(
        [route == "virtual_support", route == "workshop_complete"],
        [exit_t, ws_start],
        default=np.nan,
    )
    df["referral_to_assessment"] = _fcol(df, "assessment_start") - arrival
    df["referral_to_exit"] = exit_t - arrival
    df["workshop_waiting"] = ws_start - _fcol(df, "workshop_join_time")
    return df


def _appointments(patients: pd.DataFrame) -> pd.DataFrame:
    """
    Build a one-row-per-appointment DataFrame from patient-level totals.

    Parameters
    ----------
    patients : pandas.DataFrame
        Patient cohort with ``appointments_completed`` and
        ``assessment_hours_consumed`` columns.

    Returns
    -------
    pandas.DataFrame
        Appointment-level records with ``patient_id``, ``appointment_number``,
        ``duration_hours``, and other scheduling columns.
    """
    counts = np.nan_to_num(_fcol(patients, "appointments_completed"), nan=0.0).astype(int)
    keep = counts > 0
    if not keep.any():
        return pd.DataFrame()
    n = counts[keep]
    hours = _fcol(patients, "assessment_hours_consumed")[keep] / n
    starts = np.cumsum(np.r_[0, n[:-1]])
    appt = np.arange(int(n.sum())) - np.repeat(starts, n) + 1
    return pd.DataFrame(
        {
            "patient_id": np.repeat(_fcol(patients, "patient_id")[keep], n).astype(int),
            "appointment_number": appt,
            "duration_hours": np.repeat(hours, n),
            "queue_entry_time": np.repeat(_fcol(patients, "arrival_time")[keep], n),
            "service_start": np.repeat(_fcol(patients, "assessment_start")[keep], n),
            "service_end": None,
            "waiting_time": 0.0,
            "priority": np.where(appt > 1, 1, 2),
            "activity_type": "assessment",
        }
    )


def _workshops(patients: pd.DataFrame, experiment: Experiment) -> pd.DataFrame:
    """
    Build a one-row-per-session DataFrame from workshop group data.

    Parameters
    ----------
    patients : pandas.DataFrame
        Patient cohort with ``workshop_group_id``, ``workshop_start_time``,
        ``workshop_join_time``, and ``workshop_hours_consumed`` columns.
    experiment : Experiment
        Scenario supplying ``workshop_num_sessions`` and
        ``workshop_session_interval_weeks``.

    Returns
    -------
    pandas.DataFrame
        One row per session per workshop group with scheduling and
        clinician-hour metadata.
    """
    g = patients.dropna(subset=["workshop_group_id"]) if not patients.empty else patients
    if g.empty:
        return pd.DataFrame()
    n_sess = experiment.workshop_num_sessions
    gap = experiment.workshop_session_interval_weeks * 7
    rows = []
    for gid, grp in g.groupby("workshop_group_id", sort=False):
        start = float(grp["workshop_start_time"].iloc[0])
        join = float(grp["workshop_join_time"].iloc[0])
        per = float(grp["workshop_hours_consumed"].sum()) / n_sess if n_sess else 0.0
        ids = grp["patient_id"].astype(int).tolist()
        for s in range(1, n_sess + 1):
            rows.append(
                {
                    "workshop_id": int(gid),
                    "patient_ids": ids,
                    "session_number": s,
                    "duration_hours": per,
                    "clinician_hours": per,
                    "start_time": start + (s - 1) * gap,
                    "finish_time": None,
                    "group_size": len(grp),
                    "queue_entry_time": join,
                    "waiting_time": start - join,
                }
            )
    return pd.DataFrame(rows)


def _has_value(series: np.ndarray) -> np.ndarray:
    """Boolean mask of object-array entries that are neither ``None`` nor ``NaN``."""
    if series.size == 0:
        return np.array([], dtype=bool)
    return np.array(
        [v is not None and not (isinstance(v, float) and np.isnan(v)) for v in series],
        dtype=bool,
    )


def _validation_row(
    category: str,
    rule: str,
    status: ValidationStatus,
    message: str,
) -> Dict[str, str]:
    """Build one normalized validation-report row."""
    return {
        "category": category,
        "rule": rule,
        "status": status,
        "message": message,
    }


def _result_row(
    category: str,
    rule: str,
    violations: int,
    pass_message: str,
    fail_message: str,
) -> Dict[str, str]:
    """Return ``PASS`` when *violations* is zero, otherwise ``FAIL``."""
    if violations:
        return _validation_row(
            category,
            rule,
            "FAIL",
            f"{fail_message} ({violations} violation(s))",
        )
    return _validation_row(category, rule, "PASS", pass_message)


def _compute_validation(
    cohort_rtt: pd.DataFrame,
    all_rtt: pd.DataFrame,
    resource: pd.DataFrame,
    end: float,
    system: Optional[AutismPathwaySystem],
) -> pd.DataFrame:
    """
    Evaluate model invariants and return a structured validation report.

    Validation uses the full patient table, including warm-up arrivals.  Rules
    cover patient conservation, timestamp and RTT ordering, appointment
    bookkeeping, diagnosis sequencing, workshop ordering, terminal-state
    consistency, non-negative waits and clinician hours, waiting-list
    identities, and daily/aggregate capacity accounting.

    Parameters
    ----------
    cohort_rtt : pandas.DataFrame
        Arrival-cohort patient table enriched with RTT fields.
    all_rtt : pandas.DataFrame
        Full patient table, including warm-up arrivals, enriched with RTT
        fields at the reporting horizon.
    resource : pandas.DataFrame
        Per-weekday clinician-capacity ledger for the collection window.
    end : float
        Exclusive end of the reporting window.
    system : AutismPathwaySystem, optional
        Live model state used for independent patient-conservation and
        workshop-stock cross-checks.

    Returns
    -------
    pandas.DataFrame
        One row per rule with columns ``category``, ``rule``, ``status`` and
        ``message``.  ``WARNING`` means the rule was not independently
        checkable because optional live-system or capacity data was absent.

    Notes
    -----
    The report is descriptive evidence about internal model consistency; it is
    not an NHS data-quality submission.  :func:`compute_kpis` raises
    :class:`KPIValidationError` after all rules have been evaluated if any row
    has status ``FAIL``.
    """
    rows: List[Dict[str, str]] = []
    pts = all_rtt
    arrival = _fcol(pts, "arrival_time")
    exit_time = _fcol(pts, "exit_time")
    assessment_start = _fcol(pts, "assessment_start")
    assessment_completion = _fcol(pts, "assessment_completion")
    workshop_join = _fcol(pts, "workshop_join_time")
    workshop_start = _fcol(pts, "workshop_start_time")
    workshop_completion = _fcol(pts, "workshop_completion")

    impossible_timestamps = (
        _n(~np.isnan(exit_time) & (exit_time < arrival))
        + _n(~np.isnan(assessment_start) & (assessment_start < arrival))
        + _n(
            ~np.isnan(assessment_completion)
            & ~np.isnan(assessment_start)
            & (assessment_completion < assessment_start)
        )
    )
    rows.append(
        _result_row(
            "patient_conservation",
            "timestamp_ordering",
            impossible_timestamps,
            "Referral, assessment and exit timestamps are chronologically ordered.",
            "One or more patient milestones occur before a prerequisite timestamp",
        )
    )

    completed = _fcol(pts, "appointments_completed")
    required = _fcol(pts, "appointments_required")
    appointment_violations = _n(~np.isnan(required) & (completed > required))
    appointment_violations += _n((completed < 0) | (~np.isnan(required) & (required < 0)))
    rows.append(
        _result_row(
            "appointment_validation",
            "appointment_counts",
            appointment_violations,
            "Appointment counts are non-negative and completed never exceeds required.",
            "Invalid appointment count",
        )
    )

    diagnosed = (
        _col(pts, "diagnosis") == True  # noqa: E712
        if "diagnosis" in pts.columns
        else np.zeros(len(pts), dtype=bool)
    )
    rows.append(
        _result_row(
            "patient_conservation",
            "diagnosis_requires_assessment",
            _n(diagnosed & np.isnan(assessment_completion)),
            "Every positive diagnosis has an assessment completion timestamp.",
            "Positive diagnosis without assessment completion",
        )
    )

    workshop_violations = _n(
        ~np.isnan(workshop_start)
        & ~np.isnan(workshop_join)
        & (workshop_start < workshop_join)
    )
    workshop_violations += _n(
        ~np.isnan(workshop_completion)
        & ~np.isnan(workshop_start)
        & (workshop_completion < workshop_start)
    )
    rows.append(
        _result_row(
            "workshop_validation",
            "workshop_timestamp_ordering",
            workshop_violations,
            "Workshop join, start and completion timestamps are chronologically ordered.",
            "Invalid workshop timestamp ordering",
        )
    )

    has_route = _has_value(_col(pts, "exit_route"))
    exit_violations = _n(~np.isnan(exit_time) & ~has_route)
    exit_violations += _n(has_route & np.isnan(exit_time))
    rows.append(
        _result_row(
            "patient_conservation",
            "exit_consistency",
            exit_violations,
            "Exit route and exit time are populated together.",
            "Exit route/time inconsistency",
        )
    )

    hour_violations = 0
    for name in (
        "clinician_hours_consumed",
        "assessment_hours_consumed",
        "workshop_hours_consumed",
    ):
        hour_violations += _n(_fcol(pts, name) < -1e-9)
    total_hours = _fcol(pts, "clinician_hours_consumed")
    component_hours = _fcol(pts, "assessment_hours_consumed") + _fcol(
        pts, "workshop_hours_consumed"
    )
    hour_violations += _n(~np.isclose(total_hours, component_hours, rtol=1e-9, atol=1e-9))
    rows.append(
        _result_row(
            "capacity_validation",
            "patient_clinician_hours",
            hour_violations,
            "Patient clinician hours are non-negative and equal assessment plus workshop hours.",
            "Invalid patient clinician-hour ledger",
        )
    )

    rtt_start = _fcol(pts, "rtt_clock_start")
    rtt_stop = _fcol(pts, "rtt_clock_stop")
    rtt_wait = _fcol(pts, "rtt_wait_days")
    rtt_status = _col(pts, "rtt_pathway_status")
    rtt_violations = _n(
        ~np.isnan(rtt_stop) & ~np.isnan(rtt_start) & (rtt_stop < rtt_start)
    )
    rtt_violations += _n(~np.isnan(rtt_wait) & (rtt_wait < -1e-9))
    rtt_violations += _n((rtt_status == "nullified") & ~np.isnan(rtt_start))
    rtt_violations += _n((rtt_status == "nullified") & ~np.isnan(rtt_wait))
    rows.append(
        _result_row(
            "rtt_validation",
            "rtt_clock_ordering",
            rtt_violations,
            "RTT clocks and waits are non-negative and nullified referrals have no clock.",
            "Invalid RTT clock or wait",
        )
    )

    wait_violations = 0
    for name in (
        "referral_to_assessment",
        "referral_to_exit",
        "workshop_waiting",
    ):
        values = _fcol(pts, name)
        wait_violations += _n(~np.isnan(values) & (values < -1e-9))
    rows.append(
        _result_row(
            "rtt_validation",
            "pathway_waits_non_negative",
            wait_violations,
            "All derived pathway waiting times are non-negative.",
            "Negative derived pathway wait",
        )
    )

    cohort_incomplete = _n(
        _col(cohort_rtt, "rtt_pathway_status") == "incomplete"
    )
    system_incomplete = _n(rtt_status == "incomplete")
    waiting_violations = int(system_incomplete < cohort_incomplete)
    rows.append(
        _result_row(
            "waiting_list_validation",
            "waiting_list_stock_identity",
            waiting_violations,
            (
                "System PTL is greater than or equal to the arrival-cohort "
                f"waiting list ({system_incomplete} >= {cohort_incomplete})."
            ),
            "System PTL is smaller than the arrival-cohort waiting list",
        )
    )

    if resource.empty:
        rows.append(
            _validation_row(
                "capacity_validation",
                "capacity_accounting",
                "WARNING",
                "No capacity ledger was supplied; capacity accounting was not checked.",
            )
        )
    else:
        released = resource["hours_released"].to_numpy(dtype=float)
        used = resource["hours_used"].to_numpy(dtype=float)
        unused = resource["hours_unused"].to_numpy(dtype=float)
        assessment_used = resource["assessment_hours_used"].to_numpy(dtype=float)
        workshop_used = resource["workshop_hours_used"].to_numpy(dtype=float)
        capacity_violations = _n(
            ~np.isclose(released, used + unused, rtol=1e-9, atol=1e-9)
        )
        capacity_violations += _n(
            ~np.isclose(
                used,
                assessment_used + workshop_used,
                rtol=1e-9,
                atol=1e-9,
            )
        )
        capacity_violations += _n(
            (released < -1e-9)
            | (used < -1e-9)
            | (unused < -1e-9)
            | (assessment_used < -1e-9)
            | (workshop_used < -1e-9)
        )
        rows.append(
            _result_row(
                "capacity_validation",
                "capacity_accounting",
                capacity_violations,
                "Every capacity day balances released, used, unused and activity hours.",
                "Invalid daily capacity ledger",
            )
        )

    if system is None:
        rows.append(
            _validation_row(
                "patient_conservation",
                "live_patient_conservation",
                "WARNING",
                "No live system was supplied; system-to-audit conservation was not checked.",
            )
        )
        rows.append(
            _validation_row(
                "workshop_validation",
                "live_workshop_stock",
                "WARNING",
                "No live system was supplied; workshop waiting/active stock was not checked.",
            )
        )
    else:
        created = int(system.next_patient_id) - 1
        rows.append(
            _result_row(
                "patient_conservation",
                "live_patient_conservation",
                abs(created - len(pts)),
                f"System created {created} patients and audit contains {len(pts)} records.",
                (
                    f"System created {created} patients but audit contains "
                    f"{len(pts)} records"
                ),
            )
        )
        support_type = (
            _col(pts, "support_type")
            if "support_type" in pts.columns
            else np.full(len(pts), None)
        )
        clinical_open = _n(
            (support_type == "clinical")
            & (np.isnan(exit_time) | (exit_time >= end))
        )
        live_workshop_stock = (
            system.workshop_manager.waiting_count
            + len(system.workshop_manager.active_patient_ids)
        )
        rows.append(
            _result_row(
                "workshop_validation",
                "live_workshop_stock",
                abs(live_workshop_stock - clinical_open),
                (
                    "Live workshop waiting plus active stock equals open "
                    f"clinical pathways ({live_workshop_stock})."
                ),
                (
                    f"Live workshop stock {live_workshop_stock} does not equal "
                    f"open clinical pathways {clinical_open}"
                ),
            )
        )

    return pd.DataFrame(rows, columns=["category", "rule", "status", "message"])


def _capacity(resource: pd.DataFrame) -> Dict[str, float]:
    if resource.empty:
        return {}
    rel, used, unused = (float(resource[c].sum()) for c in ("hours_released", "hours_used", "hours_unused"))
    out = {
        "clinician_hours_released": rel,
        "clinician_hours_used": used,
        "clinician_hours_unused": unused,
    }
    if rel <= 0:
        for k in (
            "overall_clinician_utilisation",
            "assessment_utilisation",
            "workshop_utilisation",
        ):
            out[k] = _NAN
        return out
    assess = float(resource["assessment_hours_used"].sum())
    workshop = float(resource["workshop_hours_used"].sum())
    out.update(
        {
            "overall_clinician_utilisation": used / rel,
            "assessment_utilisation": assess / rel,
            "workshop_utilisation": workshop / rel,
        }
    )
    return out


def _in_window(series: np.ndarray, start: float, end: float) -> np.ndarray:
    return ~np.isnan(series) & (series >= start) & (series < end)


@dataclass(frozen=True)
class _EventWindow:
    """Arrays and masks for events occurring in the reporting window."""

    assessment_completion: np.ndarray
    arrival: np.ndarray
    exit_time: np.ndarray
    assessment_start: np.ndarray
    workshop_start: np.ndarray
    exit_route: np.ndarray
    diagnosis: np.ndarray
    support_type: np.ndarray
    assessment_started: np.ndarray
    assessment_completed: np.ndarray
    exited: np.ndarray
    workshop_started: np.ndarray


def _event_window(
    patients: pd.DataFrame,
    start: float,
    end: float,
) -> _EventWindow:
    """
    Build event-time arrays and half-open reporting-window masks.

    Event-window measures include an event when its timestamp is in
    ``[start, end)`` regardless of when the patient arrived.  This is the
    appropriate basis for throughput because work completed during the
    reporting period may belong to patients referred before warm-up ended.
    """
    assessment_completion = _fcol(patients, "assessment_completion")
    arrival = _fcol(patients, "arrival_time")
    exit_time = _fcol(patients, "exit_time")
    assessment_start = _fcol(patients, "assessment_start")
    workshop_start = _fcol(patients, "workshop_start_time")
    exit_route = (
        _col(patients, "exit_route")
        if "exit_route" in patients.columns
        else np.full(len(patients), None)
    )
    diagnosis = (
        _col(patients, "diagnosis")
        if "diagnosis" in patients.columns
        else np.full(len(patients), None)
    )
    support_type = (
        _col(patients, "support_type")
        if "support_type" in patients.columns
        else np.full(len(patients), None)
    )
    return _EventWindow(
        assessment_completion=assessment_completion,
        arrival=arrival,
        exit_time=exit_time,
        assessment_start=assessment_start,
        workshop_start=workshop_start,
        exit_route=exit_route,
        diagnosis=diagnosis,
        support_type=support_type,
        assessment_started=_in_window(assessment_start, start, end),
        assessment_completed=_in_window(assessment_completion, start, end),
        exited=_in_window(exit_time, start, end),
        workshop_started=_in_window(workshop_start, start, end),
    )


def _compute_throughput(
    patients: pd.DataFrame,
    events: _EventWindow,
    experiment: Experiment,
    collection_months: float,
    horizon: float,
) -> tuple[Dict[str, Any], pd.DataFrame, pd.DataFrame]:
    """
    Compute event-window activity and outcome measures.

    Parameters
    ----------
    patients : pandas.DataFrame
        Full patient table, including patients referred during warm-up.
    events : _EventWindow
        Event timestamps and masks for the half-open reporting window.
    experiment : Experiment
        Workshop configuration used to reconstruct session rows.
    collection_months : float
        Reporting-window duration converted using 365.25 / 12 days per month.
    horizon : float
        End-of-run census time used for the clinical-pathway stock.

    Returns
    -------
    tuple
        ``(summary, appointments, workshops)``.  Summary values use event
        dates, never the arrival cohort.
    """
    assessment_finishers = patients.loc[events.assessment_completed]
    workshop_starters = patients.loc[events.workshop_started]
    appointments = _appointments(assessment_finishers)
    workshops = _workshops(workshop_starters, experiment)

    assessments = _n(events.assessment_completed)
    diagnoses = _n(
        events.assessment_completed & (events.diagnosis == True)  # noqa: E712
    )
    no_diagnosis = _n(
        events.assessment_completed & (events.exit_route == "no_diagnosis")
    )
    clinical_enrolled = _n(
        events.assessment_completed
        & (events.diagnosis == True)  # noqa: E712
        & (events.support_type == "clinical")
    )
    rate = lambda value: value / collection_months if collection_months else 0.0

    summary: Dict[str, Any] = {
        "admin_removals": _n(
            events.exited & (events.exit_route == "admin_removal")
        ),
        "assessments_completed_in_window": assessments,
        "assessment_appointments_completed": len(appointments),
        "diagnoses_completed_in_window": diagnoses,
        "no_diagnosis": no_diagnosis,
        "virtual_supports": _n(
            events.exited & (events.exit_route == "virtual_support")
        ),
        "clinical_supports_enrolled": clinical_enrolled,
        "clinical_supports_completed": _n(
            events.exited & (events.exit_route == "workshop_complete")
        ),
        "clinical_supports_in_pathway": _n(
            (events.support_type == "clinical")
            & (np.isnan(events.exit_time) | (events.exit_time >= horizon))
        ),
        "workshop_groups": int(
            workshop_starters["workshop_group_id"].nunique(dropna=True)
            if not workshop_starters.empty
            and "workshop_group_id" in workshop_starters.columns
            else 0
        ),
        "workshop_sessions": len(workshops),
        "assessments_per_month": rate(assessments),
        "diagnoses_per_month": rate(diagnoses),
    }
    return summary, appointments, workshops


@dataclass(frozen=True)
class _RTTResult:
    """RTT summary values and arrays reused by descriptive statistics."""

    summary: Dict[str, Any]
    cohort_incomplete_waits: np.ndarray
    ptl_waits: np.ndarray
    completed_waits: np.ndarray
    first_treatment_waits: np.ndarray
    diagnosis_to_treatment: np.ndarray


def _compute_rtt(
    cohort_rtt: pd.DataFrame,
    all_rtt: pd.DataFrame,
    start: float,
    end: float,
) -> _RTTResult:
    """
    Compute RTT clock counts without changing established NHS methodology.

    Accepted referrals start at ``arrival_time``.  Rejected referrals are
    nullified.  Administrative removal stops at ``exit_time``; a clinical
    decision not to treat stops at ``assessment_completion``; virtual support
    stops at its treatment/exit event; and the clinical workshop pathway stops
    at ``workshop_start_time`` (first definitive treatment, not programme
    completion).

    Cohort incomplete measures use arrivals in ``[start, end)``. Operational
    PTL measures use every pathway still incomplete at ``end``, regardless of
    arrival date. Completed RTT throughput uses clock-stop events in
    ``[start, end)`` across all arrival dates.
    """
    cohort_status = _col(cohort_rtt, "rtt_pathway_status")
    cohort_route = _col(cohort_rtt, "exit_route")
    cohort_waits = _fcol(cohort_rtt, "rtt_wait_days")
    cohort_incomplete = cohort_status == "incomplete"
    cohort_count = _n(cohort_incomplete)
    cohort_incomplete_waits = cohort_waits[cohort_incomplete]
    cohort_over_18 = _n(cohort_incomplete_waits > RTT_18_WEEKS_DAYS)
    cohort_over_52 = _n(cohort_incomplete_waits > RTT_52_WEEKS_DAYS)
    cohort_under_18 = cohort_count - cohort_over_18
    cohort_under_52 = cohort_count - cohort_over_52
    nullified = _n(cohort_status == "nullified")
    referrals = _n(_fcol(cohort_rtt, "arrival_time") < end)
    rejected = _n(cohort_route == "referral_rejected")

    all_status = _col(all_rtt, "rtt_pathway_status")
    all_route = _col(all_rtt, "exit_route")
    all_stop = _fcol(all_rtt, "rtt_clock_stop")
    all_waits = _fcol(all_rtt, "rtt_wait_days")
    first_treatment = _fcol(all_rtt, "rtt_first_treatment_start")
    ptl_incomplete = all_status == "incomplete"
    ptl_waits = all_waits[ptl_incomplete]
    ptl_count = _n(ptl_incomplete)
    ptl_over_18 = _n(ptl_waits > RTT_18_WEEKS_DAYS)
    ptl_over_52 = _n(ptl_waits > RTT_52_WEEKS_DAYS)
    ptl_under_18 = ptl_count - ptl_over_18
    ptl_under_52 = ptl_count - ptl_over_52
    completed_in_window = (all_status == "completed") & _in_window(
        all_stop, start, end
    )
    treatment_in_window = completed_in_window & np.isin(
        all_route, list(TREATMENT_ROUTES)
    )
    diagnosis_to_treatment = np.where(
        treatment_in_window & ~np.isnan(first_treatment),
        first_treatment - _fcol(all_rtt, "assessment_completion"),
        np.nan,
    )[treatment_in_window]

    summary: Dict[str, Any] = {
        "referrals": referrals,
        "referrals_accepted": referrals - rejected,
        "referrals_rejected": rejected,
        "rtt_clocks_started": referrals - nullified,
        "rtt_clocks_nullified": nullified,
        "rtt_completed_pathways": _n(completed_in_window),
        "cohort_incomplete_pathways": cohort_count,
        "rtt_completed_stop_treatment": _n(treatment_in_window),
        "rtt_completed_stop_not_treat": _n(
            completed_in_window & (all_route == "no_diagnosis")
        ),
        "rtt_completed_stop_admin": _n(
            completed_in_window & (all_route == "admin_removal")
        ),
        "cohort_under_18_weeks": cohort_under_18,
        "cohort_over_18_weeks": cohort_over_18,
        "cohort_under_52_weeks": cohort_under_52,
        "cohort_over_52_weeks": cohort_over_52,
        "cohort_under_18_weeks_pct": (
            100.0 * cohort_under_18 / cohort_count
            if cohort_count
            else _NAN
        ),
        "cohort_over_18_weeks_pct": (
            100.0 * cohort_over_18 / cohort_count
            if cohort_count
            else _NAN
        ),
        "cohort_under_52_weeks_pct": (
            100.0 * cohort_under_52 / cohort_count
            if cohort_count
            else _NAN
        ),
        "cohort_over_52_weeks_pct": (
            100.0 * cohort_over_52 / cohort_count
            if cohort_count
            else _NAN
        ),
        "ptl_size": ptl_count,
        "ptl_under_18_weeks": ptl_under_18,
        "ptl_over_18_weeks": ptl_over_18,
        "ptl_under_52_weeks": ptl_under_52,
        "ptl_over_52_weeks": ptl_over_52,
        "ptl_under_18_weeks_pct": (
            100.0 * ptl_under_18 / ptl_count
            if ptl_count
            else _NAN
        ),
        "ptl_over_18_weeks_pct": (
            100.0 * ptl_over_18 / ptl_count
            if ptl_count
            else _NAN
        ),
        "ptl_under_52_weeks_pct": (
            100.0 * ptl_under_52 / ptl_count
            if ptl_count
            else _NAN
        ),
        "ptl_over_52_weeks_pct": (
            100.0 * ptl_over_52 / ptl_count
            if ptl_count
            else _NAN
        ),
    }
    return _RTTResult(
        summary=summary,
        cohort_incomplete_waits=cohort_incomplete_waits,
        ptl_waits=ptl_waits,
        completed_waits=all_waits[
            completed_in_window & (all_route != "admin_removal")
        ],
        first_treatment_waits=all_waits[treatment_in_window],
        diagnosis_to_treatment=diagnosis_to_treatment,
    )


def _compute_waiting_list(
    cohort_rtt: pd.DataFrame,
    all_rtt: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Compute distinct end-of-run waiting-list stocks.

    ``waiting_list_size`` is the incomplete RTT stock among patients arriving
    in the reporting window.  ``waiting_list_size_all_in_system`` is the full
    end-of-run Patient Tracking List (PTL), including warm-up arrivals still
    waiting.  ``first_assessment_waiting_list_size`` and
    ``first_workshop_waiting_list_size`` are stage-specific subsets of that
    overall stock.
    """
    cohort_incomplete = _col(cohort_rtt, "rtt_pathway_status") == "incomplete"
    system_incomplete = _col(all_rtt, "rtt_pathway_status") == "incomplete"
    cohort_count = _n(cohort_incomplete)
    system_count = _n(system_incomplete)

    first_assessment = (
        system_incomplete
        & (_col(all_rtt, "triage_outcome") == "accepted")
        & np.isnan(_fcol(all_rtt, "assessment_start"))
    )
    first_workshop = (
        system_incomplete
        & (_col(all_rtt, "diagnosis") == True)  # noqa: E712
        & (_col(all_rtt, "support_type") == "clinical")
        & ~np.isnan(_fcol(all_rtt, "workshop_join_time"))
        & np.isnan(_fcol(all_rtt, "workshop_start_time"))
    )

    return {
        "waiting_list_size": cohort_count,
        "waiting_list_size_all_in_system": system_count,
        "overall_waiting_list_size": system_count,
        "first_assessment_waiting_list_size": _n(first_assessment),
        "first_workshop_waiting_list_size": _n(first_workshop),
        "waiting_list_snapshot": float(cohort_count),
    }


def _compute_statistics(
    rtt: _RTTResult,
    events: _EventWindow,
) -> Dict[str, float]:
    """
    Compute patient-level descriptive wait statistics.

    The confidence intervals emitted here describe the mean of patient-level
    observations within one simulation run.  They are not simulation-output
    confidence intervals and do not quantify between-replication uncertainty.
    Across-replication confidence intervals remain the responsibility of
    :mod:`des.runs.confidence`.
    """
    first_assessment_wait = (
        events.assessment_start[events.assessment_started]
        - events.arrival[events.assessment_started]
        if len(events.arrival)
        else np.array([], dtype=float)
    )
    assessment_span = (
        events.assessment_completion[events.assessment_completed]
        - events.assessment_start[events.assessment_completed]
        if _n(events.assessment_completed)
        else np.array([], dtype=float)
    )
    statistics: Dict[str, float] = {}
    for values, prefix in (
        (rtt.completed_waits, "rtt_completed"),
        (rtt.first_treatment_waits, "rtt_first_treatment"),
        (first_assessment_wait, "referral_to_first_assessment"),
        (assessment_span, "assessment_to_diagnosis"),
        (rtt.diagnosis_to_treatment, "diagnosis_to_first_treatment"),
    ):
        statistics.update(_wait_stats(values, prefix))
    for scope, waits in (
        ("cohort", rtt.cohort_incomplete_waits),
        ("ptl", rtt.ptl_waits),
    ):
        scoped_statistics = _wait_stats(waits, scope)
        for statistic in ("mean", "mode", "median", "p90", "max"):
            source = f"{scope}_{statistic}_days"
            if source in scoped_statistics:
                statistics[f"{scope}_{statistic}_wait_days"] = (
                    scoped_statistics[source]
                )
        for statistic in ("ci95_low", "ci95_high"):
            source = f"{scope}_{statistic}_days"
            if source in scoped_statistics:
                statistics[f"{scope}_wait_{statistic}_days"] = (
                    scoped_statistics[source]
                )
        source = f"{scope}_n"
        if source in scoped_statistics:
            statistics[f"{scope}_wait_n"] = scoped_statistics[source]
    return statistics


def _add_legacy_aliases(summary: Dict[str, Any]) -> None:
    """Add deprecated KPI names without repeating their calculations."""
    summary["patients_completed_assessment"] = summary[
        "assessments_completed_in_window"
    ]
    summary["diagnoses"] = summary["diagnoses_completed_in_window"]
    summary["mean_waiting_list_size"] = summary["waiting_list_snapshot"]
    summary["mean_overall_rtt_days"] = summary.get(
        "rtt_completed_mean_days", _NAN
    )
    summary["rtt_incomplete_pathways"] = summary["cohort_incomplete_pathways"]
    for threshold in ("18", "52"):
        for side in ("under", "over"):
            cohort_key = f"cohort_{side}_{threshold}_weeks"
            legacy_key = f"rtt_incomplete_{side}_{threshold}_weeks"
            summary[legacy_key] = summary[cohort_key]
            summary[f"{legacy_key}_pct"] = summary[f"{cohort_key}_pct"]
    for statistic in (
        "mean",
        "mode",
        "median",
        "p90",
        "max",
    ):
        cohort_key = f"cohort_{statistic}_wait_days"
        legacy_key = f"rtt_incomplete_{statistic}_days"
        if cohort_key in summary:
            summary[legacy_key] = summary[cohort_key]
    for statistic in ("ci95_low", "ci95_high"):
        cohort_key = f"cohort_wait_{statistic}_days"
        legacy_key = f"rtt_incomplete_{statistic}_days"
        if cohort_key in summary:
            summary[legacy_key] = summary[cohort_key]
    if "cohort_wait_n" in summary:
        summary["rtt_incomplete_n"] = summary["cohort_wait_n"]


def compute_kpis(
    patients: pd.DataFrame,
    window: CollectionWindow,
    experiment: Experiment,
    system: Optional[AutismPathwaySystem] = None,
    capacity_days: Optional[List[Dict[str, float]]] = None,
) -> RunResult:
    """
    Compute NHS KPIs from finalised patient state and return a :class:`RunResult`.

    Arrival-cohort metrics (referrals, waiting_list_size, incomplete RTT among
    new arrivals) are cohort-based.  Throughput and outcome counts use
    **event time in the KPI window** (any arrival date) so that long waits do
    not zero-out assessments, diagnoses, exits, or completed RTT.

    Parameters
    ----------
    patients : pandas.DataFrame
        Patient table from :meth:`~des.audit.Audit.finalize`.
    window : CollectionWindow
        KPI collection window defining ``start`` and ``end``.
    experiment : Experiment
        Scenario configuration (used for workshop stats and metadata).
    system : AutismPathwaySystem, optional
        Live system for end-of-run waiting-list verification.
    capacity_days : list[dict], optional
        Per-weekday clinician-hour balance records from the audit.

    Returns
    -------
    RunResult
        Structured result with ``summary`` KPI dict and supporting DataFrames.

    Raises
    ------
    KPIValidationError
        If any internal consistency rule fails.  The exception's ``report``
        attribute contains every validation result.

    Notes
    -----
    Three reporting bases are intentionally preserved:

    * **Arrival cohort** — patients referred in ``[start, end)``; used for
      referrals and cohort incomplete-pathway measures.
    * **Event window** — events occurring in ``[start, end)`` for any arrival
      date; used for throughput and completed RTT.
    * **End-of-run snapshot** — pathways still open at ``end``; the full-system
      waiting-list value is the NHS Patient Tracking List (PTL).

    The function reports patient-level descriptive wait statistics only.
    Simulation replication confidence intervals are calculated separately in
    :mod:`des.runs.confidence`.
    """
    start, end = window.start, window.end
    cohort = _cohort(patients, start, end)
    resource = pd.DataFrame(capacity_days or [])
    events = _event_window(patients, start, end)
    enriched = _enrich_rtt(cohort, end)
    all_rtt = _enrich_rtt(patients, end)
    validation_report = _compute_validation(
        enriched,
        all_rtt,
        resource,
        end,
        system,
    )
    if (validation_report["status"] == "FAIL").any():
        raise KPIValidationError(validation_report)

    throughput, appointments, workshops = _compute_throughput(
        patients,
        events,
        experiment,
        window.collection_days / 30.4375,
        end,
    )
    rtt = _compute_rtt(enriched, all_rtt, start, end)
    waiting_list = _compute_waiting_list(enriched, all_rtt)

    summary: Dict[str, Any] = {}
    summary.update(rtt.summary)
    summary.update(throughput)
    summary.update(waiting_list)
    summary.update(_capacity(resource))
    summary.update(_compute_statistics(rtt, events))
    _add_legacy_aliases(summary)

    if system is not None:
        assessment_queue = system.workforce.waiting_count
        workshop_queue = system.workshop_manager.waiting_count
        queue_snapshot = pd.DataFrame(
            [
                {
                    "time": end,
                    "assessment_queue": assessment_queue,
                    "workshop_queue": workshop_queue,
                    "total_queue": assessment_queue + workshop_queue,
                }
            ]
        )
    else:
        queue_snapshot = pd.DataFrame()

    return RunResult(
        summary=summary,
        patients=enriched,
        appointments=appointments,
        workshops=workshops,
        resource_days=resource,
        queue_snapshots=queue_snapshot,
        waiting_list=pd.DataFrame(
            [
                {
                    "time": end,
                    "waiting_list_size": waiting_list["waiting_list_size"],
                }
            ]
        ),
        verified=True,
        validation_report=validation_report,
    )


def kpi_from_audit(
    audit: Any,
    system: Optional[AutismPathwaySystem] = None,
    experiment: Optional[Experiment] = None,
) -> RunResult:
    """
    Finalize audit state and compute KPIs in one step.

    Parameters
    ----------
    audit : Audit
        Patient-state recorder from a completed run.
    system : AutismPathwaySystem, optional
        Live system for end-of-run queue verification.
    experiment : Experiment, optional
        Scenario configuration; required when *system* is ``None``.

    Returns
    -------
    RunResult
        Structured KPI result from :func:`compute_kpis`.

    Raises
    ------
    ValueError
        If neither *experiment* nor *system* with an experiment is provided.
    """
    exp = experiment or (system.experiment if system is not None else None)
    if exp is None:
        raise ValueError("experiment or system with experiment is required")
    return compute_kpis(audit.finalize(), audit.window, exp, system, audit.capacity_days)


def __getattr__(name: str):
    if name in _DOCS:
        from des import kpi_docs

        return getattr(kpi_docs, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "KPIValidationError",
    "RTT_52_WEEKS_DAYS",
    "RunResult",
    "TREATMENT_ROUTES",
    "ValidationStatus",
    "compute_kpis",
    "kpi_from_audit",
    *_DOCS,
]
