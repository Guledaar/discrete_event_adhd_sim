"""Simulation runners for the three-run NHS pathway framework.

Run 1 calibrates horizon **T\\*** against provider KPI targets. Run 2 executes
stochastic baseline replications at **T\\***. Run 3 applies a policy switch at
**T\\*** and measures backlog decay over a post-switch window.

All runs build on :func:`single_run` and :func:`~des.run_report.build_run_report`
for consistent KPI extraction.

Public functions
----------------
single_run, multiple_replication, summarise_replications
    Atomic replication and aggregation.
run1, run2, run3
    Three-run study workflows.
clone_experiment
    Independent copy for a new replication or horizon step.
build_policy_kpi_time_series, summarise_policy_kpi_time_series
    Run 3 monthly KPI series helpers.

Notes
-----
Docstrings follow the NumPy convention (``Parameters``, ``Returns``, …).
"""

import simpy 
import pandas as pd 
import numpy as np
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional
from scipy.stats import t
from joblib import Parallel, delayed
import copy

from des.audit import Audit
from des.collection_window import SimulationPhases
from des.experiment import Experiment
from des.run_report import (
    build_run_report,
    FLOW_KPI_HISTORY_KEYS,
    flow_kpi_history_field_names,
    flow_kpi_history_fields,
    kpi_snapshot,
    normalize_kpi_target,
)
from des.steady_state import count_backlog_in_system
from des.system import AutismPathwaySystem

ProgressCallback = Callable[[Mapping[str, Any]], None]


@dataclass
class ReplicationReport:
    """
    Mean, SD, and 95% CI summaries across stochastic replications.

    Attributes
    ----------
    pathway_funnel, pathway_exits, capacity_utilisation, waits_stock_by_stage,
    rtt_waits_stock, rtt_breaches_stock, waits_flow_by_stage, activity_flow
        Summarised KPI tables produced by :func:`summarise_replications`.
        Each table includes ``stat``, ``mean``, ``sd``, and confidence bounds
        for numeric columns grouped by stage, cohort, or metric as appropriate.
    """

    pathway_funnel: pd.DataFrame
    pathway_exits: pd.DataFrame
    capacity_utilisation: pd.DataFrame
    waits_stock_by_stage: pd.DataFrame
    rtt_waits_stock: pd.DataFrame
    rtt_breaches_stock: pd.DataFrame
    waits_flow_by_stage: pd.DataFrame
    activity_flow: pd.DataFrame



def single_run(
    experiment: Experiment,
    rep: int,
    run_length: int,
    warm_up: int,
    *,
    flow_window_days: float = 365.0,
    with_report: bool = True,
):
    """
    Execute one simulation replication and optionally build a KPI report.

    Parameters
    ----------
    experiment : Experiment
        Configured pathway experiment (copied internally for isolation).
    rep : int
        Replication index; seeds the RNG when ``use_fixed_seed`` is enabled.
    run_length : int
        Total simulation horizon in days.
    warm_up : int
        Warm-up period in days; KPI collection starts after warm-up.
    flow_window_days : float, default 365.0
        Rolling window for flow KPIs passed to :func:`build_run_report`.
    with_report : bool, default True
        When ``False``, return audit tables only (no :class:`RunReport`).

    Returns
    -------
    tuple
        ``(patients, capacity, model_params[, report])`` depending on
        *with_report*.
    """

    # Copy experiment so each replication is independent
    exp = copy.deepcopy(experiment)
    if exp.use_fixed_seed:
        exp.set_random_no_set(rep)   

    collection_period = run_length - warm_up
    if collection_period <= 0:
        raise ValueError("run_length must be greater than warm_up")

    audit = exp.audit
    audit.reset(warmup_days=warm_up, collection_days=collection_period)
    audit.monitoring = True

    env = simpy.Environment()
    system = AutismPathwaySystem(env, exp)
    env.process(system.run())
    env.run(until=run_length)

    patients_pd = audit.finalize()
    capacity_pd = pd.DataFrame(audit.capacity_days)
    model_params = exp.to_kwargs()

    if not with_report:
        return patients_pd, capacity_pd, model_params

    report = build_run_report(
        patients_pd,
        capacity_pd,
        sim_end=run_length,
        flow_window_days=flow_window_days,
        model_params=model_params,
    )
    return patients_pd, capacity_pd, model_params, report



def multiple_replication(
    exp,
    n_reps,
    run_length,
    warm_up,
    *,
    flow_window_days=365.0,
    n_jobs=-1,
    on_progress: ProgressCallback | None = None,
):
    """
    Run multiple independent replications (parallel when possible).

    Parameters
    ----------
    exp : Experiment
        Base experiment configuration shared by all replications.
    n_reps : int
        Number of replications to run.
    run_length : int
        Simulation horizon in days for each replication.
    warm_up : int
        Warm-up period in days.
    flow_window_days : float, default 365.0
        Rolling window for flow KPIs.
    n_jobs : int, default -1
        Joblib parallel worker count; forced to 1 when *on_progress* is set.
    on_progress : callable, optional
        Callback receiving progress event dictionaries (Run 2 UI hook).

    Returns
    -------
    list
        One ``single_run`` result tuple per replication, each including a
        :class:`~des.run_report.RunReport`.
    """

    if on_progress is not None:
        n_jobs = 1

    if on_progress is not None or n_jobs == 1:
        results = []
        run_start = time.perf_counter()
        for rep in range(n_reps):
            rep_start = time.perf_counter()
            if on_progress is not None:
                on_progress(
                    {
                        "run": 2,
                        "event": "rep_start",
                        "rep": rep + 1,
                        "n_reps": n_reps,
                        "elapsed_s": time.perf_counter() - run_start,
                    }
                )
            results.append(
                single_run(
                    exp,
                    rep,
                    run_length,
                    warm_up,
                    flow_window_days=flow_window_days,
                    with_report=True,
                )
            )
            if on_progress is not None:
                snap = kpi_snapshot(results[-1][3])
                on_progress(
                    {
                        "run": 2,
                        "event": "rep_done",
                        "rep": rep + 1,
                        "n_reps": n_reps,
                        "step_elapsed_s": time.perf_counter() - rep_start,
                        "elapsed_s": time.perf_counter() - run_start,
                        "backlog": snap.get("backlog_patients_at_horizon"),
                    }
                )
        return results

    results = Parallel(n_jobs=n_jobs)(
        delayed(single_run)(
            exp,
            rep,
            run_length,
            warm_up,
            flow_window_days=flow_window_days,
            with_report=True,
        )
        for rep in range(n_reps)
    )

    return results




def _summary(values, confidence=0.95):
    """
    Compute mean, SD, and two-sided confidence interval for a numeric series.

    Parameters
    ----------
    values : array-like
        Sample values (non-numeric entries are coerced and dropped).
    confidence : float, default 0.95
        Confidence level for the interval (Student *t*).

    Returns
    -------
    pandas.Series
        Fields ``n``, ``mean``, ``min``, ``max``, ``sd``, ``se``, ``ci_lower``,
        ``ci_upper``.
    """
    values = pd.to_numeric(values, errors="coerce").dropna()
    n = len(values)
    if n == 0:
        return pd.Series(
            {
                "n": 0,
                "mean": float("nan"),
                "min": float("nan"),
                "max": float("nan"),
                "sd": float("nan"),
                "se": float("nan"),
                "ci_lower": float("nan"),
                "ci_upper": float("nan"),
            }
        )
    mean = float(values.mean())
    sd = float(values.std(ddof=1)) if n > 1 else 0.0
    se = sd / np.sqrt(n) if n > 1 else 0.0
    ci = float(t.ppf((1 + confidence) / 2, n - 1) * se) if n > 1 else 0.0
    return pd.Series(
        {
        "n": n,
        "mean": mean,
            "min": float(values.min()),
            "max": float(values.max()),
        "sd": sd,
        "se": se,
            "ci_lower": mean - ci,
            "ci_upper": mean + ci,
        }
    )


def _summary_get(stats: pd.Series, key: str, default: float = float("nan")) -> float:
    try:
        val = stats[key]
        return float(default if pd.isna(val) else val)
    except (KeyError, TypeError, ValueError):
        return float(default)

_SKIP_SUMMARY_COLS = {"rep", "window_days", "window_start"}


def _rep_frame(df: pd.DataFrame, rep: int) -> pd.DataFrame:
    """Reset index labels to columns and tag the replication number."""
    out = df.copy()
    if not isinstance(out.index, pd.RangeIndex):
        out = out.reset_index()
    return out.assign(rep=rep)


def _summarise_table(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    numeric = [
        c
        for c in df.select_dtypes(include=np.number).columns
        if c not in _SKIP_SUMMARY_COLS
    ]
    rows = []
    groups = [((), df)] if not group_cols else df.groupby(group_cols, dropna=False)
    for keys, grp in groups:
        if not isinstance(keys, tuple):
            keys = (keys,)
        base = dict(zip(group_cols, keys))
        for col in numeric:
            row = base.copy()
            row["stat"] = col
            row.update(_summary(grp[col]).to_dict())
            rows.append(row)
    return pd.DataFrame(rows)


def summarise_replications(results: list) -> ReplicationReport:
    """
    Aggregate KPI reports across replications with mean and 95% CI.

    Parameters
    ----------
    results : list
        Output of :func:`multiple_replication`. Each element is a
        ``single_run`` tuple; index ``3`` is the :class:`~des.run_report.RunReport`.

    Returns
    -------
    ReplicationReport
        Summarised tables for funnel, waits, breaches, capacity, and flow KPIs.
        Each numeric column is expanded to ``stat``, ``mean``, ``sd``,
        ``ci_lower``, and ``ci_upper`` rows per group.
    """
    reports = [r[3] for r in results]
    frames = {
        "pathway_funnel": ([_rep_frame(r.pathway_funnel, i) for i, r in enumerate(reports)], ["stage"]),
        "pathway_exits": ([_rep_frame(r.pathway_exits, i) for i, r in enumerate(reports)], ["exit_route"]),
        "capacity_utilisation": ([_rep_frame(r.capacity_utilisation, i) for i, r in enumerate(reports)], []),
        "waits_stock_by_stage": ([_rep_frame(r.waits_stock_by_stage, i) for i, r in enumerate(reports)], ["stage"]),
        "rtt_waits_stock": ([_rep_frame(r.rtt_waits_stock, i) for i, r in enumerate(reports)], ["cohort"]),
        "rtt_breaches_stock": ([_rep_frame(r.rtt_breaches_stock, i) for i, r in enumerate(reports)], ["cohort"]),
        "waits_flow_by_stage": (
            [_rep_frame(r.waits_flow_by_stage, i) for i, r in enumerate(reports)],
            ["stage"],
        ),
        "activity_flow": ([_rep_frame(r.activity_flow, i) for i, r in enumerate(reports)], ["metric"]),
    }
    summarised = {
        name: _summarise_table(pd.concat(parts, ignore_index=True), group_cols)
        for name, (parts, group_cols) in frames.items()
    }
    return ReplicationReport(**summarised)


# ---------------------------------------------------------------------------
# KPI snapshot (canonical definitions in run_report)
# ---------------------------------------------------------------------------


def _mape(sim: Mapping[str, Any], targets: Mapping[str, float], tolerance: float) -> tuple[dict, float, bool]:
    errs = {}
    for name, target in targets.items():
        key, tval = normalize_kpi_target(name, target)
        value = sim.get(key)
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return {name: float("inf")}, float("inf"), False
        errs[name] = abs(float(value) - tval) / max(abs(tval), 1e-9)
    mape_val = sum(errs.values()) / len(errs)
    return errs, mape_val, mape_val <= tolerance


def clone_experiment(experiment: Experiment, *, name: str | None = None, rep: int | None = None) -> Experiment:
    """
    Create an independent copy of an experiment for a new replication.

    Parameters
    ----------
    experiment : Experiment
        Source experiment whose parameters are copied via :meth:`to_kwargs`.
    name : str, optional
        Override ``scenario_name`` on the clone.
    rep : int, optional
        Replication index passed to :meth:`Experiment.set_random_no_set` when
        fixed seeding is enabled.

    Returns
    -------
    Experiment
        Fresh experiment with a new :class:`~des.audit.Audit` instance.
    """
    kw = experiment.to_kwargs()
    if name is not None:
        kw["scenario_name"] = name
    exp = Experiment(audit=Audit(), **kw)
    if rep is not None and exp.use_fixed_seed:
        exp.set_random_no_set(rep)
    return exp


# ---------------------------------------------------------------------------
# Run 1 — calibration: find horizon T* where KPIs match provider targets
# ---------------------------------------------------------------------------

RUN1_HISTORY_SCHEMA_VERSION = 1

def run1(
    experiment: Experiment,
    *,
    targets: Mapping[str, float],
    max_period_days: float,
    step_days: float = 365.0,
    min_period_days: float = 365.0,
    match_tolerance: float = 0.05,
    flow_window_days: float = 365.0,
    rep: int = 0,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """
    Run 1 — calibration to find horizon T*.

    Runs :func:`single_run` at increasing horizons until simulated KPIs are
    within *match_tolerance* MAPE of *targets*, or *max_period_days* is reached.

    Parameters
    ----------
    experiment : Experiment
        Calibrated model configuration.
    targets : mapping
        KPI name → provider target value (e.g. backlog size at horizon).
    max_period_days : float
        Upper search bound for T* in simulation days.
    step_days : float, default 365.0
        Horizon increment between calibration checkpoints.
    min_period_days : float, default 365.0
        First horizon to evaluate.
    match_tolerance : float, default 0.05
        Maximum mean absolute percentage error for a successful match.
    flow_window_days : float, default 365.0
        Rolling window for flow KPIs at each checkpoint.
    rep : int, default 0
        Replication seed for the calibration run.
    on_progress : callable, optional
        Callback for Streamlit / notebook progress reporting.

    Returns
    -------
    dict
        Keys include ``optimal_matching_period_days`` (T*), ``matched``,
        ``history`` (checkpoint DataFrame), ``minimum_mape``, and
        ``report_at_t_star`` (:class:`~des.run_report.RunReport` at T*).
    """
    history = []
    best_mape = float("inf")
    best_row: dict[str, Any] = {}
    t_star = float(max_period_days)
    matched = False
    run_start = time.perf_counter()
    step_idx = 0
    report_at_t_star: Any = None

    t = float(min_period_days)
    while t <= float(max_period_days):
        step_idx += 1
        if on_progress is not None:
            on_progress(
                {
                    "run": 1,
                    "event": "step_start",
                    "step": step_idx,
                    "horizon_days": t,
                    "years": t / 365.25,
                    "elapsed_s": time.perf_counter() - run_start,
                }
            )

        step_start = time.perf_counter()
        exp = clone_experiment(experiment, rep=rep)
        _, _, _, report = single_run(
            exp,
            rep,
            int(t),
            warm_up=0,
            flow_window_days=flow_window_days,
        )
        report_at_t_star = report
        step_elapsed = time.perf_counter() - step_start
        elapsed = time.perf_counter() - run_start

        kpis = kpi_snapshot(report)
        flow_fields = flow_kpi_history_fields(report)
        sim = {**kpis, **flow_fields}
        errs, mape_val, ok = _mape(sim, targets, match_tolerance)
        row = {
            "horizon_days": t,
            "years": t / 365.25,
            "mape": mape_val,
            "matched": ok,
            "step_elapsed_s": step_elapsed,
            "elapsed_s": elapsed,
            **kpis,
            **flow_fields,
            **{f"mape_{k}": v for k, v in errs.items()},
        }
        history.append(row)

        backlog = kpis.get("backlog_patients_at_horizon")
        print(
            f"[Run 1] step {step_idx}: horizon {t:.0f} d ({t / 365.25:.1f} yr) · "
            f"backlog {backlog} · MAPE {mape_val:.3f} · "
            f"step {step_elapsed:.1f}s · total {elapsed:.1f}s",
            flush=True,
        )

        if on_progress is not None:
            on_progress(
                {
                    "run": 1,
                    "event": "step_done",
                    "step": step_idx,
                    "horizon_days": t,
                    "years": t / 365.25,
                    "mape": mape_val,
                    "matched": ok,
                    "backlog": backlog,
                    "step_elapsed_s": step_elapsed,
                    "elapsed_s": elapsed,
                    "errors": dict(errs),
                }
            )

        if mape_val < best_mape:
            best_mape, best_row = mape_val, row
        if ok:
            matched, t_star = True, t
            break
        t += float(step_days)

    total_elapsed = time.perf_counter() - run_start
    if not matched and best_row:
        t_star = float(best_row["horizon_days"])

    if on_progress is not None:
        on_progress(
            {
                "run": 1,
                "event": "complete",
                "matched": matched,
                "t_star": t_star,
                "steps": step_idx,
                "elapsed_s": total_elapsed,
            }
        )

    print(
        f"[Run 1] finished in {total_elapsed:.1f}s · "
        f"T*={t_star:.0f} d · matched={matched} · steps={step_idx}",
        flush=True,
    )

    return {
        "matched": matched,
        "optimal_matching_period_days": t_star,
        "matching_period_days": t_star,
        "match_targets": dict(targets),
        "match_tolerance": float(match_tolerance),
        "minimum_mape": float(best_mape),
        "best_checkpoint": best_row,
        "history": pd.DataFrame(history),
        "history_schema_version": RUN1_HISTORY_SCHEMA_VERSION,
        "flow_window_days": float(flow_window_days),
        "elapsed_seconds": total_elapsed,
        "n_steps": step_idx,
        "report_at_t_star": report_at_t_star,
    }


# ---------------------------------------------------------------------------
# Run 2 — stochastic baseline at T* (same as multiple_replication + summary)
# ---------------------------------------------------------------------------

def run2(
    experiment: Experiment,
    *,
    matching_period_days: float,
    n_reps: int,
    warm_up: int = 0,
    flow_window_days: float = 365.0,
    n_jobs: int = -1,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """
    Run 2 — stochastic baseline at calibrated T*.

    Parameters
    ----------
    experiment : Experiment
        Model configuration calibrated in Run 1.
    matching_period_days : float
        Horizon T* from Run 1 (simulation end in days).
    n_reps : int
        Number of stochastic replications.
    warm_up : int, default 0
        Warm-up period in days (typically 0 at T*).
    flow_window_days : float, default 365.0
        Rolling window for flow KPIs.
    n_jobs : int, default -1
        Parallel worker count for :func:`multiple_replication`.
    on_progress : callable, optional
        Callback for per-replication progress events.

    Returns
    -------
    dict
        Keys include ``summary`` (:class:`ReplicationReport`),
        ``kpi_snapshots``, ``results``, and ``n_reps``.
    """
    run_start = time.perf_counter()
    if on_progress is not None:
        on_progress(
            {
                "run": 2,
                "event": "start",
                "n_reps": n_reps,
                "horizon_days": matching_period_days,
                "elapsed_s": 0.0,
            }
        )

    results = multiple_replication(
        experiment,
        n_reps,
        int(matching_period_days),
        warm_up,
        flow_window_days=flow_window_days,
        n_jobs=n_jobs,
        on_progress=on_progress,
    )
    summary = summarise_replications(results)
    snapshots = [
        {"rep": i, **kpi_snapshot(r[3]), **flow_kpi_history_fields(r[3])}
        for i, r in enumerate(results)
    ]
    elapsed = time.perf_counter() - run_start

    if on_progress is not None:
        on_progress(
            {
                "run": 2,
                "event": "complete",
                "n_reps": n_reps,
                "elapsed_s": elapsed,
            }
        )

    print(
        f"[Run 2] finished {n_reps} rep(s) at T*={matching_period_days:.0f} d in {elapsed:.1f}s",
        flush=True,
    )

    snapshots_df = pd.DataFrame(snapshots)
    flow_cols = flow_kpi_history_field_names()
    flow_summary = pd.DataFrame(
        [
            {"metric": col, **_summary(snapshots_df[col]).to_dict()}
            for col in flow_cols
            if col in snapshots_df.columns
        ]
    )
    backlog_wait_cols = ("backlog_mean_wait_days", "backlog_median_wait_days")
    backlog_wait_summary = pd.DataFrame(
        [
            {"metric": col, **_summary(snapshots_df[col]).to_dict()}
            for col in backlog_wait_cols
            if col in snapshots_df.columns
        ]
    )

    return {
        "optimal_matching_period_days": float(matching_period_days),
        "matching_period_days": float(matching_period_days),
        "n_reps": n_reps,
        "flow_window_days": float(flow_window_days),
        "results": results,
        "summary": summary,
        "kpi_snapshots": snapshots_df,
        "flow_kpi_summary": flow_summary,
        "backlog_wait_summary": backlog_wait_summary,
        "elapsed_seconds": elapsed,
    }


# ---------------------------------------------------------------------------
# Run 3 — policy: run to T*, apply overrides, measure decay window
# ---------------------------------------------------------------------------

POLICY_KPI_TIME_SERIES_KEYS = (
    "backlog_patients_at_horizon",
    "backlog_mean_wait_days",
    "backlog_median_wait_days",
    "backlog_over_18_weeks_pct",
    "backlog_over_52_weeks_pct",
    "assessments_per_month",
    "diagnoses_per_month",
)

def _policy_time_series_kpi_keys() -> tuple[str, ...]:
    """Headline + flow KPI columns for decay time series (runtime-safe if keys evolve)."""
    try:
        flow_keys = flow_kpi_history_field_names()
    except Exception:
        flow_keys = FLOW_KPI_HISTORY_KEYS
    return tuple(dict.fromkeys((*POLICY_KPI_TIME_SERIES_KEYS, *flow_keys)))


def _align_policy_time_series(series_list: list[pd.DataFrame]) -> list[pd.DataFrame]:
    """Ensure every replication frame has the same KPI columns before aggregation."""
    if not series_list:
        return series_list
    index_cols = {"sim_day", "days_since_switch", "years_since_switch", "rep"}
    all_kpis: set[str] = set()
    for s in series_list:
        all_kpis.update(c for c in s.columns if c not in index_cols)
    aligned: list[pd.DataFrame] = []
    for s in series_list:
        frame = s.copy()
        for col in all_kpis:
            if col not in frame.columns:
                frame[col] = float("nan")
        aligned.append(frame)
    return aligned


def build_policy_kpi_time_series(
    patients: pd.DataFrame,
    *,
    switch_at: float,
    run_length: float,
    flow_window_days: float,
    step_days: float = 30.4375,
) -> pd.DataFrame:
    """
    Build KPI time series from T* through the end of a policy decay window.

    Parameters
    ----------
    patients : pandas.DataFrame
        Finalised patient table for one Run 3 arm.
    switch_at : float
        Policy switch time T* in simulation days.
    run_length : float
        End of the decay window (T* + decay period).
    flow_window_days : float
        Rolling window for flow KPIs at each checkpoint.
    step_days : float, default 30.4375
        Spacing between KPI checkpoints (~ one month).

    Returns
    -------
    pandas.DataFrame
        Time series with ``sim_day``, ``years_since_switch``, and headline KPI
        columns listed in :data:`POLICY_KPI_TIME_SERIES_KEYS`.
    """
    rows: list[dict[str, Any]] = []
    switch_at = float(switch_at)
    run_length = float(run_length)
    t = switch_at

    while t <= run_length + 1e-9:
        arrival = pd.to_numeric(patients["arrival_time"], errors="coerce")
        subset = patients.loc[arrival <= t].copy()
        days_since = t - switch_at

        if subset.empty:
            kpis = {key: float("nan") for key in _policy_time_series_kpi_keys()}
        else:
            window = min(float(flow_window_days), max(days_since, 1.0))
            report = build_run_report(
                subset,
                pd.DataFrame(),
                sim_end=t,
                flow_window_days=window,
                model_params={},
            )
            snap = kpi_snapshot(report)
            try:
                flow_fields = flow_kpi_history_fields(report)
            except Exception:
                flow_fields = {}
            kpi_keys = _policy_time_series_kpi_keys()
            kpis = {key: float("nan") for key in kpi_keys}
            for key in POLICY_KPI_TIME_SERIES_KEYS:
                val = snap.get(key)
                kpis[key] = float("nan") if val is None else float(val)
            for key in kpi_keys:
                if key.startswith("flow_"):
                    val = flow_fields.get(key, float("nan"))
                    kpis[key] = float("nan") if val is None else float(val)

        rows.append(
            {
                "sim_day": t,
                "days_since_switch": days_since,
                "years_since_switch": days_since / 365.25,
                **kpis,
            }
        )
        if t >= run_length:
            break
        t = min(t + float(step_days), run_length)

    return pd.DataFrame(rows)


RUN3_ARM_SCALAR_METRICS = (
    "backlog_at_switch",
    "backlog_at_end",
    "backlog_decay",
    "backlog_decay_per_month",
)

RUN3_COMPARISON_METRICS = (
    "delta_backlog_at_end",
    "delta_backlog_decay",
    "delta_backlog_decay_per_month",
)


def summarise_policy_kpi_time_series(series_list: list[pd.DataFrame]) -> pd.DataFrame:
    """
    Aggregate policy KPI time series across replications.

    Parameters
    ----------
    series_list : list of pandas.DataFrame
        Per-replication output of :func:`build_policy_kpi_time_series`.

    Returns
    -------
    pandas.DataFrame
        Mean and 95% CI at each checkpoint; identical to the single input when
        only one replication is supplied.
    """
    if not series_list:
        return pd.DataFrame()
    if len(series_list) == 1:
        return series_list[0].copy()

    series_list = _align_policy_time_series(series_list)
    combined = pd.concat(
        [s.assign(rep=i) for i, s in enumerate(series_list)],
        ignore_index=True,
    )
    index_cols = ["sim_day", "days_since_switch", "years_since_switch"]
    kpi_cols = [
        c
        for c in combined.columns
        if c not in index_cols and c != "rep" and not str(c).endswith("_ci_lower") and not str(c).endswith("_ci_upper")
    ]
    rows: list[dict[str, Any]] = []
    for keys, grp in combined.groupby(index_cols, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = dict(zip(index_cols, keys))
        for kpi in kpi_cols:
            if kpi not in grp.columns:
                continue
            stats = _summary(grp[kpi])
            row[kpi] = _summary_get(stats, "mean")
            if int(stats.get("n", 0)) > 1:
                row[f"{kpi}_ci_lower"] = _summary_get(stats, "ci_lower")
                row[f"{kpi}_ci_upper"] = _summary_get(stats, "ci_upper")
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=[*index_cols, *kpi_cols])
    return pd.DataFrame(rows).sort_values("sim_day").reset_index(drop=True)


def summarise_run3_arm_replications(arms: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Aggregate scalar metrics and KPI time series for one Run 3 arm.

    Parameters
    ----------
    arms : list of dict
        Per-replication arm dicts from :func:`_policy_arm`.

    Returns
    -------
    dict
        Keys: ``n_reps``, ``replications``, ``snapshots`` (per-rep table),
        ``metrics_summary`` (mean / CI by metric), ``kpi_time_series``.
    """
    snapshots = pd.DataFrame(
        [
            {
                "rep": arm["rep"],
                **{m: arm[m] for m in RUN3_ARM_SCALAR_METRICS},
                **arm.get("kpis", {}),
            }
            for arm in arms
        ]
    )

    metric_rows: list[dict[str, Any]] = []
    numeric_cols = snapshots.select_dtypes(include=np.number).columns
    for col in numeric_cols:
        if col == "rep":
            continue
        stats = _summary(snapshots[col])
        metric_rows.append({"metric": col, **stats.to_dict()})

    ts_mean = summarise_policy_kpi_time_series([arm["kpi_time_series"] for arm in arms])

    return {
        "n_reps": len(arms),
        "replications": arms,
        "snapshots": snapshots,
        "metrics_summary": pd.DataFrame(metric_rows),
        "kpi_time_series": ts_mean,
    }


def _aggregate_arm_from_summary(summary: dict[str, Any], *, template: dict[str, Any]) -> dict[str, Any]:
    """Build a single arm dict using mean scalars and mean KPI series (for charts)."""
    agg = dict(template)
    ms = summary.get("metrics_summary")
    if ms is not None and not ms.empty and "mean" in ms.columns:
        metrics = ms.set_index("metric")
        for m in RUN3_ARM_SCALAR_METRICS:
            if m in metrics.index:
                agg[m] = _summary_get(metrics.loc[m], "mean")
    agg["kpi_time_series"] = summary["kpi_time_series"]
    agg["n_reps"] = summary["n_reps"]
    return agg


def _run3_arm_replications(
    experiment: Experiment,
    *,
    n_reps: int,
    switch_at: float,
    decay_period_days: float,
    overrides: dict[str, Any],
    flow_window_days: float,
    kpi_step_days: float,
    arm_name: str,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run one Run 3 arm *n_reps* times and optionally summarise."""
    arms: list[dict[str, Any]] = []
    for r in range(n_reps):
        if on_progress is not None:
            on_progress(
                {
                    "run": 3,
                    "event": "rep_start",
                    "arm": arm_name,
                    "rep": r + 1,
                    "n_reps": n_reps,
                }
            )
        arm = _policy_arm(
            experiment,
            rep=r,
            switch_at=switch_at,
            decay_period_days=decay_period_days,
            overrides=overrides,
            flow_window_days=flow_window_days,
            kpi_step_days=kpi_step_days,
            arm_name=arm_name,
            on_progress=on_progress if n_reps == 1 else None,
        )
        arms.append(arm)
        if on_progress is not None:
            on_progress(
                {
                    "run": 3,
                    "event": "rep_done",
                    "arm": arm_name,
                    "rep": r + 1,
                    "n_reps": n_reps,
                    "backlog_decay": arm["backlog_decay"],
                    "backlog_at_end": arm["backlog_at_end"],
                }
            )

    summary = summarise_run3_arm_replications(arms)
    arm = arms[0] if n_reps == 1 else _aggregate_arm_from_summary(summary, template=arms[0])
    return {
        "n_reps": n_reps,
        "arm": arm,
        "summary": summary,
        "replications": arms,
    }


def _run3_paired_comparison(
    policy_reps: list[dict[str, Any]],
    control_reps: list[dict[str, Any]],
) -> tuple[dict[str, float] | None, pd.DataFrame | None]:
    """Policy minus baseline for matched replication pairs."""
    if not policy_reps or not control_reps:
        return None, None

    delta_rows = [
        {
            "delta_backlog_at_end": p_arm["backlog_at_end"] - c_arm["backlog_at_end"],
            "delta_backlog_decay": p_arm["backlog_decay"] - c_arm["backlog_decay"],
            "delta_backlog_decay_per_month": (
                p_arm["backlog_decay_per_month"] - c_arm["backlog_decay_per_month"]
            ),
        }
        for p_arm, c_arm in zip(policy_reps, control_reps)
    ]
    if len(delta_rows) == 1:
        return delta_rows[0], None

    delta_df = pd.DataFrame(delta_rows)
    comparison = {k: float(delta_df[k].mean()) for k in RUN3_COMPARISON_METRICS}
    comp_rows = []
    for col in RUN3_COMPARISON_METRICS:
        stats = _summary(delta_df[col])
        comp_rows.append({"metric": col, **stats.to_dict()})
    return comparison, pd.DataFrame(comp_rows)


def run3(
    experiment: Experiment,
    *,
    matching_period_days: float,
    decay_period_days: float,
    policy_overrides: Optional[Mapping[str, Any]] = None,
    flow_window_days: Optional[float] = None,
    kpi_step_days: float = 30.4375,
    n_reps: int = 1,
    include_control: bool = True,
    policy_name: str = "policy",
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """
    Run 3 — policy switch at T* and backlog decay measurement.

    Simulates continuously to T*, applies *policy_overrides*, then runs for
    *decay_period_days*.  Optionally compares against a baseline control arm
    with no parameter changes.

    Both baseline and policy arms run *n_reps* times with matched replication
    indices.  Policy−baseline deltas use paired replications (rep *i* vs rep *i*).

    Parameters
    ----------
    experiment : Experiment
        Calibrated model from Run 1.
    matching_period_days : float
        Policy switch time T* in simulation days.
    decay_period_days : float
        Post-switch observation window in days.
    policy_overrides : mapping, optional
        Parameter changes applied at T* on the policy arm.
    flow_window_days : float, optional
        Rolling window for flow KPIs; defaults to *decay_period_days*.
    kpi_step_days : float, default 30.4375
        Spacing between KPI time-series checkpoints.
    n_reps : int, default 1
        Replications per arm (baseline and policy).
    include_control : bool, default True
        When ``True``, run a no-change baseline arm for comparison.
    policy_name : str, default ``"policy"``
        Label for the policy arm in logs and progress events.
    on_progress : callable, optional
        Callback for Run 3 progress events.

    Returns
    -------
    dict
        Keys include ``policy_arm``, ``control_arm``, ``policy_summary``,
        ``comparison``, ``comparison_summary``, ``n_reps``, and
        ``decay_period_days``.
    """
    n_reps = max(int(n_reps), 1)
    control_n_reps = n_reps
    run_start = time.perf_counter()
    if on_progress is not None:
        on_progress(
            {
                "run": 3,
                "event": "start",
                "t_star": matching_period_days,
                "decay_days": decay_period_days,
                "include_control": include_control,
                "n_reps": n_reps,
                "elapsed_s": 0.0,
            }
        )

    kw = {
        "switch_at": float(matching_period_days),
        "decay_period_days": float(decay_period_days),
        "flow_window_days": flow_window_days or float(decay_period_days),
        "kpi_step_days": float(kpi_step_days),
        "on_progress": on_progress,
    }

    control_bundle = None
    control = None
    if include_control:
        control_bundle = _run3_arm_replications(
            experiment,
            n_reps=control_n_reps,
            overrides={},
            arm_name="baseline_control",
            **kw,
        )
        control = control_bundle["arm"]

    policy_bundle = _run3_arm_replications(
        experiment,
        n_reps=n_reps,
        overrides=dict(policy_overrides or {}),
        arm_name=policy_name,
        **kw,
    )
    policy = policy_bundle["arm"]

    comparison = None
    comparison_summary = None
    if control is not None:
        comparison, comparison_summary = _run3_paired_comparison(
            policy_bundle["replications"],
            control_bundle["replications"],
        )

    elapsed = time.perf_counter() - run_start
    if on_progress is not None:
        on_progress(
            {
                "run": 3,
                "event": "complete",
                "elapsed_s": elapsed,
                "policy_backlog_decay": policy["backlog_decay"],
                "n_reps": n_reps,
            }
        )

    print(
        f"[Run 3] finished in {elapsed:.1f}s · policy `{policy_name}` · "
        f"baseline {control_n_reps} rep(s) · policy {n_reps} rep(s)",
        flush=True,
    )

    return {
        "matching_period_days": float(matching_period_days),
        "decay_period_days": float(decay_period_days),
        "flow_window_days": float(flow_window_days or decay_period_days),
        "n_reps": n_reps,
        "control_n_reps": control_n_reps,
        "policy_arm": policy,
        "policy_replications": policy_bundle["replications"],
        "policy_summary": policy_bundle["summary"],
        "control_arm": control,
        "control_replications": control_bundle["replications"] if control_bundle else None,
        "control_summary": control_bundle["summary"] if control_bundle else None,
        "comparison": comparison,
        "comparison_summary": comparison_summary,
        "elapsed_seconds": elapsed,
    }


def _policy_arm(
    experiment: Experiment,
    *,
    rep: int,
    switch_at: float,
    decay_period_days: float,
    overrides: dict[str, Any],
    flow_window_days: float,
    kpi_step_days: float = 30.4375,
    arm_name: str,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """One Run 3 arm — continuous sim with optional policy switch at T*."""
    arm_start = time.perf_counter()

    def _emit(event: str, **extra: Any) -> None:
        if on_progress is None:
            return
        on_progress(
            {
                "run": 3,
                "event": event,
                "arm": arm_name,
                "elapsed_s": time.perf_counter() - arm_start,
                **extra,
            }
        )

    _emit("arm_start", phase="setup", switch_at=switch_at, decay_days=decay_period_days)

    exp = clone_experiment(experiment, name=f"{experiment.scenario_name}_{arm_name}", rep=rep)
    run_length = switch_at + decay_period_days

    phases = SimulationPhases(warmup_end=switch_at, baseline_collection_days=0.0, intervention_collection_days=decay_period_days)
    exp.phases = phases
    exp.switch_time = switch_at
    exp.configure_intervention(overrides)

    audit = exp.audit
    audit.reset(phases=phases)
    audit.monitoring = True

    env = simpy.Environment()
    system = AutismPathwaySystem(env, exp)
    env.process(system.run())

    _emit("arm_phase", phase="baseline_to_tstar", target_day=switch_at)
    baseline_start = time.perf_counter()
    env.run(until=switch_at)
    baseline_elapsed = time.perf_counter() - baseline_start

    wl_switch = count_backlog_in_system(audit, switch_at)
    _emit(
        "arm_phase",
        phase="policy_switch",
        backlog_at_switch=wl_switch,
        phase_elapsed_s=baseline_elapsed,
    )

    exp.activate_intervention(switch_at)
    system.workforce.refresh_capacity_from_experiment()

    _emit("arm_phase", phase="decay_window", target_day=run_length)
    decay_start = time.perf_counter()
    env.run(until=run_length)
    decay_elapsed = time.perf_counter() - decay_start

    wl_end = count_backlog_in_system(audit, run_length)
    _emit(
        "arm_phase",
        phase="simulation_done",
        backlog_at_end=wl_end,
        phase_elapsed_s=decay_elapsed,
    )

    _emit("arm_phase", phase="building_report")
    report_start = time.perf_counter()
    patients_pd = audit.finalize()
    capacity_pd = pd.DataFrame(audit.capacity_days)
    report = build_run_report(
        patients_pd,
        capacity_pd,
        sim_end=run_length,
        flow_window_days=flow_window_days,
        model_params=exp.to_kwargs(),
    )
    decay = float(decay_period_days)
    backlog_decay = wl_switch - wl_end

    _emit("arm_phase", phase="kpi_time_series")
    kpi_time_series = build_policy_kpi_time_series(
        patients_pd,
        switch_at=switch_at,
        run_length=run_length,
        flow_window_days=flow_window_days,
        step_days=kpi_step_days,
    )
    arm_elapsed = time.perf_counter() - arm_start

    _emit(
        "arm_done",
        backlog_at_switch=wl_switch,
        backlog_at_end=wl_end,
        backlog_decay=backlog_decay,
        report_elapsed_s=time.perf_counter() - report_start,
        elapsed_s=arm_elapsed,
    )

    print(
        f"[Run 3] arm `{arm_name}`: T* backlog {wl_switch} → end {wl_end} "
        f"(decay {backlog_decay:+.0f}) in {arm_elapsed:.1f}s",
        flush=True,
    )

    return {
        "arm": arm_name,
        "rep": rep,
        "switch_time": switch_at,
        "run_length": run_length,
        "decay_period_days": decay,
        "overrides": dict(overrides),
        "backlog_at_switch": wl_switch,
        "backlog_at_end": wl_end,
        "backlog_decay": backlog_decay,
        "backlog_decay_per_month": backlog_decay / max(decay / 30.4375, 1e-9),
        "patients": patients_pd,
        "kpi_time_series": kpi_time_series,
        "report": report,
        "kpis": {**kpi_snapshot(report), **flow_kpi_history_fields(report)},
        "elapsed_seconds": arm_elapsed,
    }
