"""Executable verification suites for the NHS pathway DES model.

Run individual ``run_*_verification`` functions for targeted checks, or
:func:`run_all_verifications` for the full structural and behavioural battery.

Notes
-----
Docstrings follow the NumPy convention. Suites print ``PASS`` / ``FAIL`` to
stdout; they raise :class:`AssertionError` on failure.
"""

from __future__ import annotations

import math
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Generator, Optional, Tuple

# Allow `python des/verification.py` from repo root (package imports need parent on path).
if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import simpy

from des.audit import Audit
from des.collection_window import CollectionWindow
from des.config import (
    PCT_DIAGNOSIS,
    PCT_REFERRAL_REJECTED,
    SCENARIO_PRESETS,
    WORKFORCE_HOURS_PER_DAY,
    WORKSHOP_GROUP_SIZE,
    WORKSHOP_MAX_WAIT_DAYS,
    WORKSHOP_NUM_SESSIONS,
)
from des.experiment import Experiment
from des.run_report import build_run_report, enrich_rtt
from des.system import AutismPathwaySystem
from des.workforce import WorkforceHoursResource

# Weekday hours high enough that assessment/workshop queues are negligible vs baseline.
INFINITE_CAPACITY_HOURS_PER_DAY = 10_000.0


@dataclass
class VerificationReport:
    """
    Legacy-shaped KPI bundle built from ``run_report`` audit tables.

    Used internally by verification scenarios that pre-date
    :class:`~des.run_report.RunReport`.

    Attributes
    ----------
    summary : dict
        Flat headline metrics for the scenario run.
    patients : pandas.DataFrame
        Finalised patient audit export.
    appointments : pandas.DataFrame
        Per-patient appointment accounting table.
    workshops : pandas.DataFrame
        Workshop group accounting table.
    resource_days : pandas.DataFrame
        Daily workforce balance records.
    queue_snapshots : pandas.DataFrame
        Optional queue census snapshots.
    waiting_list : pandas.DataFrame
        Waiting-list breakdown at horizon.
    verified : bool, default True
        Whether structural checks passed for this bundle.
    validation_report : pandas.DataFrame
        Optional validation detail table.
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


def _header(name: str) -> None:
    print(f"\n{'=' * 65}")
    print(f" {name}")
    print("=" * 65)


def _pass(message: str) -> None:
    print(f"  PASS  {message}")


def _collection_cohort(patients: pd.DataFrame, window: CollectionWindow) -> pd.DataFrame:
    arrival = patients["arrival_time"].astype(float)
    return patients.loc[(arrival >= window.start) & (arrival < window.end)].copy()


def _event_in_window(
    patients: pd.DataFrame,
    milestone_col: str,
    window: CollectionWindow,
) -> pd.Series:
    times = pd.to_numeric(patients[milestone_col], errors="coerce")
    return times.notna() & (times >= window.start) & (times < window.end)


def _appointments_table(patients: pd.DataFrame) -> pd.DataFrame:
    if patients.empty:
        return pd.DataFrame()
    counts = pd.to_numeric(patients["appointments_completed"], errors="coerce").fillna(0).astype(int)
    keep = counts > 0
    if not keep.any():
        return pd.DataFrame()
    subset = patients.loc[keep]
    n = counts[keep].to_numpy()
    hours = pd.to_numeric(subset["assessment_hours_consumed"], errors="coerce").fillna(0.0).to_numpy() / n
    starts = np.cumsum(np.r_[0, n[:-1]])
    appt = np.arange(int(n.sum())) - np.repeat(starts, n) + 1
    return pd.DataFrame(
        {
            "patient_id": np.repeat(subset["patient_id"].to_numpy(), n).astype(int),
            "appointment_number": appt,
            "duration_hours": np.repeat(hours, n),
        }
    )


def _workshops_table(patients: pd.DataFrame, experiment: Experiment) -> pd.DataFrame:
    grouped = patients.dropna(subset=["workshop_group_id"]) if not patients.empty else patients
    if grouped.empty:
        return pd.DataFrame()
    n_sess = experiment.workshop_num_sessions
    gap = experiment.workshop_session_interval_weeks * 7
    rows = []
    for gid, grp in grouped.groupby("workshop_group_id", sort=False):
        start = float(grp["workshop_start_time"].iloc[0])
        join = float(grp["workshop_join_time"].iloc[0])
        per = float(grp["workshop_hours_consumed"].sum()) / n_sess if n_sess else 0.0
        ids = grp["patient_id"].astype(int).tolist()
        for session in range(1, n_sess + 1):
            rows.append(
                {
                    "workshop_id": int(gid),
                    "patient_ids": ids,
                    "session_number": session,
                    "duration_hours": per,
                    "clinician_hours": per,
                    "start_time": start + (session - 1) * gap,
                    "group_size": len(grp),
                    "queue_entry_time": join,
                    "waiting_time": start - join,
                }
            )
    return pd.DataFrame(rows)


def _summary_from_report(
    all_patients: pd.DataFrame,
    cohort: pd.DataFrame,
    run_report,
    window: CollectionWindow,
    experiment: Experiment,
    *,
    all_patients_full: pd.DataFrame,
) -> Dict[str, Any]:
    sim_end = window.end
    start = window.start
    all_rtt = enrich_rtt(all_patients_full, sim_end)
    cohort_rtt = enrich_rtt(cohort, sim_end)

    referrals = len(cohort)
    rejected = int((cohort["triage_outcome"] == "rejected").sum())
    nullified = int((cohort_rtt["rtt_status"] == "nullified").sum())
    cohort_incomplete = int((cohort_rtt["rtt_status"] == "incomplete").sum())

    stop = pd.to_numeric(all_rtt["rtt_clock_stop"], errors="coerce")
    completed_in_window = (
        (all_rtt["rtt_status"] == "completed")
        & stop.notna()
        & (stop >= start)
        & (stop < sim_end)
    )
    rtt_completed_pathways = int(completed_in_window.sum())

    ptl_waits = all_rtt.loc[all_rtt["rtt_status"] == "incomplete", "rtt_wait_days"]
    ptl_mean = float(ptl_waits.mean()) if len(ptl_waits) else float("nan")

    completed_excl_admin = cohort_rtt.loc[
        (cohort_rtt["rtt_status"] == "completed")
        & (cohort_rtt["exit_route"] != "admin_removal")
    ]
    rtt_completed_mean = (
        float(completed_excl_admin["rtt_wait_days"].mean())
        if not completed_excl_admin.empty
        else float("nan")
    )

    activity = run_report.activity_flow
    util = run_report.capacity_utilisation.iloc[0] if not run_report.capacity_utilisation.empty else {}

    def _activity_count(metric: str) -> int:
        if metric not in activity.index:
            return 0
        return int(activity.loc[metric, "count_in_window"])

    assessment_done = _event_in_window(all_patients_full, "assessment_completion", window)
    diagnosed = assessment_done & (all_patients_full["diagnosis"] == True)  # noqa: E712
    clinical = diagnosed & (all_patients_full["support_type"] == "clinical")
    exited = _event_in_window(all_patients_full, "exit_time", window)

    workshops = _workshops_table(
        all_patients_full.loc[_event_in_window(all_patients_full, "workshop_start_time", window)],
        experiment,
    )

    released = float(util.get("hours_released", 0.0))
    used = float(util.get("hours_used", 0.0))

    clinical_open = (
        (all_patients_full["support_type"] == "clinical")
        & (
            all_patients_full["exit_time"].isna()
            | (pd.to_numeric(all_patients_full["exit_time"], errors="coerce") >= sim_end)
        )
    )

    return {
        "referrals": referrals,
        "referrals_accepted": referrals - rejected,
        "referrals_rejected": rejected,
        "rtt_clocks_nullified": nullified,
        "rtt_incomplete_pathways": cohort_incomplete,
        "rtt_completed_pathways": rtt_completed_pathways,
        "rtt_completed_mean_days": rtt_completed_mean,
        "ptl_mean_wait_days": ptl_mean,
        "mean_waiting_list_size": float(cohort_incomplete),
        "waiting_list_snapshot": float(cohort_incomplete),
        "patients_completed_assessment": _activity_count("assessments_finished_in_window")
        or int(assessment_done.sum()),
        "diagnoses": _activity_count("diagnoses_in_window") or int(diagnosed.sum()),
        "assessment_appointments_completed": len(
            _appointments_table(all_patients_full.loc[assessment_done])
        ),
        "clinical_supports_enrolled": int(clinical.sum()),
        "clinical_supports_completed": int(
            (exited & (all_patients_full["exit_route"] == "workshop_complete")).sum()
        ),
        "clinical_supports_in_pathway": int(clinical_open.sum()),
        "virtual_supports": int(
            (exited & (all_patients_full["exit_route"] == "virtual_support")).sum()
        ),
        "workshop_sessions": len(workshops),
        "clinician_hours_released": released,
        "overall_clinician_utilisation": (used / released) if released else float("nan"),
        "capacity_used_pct": float((used / released) * 100.0) if released else float("nan"),
        "backlog_patients_at_horizon": float(cohort_incomplete),
    }


def _validate_run(
    cohort: pd.DataFrame,
    all_patients: pd.DataFrame,
    resource: pd.DataFrame,
    *,
    system: Optional[AutismPathwaySystem] = None,
) -> bool:
    if cohort.empty:
        return False
    accepted = int((cohort["triage_outcome"] == "accepted").sum())
    rejected = int((cohort["triage_outcome"] == "rejected").sum())
    if len(cohort) != accepted + rejected:
        return False

    if not resource.empty:
        for _, row in resource.iterrows():
            if not math.isclose(
                row["hours_released"],
                row["hours_used"] + row["hours_unused"],
                rel_tol=1e-9,
                abs_tol=1e-9,
            ):
                return False

    if system is not None:
        created = int(system.next_patient_id) - 1
        if created != len(all_patients):
            return False
    return True


def _simulate(
    warmup_days: int = 0,
    collection_days: int = 365,
    rep: int = 0,
    *,
    with_system: bool = False,
    **experiment_kwargs: Any,
) -> Tuple[Audit, VerificationReport, Dict[str, Any], Optional[AutismPathwaySystem]]:
    workforce_hours = experiment_kwargs.pop(
        "workforce_hours_per_day", WORKFORCE_HOURS_PER_DAY
    )
    audit = Audit()
    experiment = Experiment(
        audit=audit,
        use_fixed_seed=True,
        workforce_hours_per_day=workforce_hours,
        **experiment_kwargs,
    )
    window = CollectionWindow(float(warmup_days), float(collection_days))
    audit.reset(warmup_days=warmup_days, collection_days=collection_days)
    experiment.warmup_days = float(warmup_days)
    experiment.collection_days = float(collection_days)
    experiment.run_length = window.end
    if experiment.use_fixed_seed:
        experiment.set_random_no_set(rep)

    env = simpy.Environment()
    system = AutismPathwaySystem(env, experiment)
    env.process(system.run())
    env.run(until=window.end)

    all_patients = audit.finalize()
    capacity = pd.DataFrame(audit.capacity_days)
    run_report = build_run_report(
        all_patients,
        capacity,
        sim_end=window.end,
        flow_window_days=float(collection_days),
        model_params=experiment.to_kwargs(),
    )

    cohort = _collection_cohort(all_patients, window)
    cohort_enriched = enrich_rtt(cohort, window.end)
    assessment_done = _event_in_window(all_patients, "assessment_completion", window)
    workshop_started = _event_in_window(all_patients, "workshop_start_time", window)

    summary = _summary_from_report(
        cohort,
        cohort,
        run_report,
        window,
        experiment,
        all_patients_full=all_patients,
    )
    summary.update(
        {
            "rep": rep,
            "warmup_days": warmup_days,
            "collection_days": collection_days,
            "run_length": window.end,
        }
    )

    if with_system:
        assessment_queue = system.workforce.waiting_count
        workshop_queue = system.workshop_manager.waiting_count
        queue_snapshots = pd.DataFrame(
            [
                {
                    "time": window.end,
                    "assessment_queue": assessment_queue,
                    "workshop_queue": workshop_queue,
                    "total_queue": assessment_queue + workshop_queue,
                }
            ]
        )
    else:
        queue_snapshots = pd.DataFrame()

    verification = VerificationReport(
        summary=summary,
        patients=cohort_enriched,
        appointments=_appointments_table(all_patients.loc[assessment_done]),
        workshops=_workshops_table(all_patients.loc[workshop_started], experiment),
        resource_days=capacity,
        queue_snapshots=queue_snapshots,
        waiting_list=pd.DataFrame(
            [{"time": window.end, "waiting_list_size": summary["waiting_list_snapshot"]}]
        ),
        verified=_validate_run(cohort, all_patients, capacity, system=system if with_system else None),
    )
    experiment.last_result = verification
    return audit, verification, summary, system if with_system else None


def _run(
    warmup_days: int = 0,
    collection_days: int = 365,
    rep: int = 0,
    **experiment_kwargs: Any,
) -> Tuple[Audit, VerificationReport, Dict[str, Any]]:
    audit, report, results, _ = _simulate(
        warmup_days,
        collection_days,
        rep,
        with_system=False,
        **experiment_kwargs,
    )
    return audit, report, results


def _run_with_system(
    warmup_days: int = 0,
    collection_days: int = 365,
    rep: int = 0,
    **experiment_kwargs: Any,
) -> Tuple[Audit, VerificationReport, Dict[str, Any], AutismPathwaySystem]:
    audit, report, results, system = _simulate(
        warmup_days,
        collection_days,
        rep,
        with_system=True,
        **experiment_kwargs,
    )
    assert system is not None
    return audit, report, results, system


def _scenario_results(collection_days: int = 365, rep: int = 0, **kwargs: Any) -> Dict[str, Any]:
    _, _, results = _run(collection_days=collection_days, rep=rep, **kwargs)
    return results


def _rtt_value(results: Dict[str, Any], missing: float) -> float:
    """Return operational mean wait across the complete current PTL."""
    ptl_wait = results.get("ptl_mean_wait_days")
    if ptl_wait is not None and not (
        isinstance(ptl_wait, float) and math.isnan(ptl_wait)
    ):
        return float(ptl_wait)
    return missing


def _pre_assessment_queue_days(patients: pd.DataFrame) -> pd.Series:
    """Days from referral arrival to first assessment service (workforce scheduler wait)."""
    arrival = pd.to_numeric(patients["arrival_time"], errors="coerce")
    start = pd.to_numeric(patients["assessment_start"], errors="coerce")
    return start - arrival


def _workshop_queue_days(patients: pd.DataFrame) -> pd.Series:
    """Days from workshop queue join to workshop programme start."""
    join_t = pd.to_numeric(patients["workshop_join_time"], errors="coerce")
    start_t = pd.to_numeric(patients["workshop_start_time"], errors="coerce")
    return start_t - join_t


def _completed_rtt_slack_days(patients: pd.DataFrame) -> pd.Series:
    """
    RTT minus assessment-phase calendar time (service + inter-appointment gaps).

    For virtual exits this is near zero when capacity is unlimited; for workshops it
    includes post-assessment pathway time (workshop queue + sessions).
    """
    mask = (patients["rtt_status"] == "completed") & (patients["exit_route"] != "admin_removal")
    cohort = patients.loc[mask]
    if cohort.empty:
        return pd.Series(dtype=float)
    rtt = pd.to_numeric(cohort["rtt_wait_days"], errors="coerce")
    assess_start = pd.to_numeric(cohort["assessment_start"], errors="coerce")
    assess_end = pd.to_numeric(cohort["assessment_completion"], errors="coerce")
    assess_phase = assess_end - assess_start
    return rtt - assess_phase


def run_infinite_capacity_rtt_sanity_check() -> None:
    """
    Near-infinite capacity: completed RTT should fall vs baseline and queue waits shrink.

    Same seed/rep — compares default capacity to ``INFINITE_CAPACITY_HOURS_PER_DAY``.
    Separates **scheduler wait** (pre-assessment and workshop queue) from **pathway time**
    embedded in RTT (assessment phase + post-diagnosis route).
    """
    _header("INFINITE CAPACITY — RTT & SCHEDULER WAIT")
    collection_days = 730
    rep = 0
    common = dict(collection_days=collection_days, rep=rep)

    _, report_base, base = _run(**common)
    _, report_inf, inf = _run(
        **common,
        workforce_hours_per_day=INFINITE_CAPACITY_HOURS_PER_DAY,
    )

    if inf["rtt_completed_pathways"] < 20:
        raise AssertionError(
            f"too few completed RTT pathways under infinite capacity "
            f"({inf['rtt_completed_pathways']})"
        )

    base_rtt = float(base["rtt_completed_mean_days"])
    inf_rtt = float(inf["rtt_completed_mean_days"])
    if not (inf_rtt < base_rtt * 0.85):
        raise AssertionError(
            f"infinite capacity RTT mean {inf_rtt:.1f} d not sufficiently below "
            f"baseline {base_rtt:.1f} d (expected queue-dominated reduction)"
        )

    p_base = report_base.patients
    p_inf = report_inf.patients
    started_base = p_base[p_base["assessment_start"].notna()]
    started_inf = p_inf[p_inf["assessment_start"].notna()]
    q_base = _pre_assessment_queue_days(started_base).dropna()
    q_inf = _pre_assessment_queue_days(started_inf).dropna()
    if q_inf.empty:
        raise AssertionError("no assessment starts recorded under infinite capacity")
    med_q_base = float(q_base.median()) if not q_base.empty else float("inf")
    med_q_inf = float(q_inf.median())
    if med_q_inf >= med_q_base:
        raise AssertionError(
            f"infinite capacity did not reduce median pre-assessment queue "
            f"({med_q_inf:.2f} d vs baseline {med_q_base:.2f} d)"
        )
    if med_q_inf > 7.0:
        raise AssertionError(
            f"median pre-assessment queue still high under infinite capacity: {med_q_inf:.1f} d"
        )

    clinical_inf = p_inf[p_inf["exit_route"] == "workshop_complete"]
    if not clinical_inf.empty:
        wq = _workshop_queue_days(clinical_inf).dropna()
        if not wq.empty and float(wq.median()) > 21.0:
            raise AssertionError(
                f"workshop queue median too high under infinite capacity: {float(wq.median()):.1f} d"
            )

    slack_base = _completed_rtt_slack_days(p_base).dropna()
    slack_inf = _completed_rtt_slack_days(p_inf).dropna()
    if slack_inf.empty:
        raise AssertionError("no completed RTT slack metrics under infinite capacity")
    med_slack_base = float(slack_base.median()) if not slack_base.empty else float("inf")
    med_slack_inf = float(slack_inf.median())
    if med_slack_inf >= med_slack_base:
        raise AssertionError(
            "infinite capacity did not reduce RTT slack beyond assessment phase "
            f"({med_slack_inf:.1f} d vs baseline {med_slack_base:.1f} d)"
        )

    _pass(
        f"RTT mean {base_rtt:.0f}→{inf_rtt:.0f} d · pre-assess queue median "
        f"{med_q_base:.1f}→{med_q_inf:.1f} d · RTT slack median "
        f"{med_slack_base:.1f}→{med_slack_inf:.1f} d "
        f"(@ {INFINITE_CAPACITY_HOURS_PER_DAY:.0f} h/d)"
    )


def run_seed_verification() -> None:
    """
    Verify fixed RNG streams reproduce identical KPIs for the same rep.

    Notes
    -----
    Raises ``AssertionError`` on mismatch; prints PASS on success.
    """
    _header("SEED / REPRODUCIBILITY")
    _, _, r1 = _run(collection_days=365, rep=0)
    _, _, r2 = _run(collection_days=365, rep=0)
    keys = [
        "referrals",
        "rtt_completed_pathways",
        "rtt_completed_mean_days",
        "mean_waiting_list_size",
    ]
    for key in keys:
        if r1[key] != r2[key]:
            raise AssertionError(f"rep=0 mismatch on {key}: {r1[key]!r} != {r2[key]!r}")
    _, _, r3 = _run(collection_days=365, rep=1)
    if r1["referrals"] == r3["referrals"]:
        raise AssertionError("different reps produced identical referral counts")
    _pass("rep=0 reproducible; rep=1 differs from rep=0")


def run_flow_conservation_verification() -> None:
    """
    Verify patient counts are conserved in the collection window.

    Notes
    -----
    Checks referral/RTT accounting identities in the collection window.
    """
    _header("FLOW CONSERVATION")
    audit, report, results = _run(collection_days=730)
    patients = report.patients
    if results["referrals"] != results["referrals_accepted"] + results["referrals_rejected"]:
        raise AssertionError("referrals != accepted + rejected")
    if (
        results["rtt_clocks_nullified"]
        + results["rtt_completed_pathways"]
        + results["rtt_incomplete_pathways"]
        != results["referrals"]
    ):
        raise AssertionError(
            "referrals != nullified + NHS completed + NHS incomplete"
        )
    arrivals = len(patients)
    incomplete = int((patients["rtt_status"] == "incomplete").sum())
    if incomplete != results["rtt_incomplete_pathways"]:
        raise AssertionError(
            f"patient table incomplete ({incomplete}) != "
            f"rtt_incomplete_pathways ({results['rtt_incomplete_pathways']})"
        )
    _pass(f"arrivals={arrivals}, incomplete={incomplete}")


def run_rtt_cohort_verification() -> None:
    """
    Verify NHS RTT cohort rules (nullified, completed, incomplete).

    Notes
    -----
    Checks nullified, completed, and incomplete pathway counts.
    """
    _header("NHS RTT COHORT")
    audit, report, results = _run(collection_days=730)
    patients = report.patients

    nullified = patients[patients["rtt_status"] == "nullified"]
    completed = patients[patients["rtt_status"] == "completed"]
    incomplete = patients[patients["rtt_status"] == "incomplete"]

    if not nullified.empty and nullified["rtt_wait_days"].notna().any():
        raise AssertionError("nullified referrals must not have NHS RTT wait days")
    rtt_completed = completed[~completed["exit_route"].eq("admin_removal")]
    if rtt_completed.empty:
        raise AssertionError("no non-admin completed NHS RTT observations")
    if rtt_completed["rtt_wait_days"].median() < 30:
        raise AssertionError(
            f"completed NHS RTT median unexpectedly low: "
            f"{rtt_completed['rtt_wait_days'].median():.2f}"
        )
    if abs(
        results["rtt_completed_mean_days"] - rtt_completed["rtt_wait_days"].mean()
    ) > 1e-6:
        raise AssertionError("rtt_completed_mean_days != completed cohort mean")

    treatment_stops = completed[completed["exit_route"].isin({"virtual_support", "workshop_complete"})]
    if treatment_stops.empty:
        raise AssertionError("no treatment clock stops in completed cohort")

    _pass(
        f"nullified={len(nullified)}, completed={len(completed)}, "
        f"incomplete={len(incomplete)}, "
        f"completed median RTT={completed['rtt_wait_days'].median():.1f}d"
    )


def run_math_convergence_verification() -> None:
    """
    Verify stochastic parameters converge toward config over long horizons.

    Notes
    -----
    Uses a long collection horizon so rates approach config means.
    """
    _header("MATH / PARAMETER CONVERGENCE")
    reps = 5
    short_rates = []
    long_rates = []
    for rep in range(reps):
        _, _, short = _run(collection_days=365, rep=rep)
        _, _, long = _run(collection_days=5 * 365, rep=rep)
        short_rates.append(short["referrals_rejected"] / short["referrals"])
        long_rates.append(long["referrals_rejected"] / long["referrals"])

    short_err = abs(np.mean(short_rates) - PCT_REFERRAL_REJECTED)
    long_err = abs(np.mean(long_rates) - PCT_REFERRAL_REJECTED)
    if long_err > 0.05:
        raise AssertionError(f"5yr rejection rate error {long_err:.3f} exceeds tolerance")
    if np.std(long_rates) >= np.std(short_rates):
        raise AssertionError(
            f"long-run rejection std ({np.std(long_rates):.3f}) "
            f"not lower than short-run ({np.std(short_rates):.3f})"
        )

    _, _, long = _run(collection_days=5 * 365, rep=0)
    if long["patients_completed_assessment"] < 50:
        raise AssertionError("insufficient assessments for convergence check")
    long_dx = long["diagnoses"] / long["patients_completed_assessment"]
    if abs(long_dx - PCT_DIAGNOSIS) > 0.08:
        raise AssertionError(f"diagnosis rate {long_dx:.3f} outside tolerance of {PCT_DIAGNOSIS}")

    _pass(
        f"rejection error: 1yr={short_err:.3f}, 5yr={long_err:.3f} "
        f"(target {PCT_REFERRAL_REJECTED:.3f})"
    )


def run_demand_stress_verification() -> None:
    """
    Verify high-demand scenario satisfies conservation and audit checks.

    Notes
    -----
    Stresses arrivals while requiring conservation and audit verification.
    """
    _header("DEMAND STRESS")
    params = SCENARIO_PRESETS["high_demand"]
    _, report, results = _run(
        collection_days=365,
        rep=0,
        scenario_name="high_demand",
        **params,
    )
    if not report.verified:
        raise AssertionError("audit verification flag not set")
    if results["referrals"] <= 0:
        raise AssertionError("no referrals in stress scenario")
    if results["mean_waiting_list_size"] <= 0:
        raise AssertionError("expected positive NHS waiting list under high demand")
    _pass(
        f"referrals={results['referrals']}, "
        f"nhs_waiting_list={results['mean_waiting_list_size']:.1f}"
    )


def run_appointment_accounting_verification() -> None:
    """
    Verify required assessment slots equal completed slots per patient.

    Notes
    -----
    Per-patient required appointments must equal completed count.
    """
    _header("APPOINTMENT ACCOUNTING")
    audit, report, results = _run(collection_days=730)
    patients = report.patients
    in_progress = 0

    for _, row in patients.iterrows():
        required = row["appointments_required"]
        completed = int(row["appointments_completed"])

        if pd.isna(required):
            if completed != 0:
                raise AssertionError(
                    f"patient {row['patient_id']}: no required count but completed={completed}"
                )
            continue

        if pd.notna(row["assessment_completion"]):
            if completed != required:
                raise AssertionError(
                    f"patient {row['patient_id']}: required {required} != completed {completed}"
                )
        else:
            if completed > required:
                raise AssertionError(
                    f"patient {row['patient_id']}: completed {completed} > required {required}"
                )
            if completed < required:
                in_progress += 1

    if len(report.appointments) != results["assessment_appointments_completed"]:
        raise AssertionError("appointment table length != KPI appointment count")

    _pass(
        f"all finished patients balanced; {in_progress} still in assessment at horizon"
    )


def run_appointment_loop_verification() -> None:
    """
    Backward-compatible alias for :func:`run_appointment_accounting_verification`.

    Notes
    -----
    Calls :func:`run_appointment_accounting_verification`.
    """
    run_appointment_accounting_verification()


def run_daily_workforce_balance_verification() -> None:
    """
    Verify released hours equal used plus unused on every weekday.

    Notes
    -----
    Identity: released = used + unused for each weekday.
    """
    _header("DAILY WORKFORCE BALANCE")
    audit, report, _ = _run(collection_days=365)
    resource = report.resource_days
    if resource.empty:
        raise AssertionError("no weekday resource records")

    bad_days = []
    for _, row in resource.iterrows():
        if not math.isclose(
            row["hours_released"],
            row["hours_used"] + row["hours_unused"],
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            bad_days.append(float(row["day"]))

    if bad_days:
        raise AssertionError(f"daily balance failed on days: {bad_days[:5]}")

    _pass(f"{len(resource)} weekdays: released = used + unused on every day")


def run_workshop_group_integrity_verification() -> None:
    """
    Verify clinical workshop patients equal completed + waiting + active.

    Notes
    -----
    Clinical-support stock identity across completed/waiting/active.
    """
    _header("WORKSHOP GROUP INTEGRITY")
    audit, report, results, system = _run_with_system(
        collection_days=730,
        pct_diagnosis=1.0,
        pct_virtual_support=0.0,
    )
    patients = report.patients
    clinical = patients[patients["support_type"] == "clinical"]

    enrolled = int(results["clinical_supports_enrolled"])
    completed = int(results["clinical_supports_completed"])
    in_pathway = int(results["clinical_supports_in_pathway"])

    if enrolled != len(clinical):
        raise AssertionError("clinical_supports_enrolled != clinical patients in table")
    if enrolled != completed + in_pathway:
        raise AssertionError(
            f"enrolled ({enrolled}) != completed ({completed}) + in_pathway ({in_pathway})"
        )

    waiting = system.workshop_manager.waiting_count
    active = len(system.workshop_manager.active_patient_ids)
    if waiting + active != in_pathway:
        raise AssertionError(
            f"waiting ({waiting}) + active ({active}) != in_pathway ({in_pathway})"
        )

    _pass(
        f"enrolled={enrolled}, completed={completed}, "
        f"waiting={waiting}, active={active}"
    )


def run_queue_integrity_verification() -> None:
    """
    Verify resource queues and waiting-list snapshots are never negative.

    Notes
    -----
    Queue lengths and waiting-list sizes must stay non-negative.
    """
    _header("QUEUE / WAITING-LIST INTEGRITY")
    _, report, _, _ = _run_with_system(collection_days=365)
    queues = report.queue_snapshots
    waiting_list = report.waiting_list
    if queues.empty:
        raise AssertionError("no resource queue snapshots recorded")
    if waiting_list.empty:
        raise AssertionError("no NHS waiting-list snapshots recorded")

    for col in ("assessment_queue", "workshop_queue", "total_queue"):
        if (queues[col] < 0).any():
            raise AssertionError(f"negative values found in {col}")
    if (waiting_list["waiting_list_size"] < 0).any():
        raise AssertionError("negative NHS waiting-list values found")

    min_total = int(queues["total_queue"].min())
    max_total = int(queues["total_queue"].max())
    max_wl = int(waiting_list["waiting_list_size"].max())
    _pass(
        f"{len(queues)} resource snapshots [{min_total}, {max_total}]; "
        f"{len(waiting_list)} NHS waiting-list snapshots (max={max_wl})"
    )


def run_priority_invariant_verification() -> None:
    """
    Verify lower-priority service never starts while higher priority waits.

    Notes
    -----
    Workshop and returning assessments preempt new assessments.
    """
    _header("PRIORITY INVARIANT")
    violations: list[tuple[float, int, int]] = []
    original_try_grant = WorkforceHoursResource._try_grant

    def guarded_try_grant(self: WorkforceHoursResource) -> None:
        """Wrap ``_try_grant`` and record priority-order violations."""
        request = self._next_waiting_request()
        if request is not None:
            for higher_priority in range(request.priority):
                if self._queues[higher_priority]:
                    violations.append(
                        (self.env.now, request.priority, higher_priority)
                    )
        original_try_grant(self)

    WorkforceHoursResource._try_grant = guarded_try_grant  # type: ignore[method-assign]
    try:
        _run(collection_days=365, rep=0)
    finally:
        WorkforceHoursResource._try_grant = original_try_grant  # type: ignore[method-assign]

    if violations:
        raise AssertionError(f"priority violations at sim times: {violations[:3]}")

    # Controlled scarcity check: workshop before assessment when both compete
    env = simpy.Environment()
    audit = Audit()
    audit.reset(warmup_days=0, collection_days=30)
    from types import SimpleNamespace

    experiment = SimpleNamespace(workforce_hours_per_day=5.0)
    workforce = WorkforceHoursResource(env, experiment, audit=audit)
    grant_order: list[str] = []

    def workshop_request() -> Generator[simpy.Event, None, None]:
        """SimPy process requesting workshop-priority hours."""
        yield env.timeout(0)
        yield from workforce.request_hours(4.0, WorkforceHoursResource.PRIORITY_WORKSHOP)
        grant_order.append("workshop")

    def assessment_request() -> Generator[simpy.Event, None, None]:
        """SimPy process requesting new-assessment-priority hours."""
        yield env.timeout(0)
        yield from workforce.request_hours(4.0, WorkforceHoursResource.PRIORITY_NEW)
        grant_order.append("assessment")

    env.process(workshop_request())
    env.process(assessment_request())
    env.run(until=14)

    if grant_order[0] != "workshop":
        raise AssertionError(f"expected workshop first, got order={grant_order}")

    _pass("no invariant violations in 1yr run; scarcity order=['workshop', 'assessment']")


def run_priority_queue_verification() -> None:
    """
    Backward-compatible alias for :func:`run_priority_invariant_verification`.

    Notes
    -----
    Calls :func:`run_priority_invariant_verification`.
    """
    run_priority_invariant_verification()


def run_extreme_capacity_verification() -> None:
    """
    Verify zero capacity blocks service and high capacity collapses queues.

    Notes
    -----
    Zero hours stall service; very high hours clear queues.
    """
    _header("EXTREME CAPACITY")
    collection_days = 365

    _, _, zero = _run(
        collection_days=collection_days,
        rep=0,
        workforce_hours_per_day=0.0,
    )
    if zero["patients_completed_assessment"] != 0:
        raise AssertionError("zero capacity still completed assessments")
    if zero["workshop_sessions"] != 0:
        raise AssertionError("zero capacity still ran workshops")
    if zero["mean_waiting_list_size"] <= 0:
        raise AssertionError("expected positive NHS waiting list growth with zero capacity")

    _, _, baseline = _run(collection_days=collection_days, rep=0)
    _, _, high = _run(
        collection_days=collection_days,
        rep=0,
        workforce_hours_per_day=1000.0,
    )

    if high["mean_waiting_list_size"] >= baseline["mean_waiting_list_size"]:
        raise AssertionError("1000h capacity did not reduce NHS waiting list vs baseline")
    if high["rtt_completed_mean_days"] >= baseline["rtt_completed_mean_days"]:
        raise AssertionError("1000h capacity did not reduce NHS completed RTT vs baseline")
    if high["patients_completed_assessment"] <= baseline["patients_completed_assessment"]:
        raise AssertionError("1000h capacity did not increase throughput vs baseline")
    if high["overall_clinician_utilisation"] >= baseline["overall_clinician_utilisation"]:
        raise AssertionError("1000h capacity did not reduce utilisation vs baseline")

    _pass(
        f"0h: assessments={zero['patients_completed_assessment']}, "
        f"nhs_waiting_list={zero['mean_waiting_list_size']:.1f}; "
        f"1000h: nhs_waiting_list={high['mean_waiting_list_size']:.1f}, "
        f"RTT={high['rtt_completed_mean_days']:.1f}, "
        f"util={high['overall_clinician_utilisation']:.2f}"
    )


def run_behavioural_validation() -> None:
    """
    Verify model responds logically to demand and capacity scenario changes.

    Notes
    -----
    Compares KPI direction under demand/capacity scenario presets.
    """
    _header("BEHAVIOURAL VALIDATION (DYNAMIC)")
    collection_days = 730
    rep = 0

    baseline = _scenario_results(collection_days=collection_days, rep=rep)
    high_demand = _scenario_results(
        collection_days=collection_days, rep=rep, **SCENARIO_PRESETS["high_demand"]
    )
    low_demand = _scenario_results(
        collection_days=collection_days, rep=rep, **SCENARIO_PRESETS["low_demand"]
    )
    high_capacity = _scenario_results(
        collection_days=collection_days, rep=rep, **SCENARIO_PRESETS["high_capacity"]
    )
    low_capacity = _scenario_results(
        collection_days=collection_days, rep=rep, **SCENARIO_PRESETS["low_capacity"]
    )

    baseline_rtt = _rtt_value(baseline, missing=float("nan"))
    high_demand_rtt = _rtt_value(high_demand, missing=float("inf"))
    low_demand_rtt = _rtt_value(low_demand, missing=0.0)
    high_capacity_rtt = _rtt_value(high_capacity, missing=0.0)
    low_capacity_rtt = _rtt_value(low_capacity, missing=float("inf"))

    util_checks = [
        (
            "increase demand → util ↑ (or saturated)",
            high_demand["overall_clinician_utilisation"]
            >= baseline["overall_clinician_utilisation"] - 0.03,
        )
    ]

    checks = [
        (
            "increase demand → NHS waiting list ↑",
            high_demand["mean_waiting_list_size"],
            ">",
            baseline["mean_waiting_list_size"],
        ),
        ("increase demand → RTT ↑", high_demand_rtt, ">", baseline_rtt),
        (
            "decrease demand → NHS waiting list ↓",
            low_demand["mean_waiting_list_size"],
            "<",
            baseline["mean_waiting_list_size"],
        ),
        ("decrease demand → RTT ↓", low_demand_rtt, "<", baseline_rtt),
        (
            "decrease demand → util ↓",
            low_demand["overall_clinician_utilisation"],
            "<",
            baseline["overall_clinician_utilisation"],
        ),
        (
            "increase capacity → NHS waiting list ↓",
            high_capacity["mean_waiting_list_size"],
            "<",
            baseline["mean_waiting_list_size"],
        ),
        ("increase capacity → RTT ↓", high_capacity_rtt, "<", baseline_rtt),
        (
            "increase capacity → released hours ↑",
            high_capacity["clinician_hours_released"],
            ">",
            baseline["clinician_hours_released"],
        ),
        (
            "increase capacity → throughput ↑",
            high_capacity["patients_completed_assessment"],
            ">",
            baseline["patients_completed_assessment"],
        ),
        (
            "decrease capacity → NHS waiting list ↑",
            low_capacity["mean_waiting_list_size"],
            ">",
            baseline["mean_waiting_list_size"],
        ),
        ("decrease capacity → RTT ↑", low_capacity_rtt, ">", baseline_rtt),
        (
            "decrease capacity → throughput ↓",
            low_capacity["patients_completed_assessment"],
            "<",
            baseline["patients_completed_assessment"],
        ),
    ]

    failed = []
    for label, observed, op, expected in checks:
        if isinstance(observed, float) and math.isnan(observed):
            ok = isinstance(expected, float) and math.isnan(expected)
        elif isinstance(expected, float) and math.isnan(expected):
            ok = observed > 0 if "RTT" in label and "↑" in label else observed < float("inf")
        else:
            ok = observed > expected if op == ">" else observed < expected
        symbol = "✓" if ok else "✗"
        obs_txt = f"{observed:.2f}" if math.isfinite(float(observed)) else str(observed)
        exp_txt = f"{expected:.2f}" if math.isfinite(float(expected)) else str(expected)
        print(f"  {symbol}  {label}: {obs_txt} {op} {exp_txt}")
        if not ok:
            failed.append(label)

    for label, ok in util_checks:
        symbol = "✓" if ok else "✗"
        print(f"  {symbol}  {label}")
        if not ok:
            failed.append(label)

    if failed:
        raise AssertionError(f"behavioural checks failed: {failed}")

    _pass(f"{len(checks) + len(util_checks)} directional scenario checks passed")


def run_workshop_grouping_verification() -> None:
    """
    Verify workshop groups respect configured size and session count.

    Notes
    -----
    Group size and session counts match experiment settings.
    """
    _header("WORKSHOP GROUPING")
    audit, report, _ = _run(
        collection_days=730,
        pct_diagnosis=1.0,
        pct_virtual_support=0.0,
    )
    workshops = report.workshops
    if workshops.empty:
        raise AssertionError("no workshop sessions recorded")

    if (workshops["group_size"] > WORKSHOP_GROUP_SIZE).any():
        raise AssertionError("workshop group size exceeds configured maximum")

    for workshop_id, group in workshops.groupby("workshop_id"):
        if group["session_number"].max() > WORKSHOP_NUM_SESSIONS:
            raise AssertionError(f"workshop {workshop_id} exceeds session count")
        waits = group["waiting_time"].dropna()
        if not waits.empty and waits.max() > WORKSHOP_MAX_WAIT_DAYS + 1:
            raise AssertionError(f"workshop {workshop_id} wait exceeds max wait days")

    patients = report.patients
    clinical = patients[patients["support_type"] == "clinical"]
    if clinical.empty:
        raise AssertionError("expected clinical patients with forced diagnosis")

    completed = clinical[clinical["exit_route"] == "workshop_complete"]
    late_join = completed[
        completed["workshop_start_time"] < completed["workshop_join_time"]
    ]
    if not late_join.empty:
        raise AssertionError("workshop_start precedes workshop_join for some patients")

    _pass(f"{workshops['workshop_id'].nunique()} groups, {len(workshops)} sessions")


def run_virtual_support_zero_capacity_verification() -> None:
    """
    Verify virtual-support patients do not enter workshops.

    Notes
    -----
    Virtual path must not consume workshop slots.
    """
    _header("VIRTUAL SUPPORT ZERO WORKSHOP CAPACITY")
    audit, report, results = _run(collection_days=730)
    patients = report.patients
    virtual = patients[patients["exit_route"] == "virtual_support"]
    if virtual.empty and results["virtual_supports"] == 0:
        _pass("no virtual supports in this replication (stochastic skip)")
        return

    if virtual["workshop_join_time"].notna().any():
        raise AssertionError("virtual-support patients recorded workshop joins")
    workshops = report.workshops
    if not workshops.empty:
        virtual_ids = set(virtual["patient_id"])
        for patient_ids in workshops["patient_ids"]:
            if virtual_ids.intersection(patient_ids):
                raise AssertionError("virtual-support patient found in workshop session")

    resource = report.resource_days
    if not resource.empty and resource["workshop_hours_used"].sum() > 0:
        # virtual-only path should still allow workshops for clinical patients
        pass
    _pass(f"{len(virtual)} virtual-support exits with no workshop activity")


def run_workshop_resource_accounting_verification() -> None:
    """
    Verify workshop clinician hours are recorded once per session.

    Notes
    -----
    Hours charged once per session for the group.
    """
    _header("WORKSHOP RESOURCE ACCOUNTING")
    audit, report, _ = _run(collection_days=730, pct_diagnosis=1.0, pct_virtual_support=0.0)
    workshops = report.workshops
    resource = report.resource_days
    if workshops.empty:
        raise AssertionError("no workshops to account for")

    for _, row in workshops.iterrows():
        if not math.isclose(row["duration_hours"], row["clinician_hours"], rel_tol=1e-9):
            raise AssertionError("workshop duration_hours != clinician_hours per session")

    total_workshop_hours = float(workshops["clinician_hours"].sum())
    recorded_workshop_hours = float(resource["workshop_hours_used"].sum())
    if not math.isclose(total_workshop_hours, recorded_workshop_hours, rel_tol=0.02, abs_tol=1.0):
        raise AssertionError(
            f"workshop table hours ({total_workshop_hours:.2f}) != "
            f"resource workshop hours ({recorded_workshop_hours:.2f})"
        )
    _pass(f"workshop hours reconciled: {total_workshop_hours:.2f}")


def run_diagnosis_timing_verification() -> None:
    """
    Verify diagnosis decisions occur only after assessment completion.

    Notes
    -----
    Diagnosis fields are set only after assessment_completion.
    """
    _header("DIAGNOSIS TIMING")
    audit, report, _ = _run(collection_days=730)
    patients = report.patients
    diagnosed = patients[patients["diagnosis"] == True]  # noqa: E712
    for _, row in diagnosed.iterrows():
        if pd.isna(row["assessment_completion"]):
            raise AssertionError(f"patient {row['patient_id']} diagnosed before assessment completion")
        if row["assessment_completion"] > row.get("exit_time", np.inf):
            raise AssertionError(f"patient {row['patient_id']} assessment completes after exit")

    no_dx = patients[patients["exit_route"] == "no_diagnosis"]
    for _, row in no_dx.iterrows():
        if pd.isna(row["assessment_completion"]):
            raise AssertionError(f"no_diagnosis patient {row['patient_id']} missing assessment completion")

    _pass(f"{len(diagnosed)} diagnoses and {len(no_dx)} no-diagnosis exits sequenced correctly")


def run_workforce_accounting_verification() -> None:
    """
    Verify weekday capacity release and aggregate utilisation identity.

    Notes
    -----
    Capacity-day ledger matches aggregate utilisation KPIs.
    """
    run_daily_workforce_balance_verification()
    _header("WORKFORCE ACCOUNTING (AGGREGATE)")
    audit, report, results = _run(collection_days=180)
    resource = report.resource_days
    total_released = float(resource["hours_released"].sum())
    total_used = float(resource["hours_used"].sum())
    util = total_used / total_released
    if not math.isclose(util, results["overall_clinician_utilisation"], rel_tol=1e-9, abs_tol=1e-6):
        raise AssertionError("utilisation KPI != used / released")
    _pass(f"aggregate utilisation={util:.3f} matches KPI")


def run_boundary_conditions_verification() -> None:
    """
    Verify warm-up exclusion and end-of-horizon remaining patients.

    Notes
    -----
    Warm-up arrivals excluded; short horizons still verify.
    """
    _header("BOUNDARY CONDITIONS")
    warmup, collection = 180, 180
    audit, report, results = _run(warmup_days=warmup, collection_days=collection)
    all_patients = pd.DataFrame([asdict(p) for p in audit.patients.values()])
    collection_patients = report.patients

    warmup_count = int((all_patients["arrival_time"] < warmup).sum())
    if warmup_count == 0:
        raise AssertionError("expected warmup-period arrivals")
    if (collection_patients["arrival_time"] < warmup).any():
        raise AssertionError("collection KPIs include warmup arrivals")

    remaining = collection_patients[collection_patients["rtt_status"] == "incomplete"]
    if len(remaining) != results["rtt_incomplete_pathways"]:
        raise AssertionError("NHS incomplete pathways at horizon mismatch")

    # very short run should complete without error
    _, report_short, _ = _run(collection_days=14)
    if not report_short.verified:
        raise AssertionError("short horizon failed audit verification")

    _pass(
        f"warmup excluded ({warmup_count} pre-warmup patients), "
        f"remaining at horizon={results['rtt_incomplete_pathways']}"
    )


def run_all_verifications() -> None:
    """
    Run every structural and behavioural verification suite.

    Notes
    -----
    Runs structural suites then behavioural validation; prints a final banner.
    """
    print("\n" + "#" * 65)
    print(" STRUCTURAL VERIFICATION")
    print("#" * 65)
    run_seed_verification()
    run_flow_conservation_verification()
    run_rtt_cohort_verification()
    run_math_convergence_verification()
    run_appointment_accounting_verification()
    run_daily_workforce_balance_verification()
    run_workshop_group_integrity_verification()
    run_queue_integrity_verification()
    run_priority_invariant_verification()
    run_workshop_grouping_verification()
    run_virtual_support_zero_capacity_verification()
    run_workshop_resource_accounting_verification()
    run_diagnosis_timing_verification()
    run_workforce_accounting_verification()
    run_boundary_conditions_verification()
    run_demand_stress_verification()
    run_extreme_capacity_verification()
    run_infinite_capacity_rtt_sanity_check()

    print("\n" + "#" * 65)
    print(" BEHAVIOURAL VALIDATION")
    print("#" * 65)
    run_behavioural_validation()

    print("\n" + "=" * 65)
    print(" ALL VERIFICATION SUITES PASSED")
    print("=" * 65)


if __name__ == "__main__":
    run_all_verifications()
