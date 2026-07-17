"""
Three-run framework built on one engine: ``single_run(experiment, ...)``.

Flow
----
Experiment (+ patient Audit) → SimPy system → patient table → NHS KPIs.

Modes of ``single_run``
-----------------------
- plain   — run to horizon → KPI summary          (building block for Run 2)
- match   — step until outcome KPIs close enough  (Run 1 → T*)
- switch  — run to T*, apply overrides, continue  (Run 3)

Public API: ``run1`` / ``run2`` / ``run3`` — pass an ``Experiment``, not JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Union

import pandas as pd
import simpy

from des.audit import Audit
from des.collection_window import CollectionWindow, SimulationPhases
from des.experiment import Experiment
from des.steady_state import count_waiting_list_all_in_system
from des.system import AutismPathwaySystem

PathLike = Union[str, Path]
CheckpointFn = Callable[[float, Dict[str, Any]], None]

# Outcome KPI aliases (fixed inputs like accept_rate belong on Experiment).
KPI_ALIAS = {
    "waiting_list_size": "waiting_list_size_all_in_system",
    "waiting_list_stock": "waiting_list_size_all_in_system",
    "waiting_list": "waiting_list_size_all_in_system",
    "rtt_incomplete": "rtt_incomplete_mean_days",
    "rtt_complete_mean_days": "mean_overall_rtt_days",
    "utilisation": "overall_clinician_utilisation",
    "utilization": "overall_clinician_utilisation",
}
FIXED_INPUTS = frozenset({
    "referrals_per_day", "accept_rate", "reject_rate", "iat",
    "pct_referral_rejected", "pct_admin_removal", "admin_removal",
    "pct_diagnosis", "pct_virtual_support", "workforce_hours_per_day", "capacity",
})
DEFAULT_KPIS = [
    "waiting_list_size_all_in_system",
    "rtt_incomplete_mean_days",
    "rtt_completed_mean_days",
    "referral_to_first_assessment_mean_days",
    "assessments_per_month",
    "diagnoses_per_month",
    "overall_clinician_utilisation",
    "workshop_utilisation",
]


# ---------------------------------------------------------------------------
# Tiny utilities
# ---------------------------------------------------------------------------

def save_json(path: PathLike, payload: Dict[str, Any]) -> Path:
    """
    Serialise *payload* to a JSON file, creating parent directories as needed.

    Parameters
    ----------
    path : str or pathlib.Path
        Destination file path.
    payload : dict[str, Any]
        JSON-serialisable data to write.

    Returns
    -------
    pathlib.Path
        The resolved output path.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str))
    return out


save_matching_period = save_baseline_results = save_policy_results = save_json


def load_matching_period(path: PathLike) -> Dict[str, Any]:
    """
    Load a Run 1 matching-period JSON file and validate its contents.

    Parameters
    ----------
    path : str or pathlib.Path
        Path to the JSON file written by :func:`save_json`.

    Returns
    -------
    dict[str, Any]
        Parsed JSON data.

    Raises
    ------
    KeyError
        If ``'optimal_matching_period_days'`` is not present in the file.
    """
    data = json.loads(Path(path).read_text())
    if "optimal_matching_period_days" not in data:
        raise KeyError(f"{path} missing 'optimal_matching_period_days'")
    return data


def clone(exp: Experiment, name: Optional[str] = None, seed: Optional[int] = None) -> Experiment:
    """
    Create a fresh :class:`~des.experiment.Experiment` cloned from *exp*.

    The clone uses a new :class:`~des.audit.Audit` and derives its
    parameters from :meth:`~des.experiment.Experiment.to_kwargs`.

    Parameters
    ----------
    exp : Experiment
        Source experiment to clone.
    name : str, optional
        Override for ``scenario_name``.  Defaults to the source name.
    seed : int, optional
        If provided and ``use_fixed_seed`` is ``True``, sets the
        replication seed on the clone.

    Returns
    -------
    Experiment
        Freshly initialised clone with an empty audit.
    """
    kw = exp.to_kwargs()
    if name is not None:
        kw["scenario_name"] = name
    out = exp.__class__(audit=Audit(), **kw)
    if seed is not None and out.use_fixed_seed:
        out.set_random_no_set(int(seed))
    return out


def _key(name: str) -> str:
    """Resolve a KPI alias to its canonical internal key."""
    return KPI_ALIAS.get(name, name)


def _mape(
    sim: Mapping[str, Any],
    targets: Mapping[str, float],
    weights: Optional[Mapping[str, float]] = None,
    wl_fallback: Optional[float] = None,
) -> tuple[Dict[str, float], float]:
    """
    Compute per-KPI absolute percentage errors and their weighted mean (MAPE).

    Parameters
    ----------
    sim : Mapping[str, Any]
        Simulated KPI values keyed by canonical name.
    targets : Mapping[str, float]
        Provider target values keyed by KPI name (aliases resolved internally).
    weights : Mapping[str, float], optional
        Per-KPI weights for the aggregate MAPE.  KPIs with weight ≤ 0 are
        excluded.  Equal weights when ``None``.
    wl_fallback : float, optional
        Fallback value for waiting-list KPIs that are missing from *sim*.

    Returns
    -------
    tuple[dict[str, float], float]
        ``(per_kpi_errors, aggregate_mape)`` where both are ``inf`` when any
        required KPI value is unavailable.
    """
    errs: Dict[str, float] = {}
    for k, t in targets.items():
        if weights is not None and float(weights.get(k, 0.0)) <= 0:
            continue
        mk = _key(k)
        v = sim.get(mk)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            if mk.startswith("waiting_list") and wl_fallback is not None:
                v = wl_fallback
            else:
                return {k: float("inf") for k in targets}, float("inf")
        errs[k] = abs(float(v) - float(t)) / max(abs(float(t)), 1e-9)
    if not errs:
        return {}, float("inf")
    wts = [float(weights[k]) if weights else 1.0 for k in errs]
    return errs, sum(w * errs[k] for w, k in zip(wts, errs)) / sum(wts)


def _ci_frame(df: pd.DataFrame, kpis: Sequence[str], level: float = 0.95) -> pd.DataFrame:
    """
    Compute Student-t confidence intervals across replications.

    Parameters
    ----------
    df : pandas.DataFrame
        One row per replication with numeric KPI columns.
    kpis : sequence[str]
        Column names to summarise.
    level : float, optional
        Confidence level.  Default ``0.95``.

    Returns
    -------
    pandas.DataFrame
        CI summary from :class:`~des.runs.confidence.ConfidenceIntervalCalculator`.
    """
    from des.runs.confidence import ConfidenceIntervalCalculator
    return ConfidenceIntervalCalculator(level).summarise_frame(df, kpis)


# ---------------------------------------------------------------------------
# Engine: start DES → patient Audit → NHS KPIs
# ---------------------------------------------------------------------------

def _boot(exp: Experiment, horizon: float):
    """
    Initialise the experiment and start a SimPy environment for a new run.

    Resets the audit in continuous-monitoring mode (no warm-up), creates a
    fresh :class:`~des.system.AutismPathwaySystem`, and starts the arrival
    generator.  Used by :func:`single_run` in match and switch modes.

    Parameters
    ----------
    exp : Experiment
        Scenario to run; mutated in place (audit reset, horizons set).
    horizon : float
        Total simulation horizon in days.

    Returns
    -------
    tuple[simpy.Environment, AutismPathwaySystem]
        The running SimPy environment and the pathway system.
    """
    exp.switch_time = None
    exp.phases = None
    exp.phase = "calibration"
    exp._intervention_overrides = {}
    exp.audit.reset(warmup_days=0.0, collection_days=float(horizon))
    exp.audit.monitoring = True
    exp.warmup_days = 0.0
    exp.collection_days = float(horizon)
    exp.run_length = float(horizon)
    env = simpy.Environment()
    system = AutismPathwaySystem(env, exp)
    env.process(system.run())
    return env, system


def _advance(env: simpy.Environment, until: float) -> None:
    """
    Advance the SimPy environment to simulation time *until* if not already there.

    Parameters
    ----------
    env : simpy.Environment
        The running environment to advance.
    until : float
        Target simulation time in days.
    """
    if env.now < float(until):
        env.run(until=float(until))


def nhs_kpis(exp: Experiment, now: float, window: float = 365.0) -> Dict[str, Any]:
    """
    Compute NHS KPIs from the patient audit for the rolling window ending at *now*.

    Parameters
    ----------
    exp : Experiment
        Experiment whose :attr:`~des.experiment.Experiment.audit` holds
        patient records.
    now : float
        Current simulation time (days); defines the end of the KPI window.
    window : float, optional
        Length of the rolling KPI collection window in days.  Default ``365.0``.

    Returns
    -------
    dict[str, Any]
        KPI summary dict augmented with ``referrals_per_day``,
        ``accept_rate``, and ``_window_days``.
    """
    from des.kpi import compute_kpis

    start = max(0.0, float(now) - float(window))
    days = max(float(now) - start, 1e-9)
    cap = [r for r in exp.audit.capacity_days if start <= float(r["day"]) < float(now)]
    summary = compute_kpis(
        exp.audit.finalize(), CollectionWindow(start, days), exp, None, cap
    ).summary
    # derived rates (diagnostic only — not match targets)
    refs = float(summary.get("referrals", 0) or 0)
    summary["referrals_per_day"] = refs / days if days else 0.0
    summary["accept_rate"] = float(summary.get("referrals_accepted", 0) or 0) / max(refs, 1.0)
    summary["_window_days"] = days
    return summary


def _wl(exp: Experiment, t: float) -> float:
    """Return the waiting-list count (all-in-system) at simulation time *t*."""
    return float(count_waiting_list_all_in_system(exp.audit, t))


def single_run(
    experiment: Experiment,
    rep: int = 0,
    *,
    run_length: float,
    snapshot_window: float = 365.0,
    # match mode (Run 1)
    match_targets: Optional[Mapping[str, float]] = None,
    match_weights: Optional[Mapping[str, float]] = None,
    match_tolerance: float = 0.05,
    check_every: Optional[float] = None,
    min_period: float = 0.0,
    on_checkpoint: Optional[CheckpointFn] = None,
    # switch mode (Run 3)
    switch_at: Optional[float] = None,
    switch_overrides: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute one DES run on *experiment* in plain, match, or switch mode.

    Patient records accumulate on ``experiment.audit``; KPIs are computed
    via :func:`nhs_kpis`. Mode is selected by keyword arguments:

    - **plain** — run to *run_length* (Run 2 building block).
    - **match** — step until MAPE ≤ *match_tolerance* (Run 1).
    - **switch** — run to *switch_at*, apply overrides, continue (Run 3).

    Parameters
    ----------
    experiment : Experiment
        Scenario configuration; mutated in place.
    rep : int, optional
        Replication seed index. Default is 0.
    run_length : float
        Total simulation horizon in days.
    snapshot_window : float, optional
        Rolling KPI window length. Default is 365.0.
    match_targets : Mapping[str, float], optional
        Provider KPI targets for match mode (Run 1).
    match_weights : Mapping[str, float], optional
        Per-KPI MAPE weights for match mode.
    match_tolerance : float, optional
        MAPE stopping threshold. Default is 0.05.
    check_every : float, optional
        Horizon step size for match mode.
    min_period : float, optional
        Earliest candidate horizon in match mode.
    on_checkpoint : callable, optional
        ``(time, row)`` callback invoked at each match checkpoint.
    switch_at : float, optional
        SwitchTime T* for switch mode (Run 3).
    switch_overrides : Mapping[str, Any], optional
        Experiment attribute overrides applied at *switch_at*.

    Returns
    -------
    dict[str, Any]
        Mode-specific result dict (KPI summary, calibration history, or
        policy-arm metrics).

    Raises
    ------
    ValueError
        If fixed model inputs appear in *match_targets*, or if
        ``run_length <= switch_at`` in switch mode.
    """
    if experiment.use_fixed_seed:
        experiment.set_random_no_set(int(rep))

    # --- match: grow until MAPE ≤ tolerance ---
    if match_targets and check_every is not None:
        bad = [k for k in match_targets if k in FIXED_INPUTS or _key(k) in FIXED_INPUTS]
        if bad:
            raise ValueError(f"Fixed model inputs cannot be match targets: {bad}")
        targets = {str(k): float(v) for k, v in match_targets.items()}
        env, _ = _boot(experiment, float(run_length) + float(snapshot_window))
        history, best_mape, best = [], float("inf"), {}
        matched, t_star = False, float(run_length)
        t = 0.0
        while t < run_length:
            t = min(t + float(check_every), float(run_length))
            if t < min_period:
                _advance(env, t)
                continue
            _advance(env, t)
            kpis = nhs_kpis(experiment, t, snapshot_window)
            wl = _wl(experiment, t)
            errs, mape = _mape(kpis, targets, match_weights, wl)
            row = {
                "candidate_period_days": t, "years": t / 365.25,
                "mape": mape, "matched": mape == mape and mape <= match_tolerance,
                "waiting_list_size_all_in_system": wl,
                **{f"mape_{k}": v for k, v in errs.items()},
                **{f"sim_{k}": kpis.get(_key(k), wl if _key(k).startswith("waiting_list") else None)
                   for k in targets},
                **kpis,
            }
            history.append(row)
            if on_checkpoint:
                on_checkpoint(t, row)
            if mape == mape and mape < best_mape:
                best_mape, best = mape, dict(row)
            if row["matched"]:
                matched, t_star = True, t
                break
        opt = next((h for h in history if h["candidate_period_days"] == t_star), best)
        return {
            "matched": matched,
            "optimal_matching_period_days": t_star,
            "matching_period_days": t_star,
            "match_targets": targets,
            "match_weights": dict(match_weights or {}),
            "match_tolerance": float(match_tolerance),
            "minimum_mape": float(opt.get("mape", best_mape)),
            "best_checkpoint": opt,
            "history": history,
            "rep": rep,
            "scenario": experiment.scenario_name,
        }

    # --- switch: As-Is to T*, then policy overrides ---
    if switch_at is not None:
        decay = float(run_length) - float(switch_at)
        if decay <= 0:
            raise ValueError("run_length must be > switch_at")
        env, system = _boot(experiment, float(run_length) + 1.0)
        _advance(env, switch_at)
        wl0 = _wl(experiment, switch_at)
        phases = SimulationPhases(float(switch_at), 0.0, decay)
        experiment.phases = phases
        experiment.warmup_days = phases.warmup_end
        experiment.switch_time = float(switch_at)
        experiment.collection_days = decay
        experiment.run_length = phases.end
        experiment.audit.set_phases(phases)
        experiment.configure_intervention(dict(switch_overrides or {}))
        experiment.phase = "baseline"
        experiment.activate_intervention(env.now)
        system.workforce.refresh_capacity_from_experiment()
        _advance(env, run_length)
        wl1 = _wl(experiment, run_length)
        kpis = nhs_kpis(experiment, run_length, decay)
        return {
            "rep": rep, "scenario": experiment.scenario_name,
            "switch_time": float(switch_at), "decay_period_days": decay,
            "run_length": float(run_length),
            "waiting_list_at_switch": wl0, "waiting_list_at_end": wl1,
            "backlog_decay_total": wl0 - wl1,
            "backlog_decay_per_month": (wl0 - wl1) / max(decay / 30.4375, 1e-9),
            "overrides": dict(switch_overrides or {}),
            **kpis,
        }

    # --- plain: run to horizon ---
    env, _ = _boot(experiment, float(run_length) + float(snapshot_window))
    _advance(env, run_length)
    kpis = nhs_kpis(experiment, run_length, snapshot_window)
    kpis.update({
        "rep": rep, "seed": rep, "scenario": experiment.scenario_name,
        "run_length": float(run_length),
        "matching_period_days": float(run_length),
        "waiting_list_size_all_in_system": _wl(experiment, run_length),
    })
    return kpis


# ---------------------------------------------------------------------------
# Run 1 / 2 / 3 — Experiment in, results out (no auto-save)
# ---------------------------------------------------------------------------

def run1(
    experiment: Experiment,
    *,
    match_targets: Mapping[str, float],
    max_period_days: float,
    match_weights: Optional[Mapping[str, float]] = None,
    match_tolerance: float = 0.05,
    step_days: float = 30.0,
    min_period_days: float = 90.0,
    snapshot_window: float = 365.0,
    seed: int = 0,
    on_checkpoint: Optional[CheckpointFn] = None,
) -> Dict[str, Any]:
    """
    Run 1 — find the Optimal Matching Period T* for outcome KPI targets.

    Advances the simulation in steps of *step_days* and evaluates the
    aggregate MAPE against *match_targets* at each step.  Stops when MAPE
    falls within *match_tolerance* or *max_period_days* is reached.

    Parameters
    ----------
    experiment : Experiment
        Scenario to calibrate.
    match_targets : Mapping[str, float]
        KPI targets to match (e.g. ``{'waiting_list_size': 450}``).
    max_period_days : float
        Upper bound on the search horizon.
    match_weights : Mapping[str, float], optional
        Per-KPI weights for the aggregate MAPE.
    match_tolerance : float, optional
        MAPE stopping threshold.  Default ``0.05`` (5%).
    step_days : float, optional
        Calibration step size.  Default ``30.0`` days.
    min_period_days : float, optional
        Earliest candidate horizon.  Default ``90.0`` days.
    snapshot_window : float, optional
        Rolling KPI window length.  Default ``365.0`` days.
    seed : int, optional
        RNG seed for the calibration run.  Default ``0``.
    on_checkpoint : callable, optional
        Function called as ``on_checkpoint(time, row)`` after each calibration
        checkpoint.  Useful for live annual progress reporting.

    Returns
    -------
    dict[str, Any]
        Calibration result including ``optimal_matching_period_days``,
        ``matched``, ``minimum_mape``, and ``history``.
    """
    return single_run(
        experiment, rep=seed, run_length=float(max_period_days),
        check_every=float(step_days), min_period=float(min_period_days),
        match_targets=dict(match_targets), match_weights=match_weights,
        match_tolerance=float(match_tolerance), snapshot_window=float(snapshot_window),
        on_checkpoint=on_checkpoint,
    )


def run2(
    experiment: Experiment,
    *,
    matching_period_days: float,
    n_reps: int = 20,
    snapshot_window: float = 365.0,
    confidence_level: float = 0.95,
    seeds: Optional[Sequence[int]] = None,
    baseline_kpis: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    Run 2 — stochastic baseline: N replications at T* with confidence intervals.

    Each replication is a fresh clone of *experiment* run to
    *matching_period_days*.  Student-t CIs are computed across replications
    for the requested *baseline_kpis*.

    Parameters
    ----------
    experiment : Experiment
        As-Is (provider) scenario.
    matching_period_days : float
        Horizon T* from Run 1.
    n_reps : int, optional
        Number of replications.  Default ``20``.
    snapshot_window : float, optional
        Rolling KPI window length.  Default ``365.0`` days.
    confidence_level : float, optional
        CI confidence level.  Default ``0.95``.
    seeds : sequence[int], optional
        Explicit seed list.  Defaults to ``range(n_reps)``.
    baseline_kpis : sequence[str], optional
        KPI columns to include in the CI summary.

    Returns
    -------
    dict[str, Any]
        Result including ``summary`` (CI table as list of dicts),
        ``replications`` (per-rep rows), and metadata.
    """
    seed_list = list(seeds) if seeds is not None else list(range(int(n_reps)))
    kpis = list(baseline_kpis or DEFAULT_KPIS)
    rows = [
        single_run(clone(experiment, seed=s), rep=s,
                   run_length=float(matching_period_days),
                   snapshot_window=float(snapshot_window))
        for s in seed_list
    ]
    summary = _ci_frame(pd.DataFrame(rows), kpis, confidence_level)
    return {
        "optimal_matching_period_days": float(matching_period_days),
        "matching_period_days": float(matching_period_days),
        "n_reps": len(seed_list), "confidence_level": float(confidence_level),
        "seeds": seed_list,
        "summary": summary.to_dict(orient="records"),
        "replications": rows,
        "scenario": experiment.scenario_name,
    }


def run3(
    experiment: Experiment,
    *,
    matching_period_days: float,
    decay_period_days: float,
    switch_overrides: Optional[Mapping[str, Any]] = None,
    seed: int = 0,
    include_control: bool = True,
    policy_id: str = "policy",
) -> Dict[str, Any]:
    """
    Run 3 — continuous policy branching: run to T*, apply overrides, then decay.

    At simulation time T* (``matching_period_days``), the experiment's
    parameters are updated with *switch_overrides* without resetting
    in-flight RTT clocks.  The simulation continues for *decay_period_days*
    under the new parameters.  Optionally runs an empty-override control arm
    in the same environment for direct comparison.

    Parameters
    ----------
    experiment : Experiment
        As-Is scenario to branch from.
    matching_period_days : float
        SwitchTime T*.
    decay_period_days : float
        Simulated days after T* to evaluate backlog decay.
    switch_overrides : Mapping[str, Any], optional
        Experiment attribute overrides applied at T*.
    seed : int, optional
        RNG seed.  Default ``0``.
    include_control : bool, optional
        When ``True`` (default) also run the empty-override control arm.
    policy_id : str, optional
        Label for the policy arm.  Default ``'policy'``.

    Returns
    -------
    dict[str, Any]
        Result containing ``policy_arm``, ``control_arm`` (when requested),
        and ``comparison`` metrics.
    """
    T, decay = float(matching_period_days), float(decay_period_days)
    overrides = dict(switch_overrides or {})

    def arm(name: str, ov: dict) -> Dict[str, Any]:
        raw = single_run(
            clone(experiment, f"{experiment.scenario_name}_{name}", seed),
            rep=seed, run_length=T + decay, switch_at=T, switch_overrides=ov,
        )
        meta = {
            "rep", "scenario", "switch_time", "decay_period_days", "run_length",
            "waiting_list_at_switch", "waiting_list_at_end",
            "backlog_decay_total", "backlog_decay_per_month", "overrides",
        }
        return {
            "arm": name, "seed": seed,
            "matching_period_days": T, "decay_period_days": decay,
            "switch_time": T,
            "waiting_list_at_switch": raw["waiting_list_at_switch"],
            "waiting_list_at_end": raw["waiting_list_at_end"],
            "backlog_decay_total": raw["backlog_decay_total"],
            "backlog_decay_per_month": raw["backlog_decay_per_month"],
            "overrides": dict(ov),
            **{f"kpi_{k}": v for k, v in raw.items() if k not in meta},
        }

    policy = arm(policy_id, overrides)
    control = comparison = None
    if include_control:
        control = arm("baseline_control", {})
        comparison = {
            "delta_wl_end": policy["waiting_list_at_end"] - control["waiting_list_at_end"],
            "delta_decay_total": policy["backlog_decay_total"] - control["backlog_decay_total"],
            "delta_decay_per_month": (
                policy["backlog_decay_per_month"] - control["backlog_decay_per_month"]
            ),
        }
    return {
        "policy_id": policy_id,
        "optimal_matching_period_days": T,
        "matching_period_days": T,
        "decay_period_days": decay,
        "seed": int(seed),
        "policy_arm": policy, "control_arm": control, "comparison": comparison,
        "scenario": experiment.scenario_name,
    }


# ---------------------------------------------------------------------------
# Optional: config wrappers (for CLI scripts / des.__init__ compatibility)
# ---------------------------------------------------------------------------

def _setup_from_config(config, name: str, seed: Optional[int] = None) -> Experiment:
    from des.runs.config import setup_experiment
    return setup_experiment(config, name, seed=seed)


def find_optimal_matching_period(config, *, seed: Optional[int] = None) -> Dict[str, Any]:
    """
    Derive a :class:`~des.experiment.Experiment` from *config* and run Run 1.

    Equivalent to ``execute_run1`` but without saving output to disk.

    Parameters
    ----------
    config : ProviderRunConfig
        Provider configuration supplying targets, weights, and horizons.
    seed : int, optional
        Override for the calibration seed.

    Returns
    -------
    dict[str, Any]
        Run 1 result dict (same as :func:`run1`).

    Raises
    ------
    ValueError
        If ``config.provider_targets`` is empty.
    """
    if not config.provider_targets:
        raise ValueError("provider_targets must be non-empty for Run 1")
    rep = int(config.calibration_seed if seed is None else seed)
    result = run1(
        _setup_from_config(config, f"{config.provider_id}_run1", rep),
        match_targets=dict(config.provider_targets),
        match_weights=dict(config.mape_weights) if config.mape_weights else None,
        match_tolerance=float(config.match_tolerance),
        max_period_days=float(config.max_period_days),
        step_days=float(config.step_days),
        min_period_days=float(config.min_period_days),
        snapshot_window=float(config.rolling_window_days),
        seed=rep,
    )
    result["provider_id"] = config.provider_id
    result["minimum_aggregate_mape"] = result["minimum_mape"]
    result["provider_targets"] = dict(config.provider_targets)
    return result


def execute_run1(config, *, seed: Optional[int] = None) -> Dict[str, Any]:
    """
    Run calibration (Run 1) and save the matching-period JSON and history CSV.

    Parameters
    ----------
    config : ProviderRunConfig
        Provider configuration.
    seed : int, optional
        Override for the calibration seed.

    Returns
    -------
    dict[str, Any]
        Run 1 result with ``output_path`` added.
    """
    result = find_optimal_matching_period(config, seed=seed)
    path = save_matching_period(config.matching_period_path(), result)
    pd.DataFrame(result["history"]).to_csv(
        Path(path).with_name(Path(path).stem + "_history.csv"), index=False
    )
    result["output_path"] = str(path)
    return result


def execute_run2(config, *, matching_period_days: Optional[float] = None) -> Dict[str, Any]:
    """
    Run stochastic baseline (Run 2) and save JSON and summary CSV.

    Loads T* from the Run 1 artefact when *matching_period_days* is not given.

    Parameters
    ----------
    config : ProviderRunConfig
        Provider configuration.
    matching_period_days : float, optional
        Override for T*.  When ``None`` loads from Run 1 output file.

    Returns
    -------
    dict[str, Any]
        Run 2 result with ``output_path`` and ``summary_csv`` added.
    """
    T = matching_period_days
    if T is None:
        T = float(load_matching_period(config.matching_period_path())["optimal_matching_period_days"])
    result = run2(
        _setup_from_config(config, f"{config.provider_id}_run2"),
        matching_period_days=float(T),
        n_reps=len(config.baseline_seed_list()),
        snapshot_window=float(config.rolling_window_days),
        confidence_level=float(config.confidence_level),
        seeds=config.baseline_seed_list(),
        baseline_kpis=config.baseline_kpis,
    )
    result["provider_id"] = config.provider_id
    path = save_baseline_results(config.baseline_path(), result)
    pd.DataFrame(result["summary"]).to_csv(
        config.baseline_path().with_name(config.baseline_path().stem + "_summary.csv"),
        index=False,
    )
    result["output_path"] = str(path)
    return result


def execute_run3(
    config,
    *,
    matching_period_days: Optional[float] = None,
    policy_id: Optional[str] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run policy branching (Run 3) and save the policy JSON artefact.

    Loads T* from the Run 1 artefact when *matching_period_days* is not given.

    Parameters
    ----------
    config : ProviderRunConfig
        Provider configuration.
    matching_period_days : float, optional
        Override for T*.  When ``None`` loads from Run 1 output file.
    policy_id : str, optional
        Policy package key from ``config.policy_packages``.
    seed : int, optional
        Override for the policy seed.

    Returns
    -------
    dict[str, Any]
        Run 3 result with ``output_path`` added.
    """
    T = matching_period_days
    if T is None:
        T = float(load_matching_period(config.matching_period_path())["optimal_matching_period_days"])
    pid = policy_id or config.policy_id
    rep = int(config.policy_seed if seed is None else seed)
    result = run3(
        _setup_from_config(config, f"{config.provider_id}_run3", rep),
        matching_period_days=float(T),
        decay_period_days=float(config.decay_period_days),
        switch_overrides=config.resolve_policy(pid),
        seed=rep,
        include_control=bool(config.include_control_arm),
        policy_id=pid,
    )
    result["provider_id"] = config.provider_id
    result["output_path"] = str(save_policy_results(config.policy_path(), result))
    return result

