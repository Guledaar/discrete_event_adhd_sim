"""
Warm-up / collection simulation runners.

Public API: :func:`single_run` and :func:`multiple_replications`.
Horizons are resolved by :func:`resolve_periods`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import pandas as pd
import simpy
from joblib import Parallel, delayed

from des.audit import Audit
from des.config import DEFAULT_RESULTS_COLLECTION_PERIOD, N_REP, WARM_UP_PERIOD
from des.kpi import compute_kpis
from des.reporting import export_run_result
from des.system import AutismPathwaySystem


def resolve_periods(
    warmup_days: Optional[float] = None,
    collection_days: Optional[float] = None,
    run_length: Optional[float] = None,
) -> Tuple[float, float, float]:
    """
    Resolve simulation horizons as ``(warmup, collection, total)``.

    Pass either ``collection_days`` (total = warmup + collection) or
    ``run_length`` (collection = run_length − warmup). When both are given,
    they must be consistent.

    Parameters
    ----------
    warmup_days : float, optional
        Warm-up length in days. Default is ``WARM_UP_PERIOD``.
    collection_days : float, optional
        KPI collection length in days.
    run_length : float, optional
        Total horizon; collection is derived as run_length − warmup.

    Returns
    -------
    tuple[float, float, float]
        ``(warmup_days, collection_days, run_length)``.
    """
    warmup = float(WARM_UP_PERIOD if warmup_days is None else warmup_days)

    if collection_days is not None and run_length is not None:
        collection, total = float(collection_days), float(run_length)
        if abs(total - (warmup + collection)) > 1e-9:
            raise ValueError(
                f"run_length ({total}) must equal warmup + collection ({warmup + collection})"
            )
        return warmup, collection, total

    if run_length is not None:
        total = float(run_length)
        if total < warmup:
            raise ValueError("run_length must be >= warmup_days")
        return warmup, total - warmup, total

    collection = float(
        DEFAULT_RESULTS_COLLECTION_PERIOD if collection_days is None else collection_days
    )
    return warmup, collection, warmup + collection


def apply_run_horizons(experiment: Any, warmup_days: float, collection_days: float) -> None:
    """
    Set experiment horizons and reset the audit collection window.

    Parameters
    ----------
    experiment : Experiment
        Scenario to configure; mutated in place.
    warmup_days : float
        Warm-up period length in days.
    collection_days : float
        KPI collection period length in days.
    """
    experiment.warmup_days = float(warmup_days)
    experiment.collection_days = float(collection_days)
    experiment.run_length = float(warmup_days) + float(collection_days)
    experiment.phases = None
    experiment.switch_time = None
    experiment.phase = "baseline"
    experiment.audit.reset(warmup_days=warmup_days, collection_days=collection_days)


def single_run(
    experiment: Any,
    rep: int = 0,
    warmup_days: Optional[float] = None,
    collection_days: Optional[float] = None,
    run_length: Optional[float] = None,
    export_results: bool = True,
    output_root: Union[str, Path] = "run_output/simulations",
) -> Dict[str, Any]:
    """
    Run one replication and return a flat KPI summary dict.

    Parameters
    ----------
    experiment : Experiment
        Scenario configuration and audit owner.
    rep : int, optional
        Replication index for seeding. Default is 0.
    warmup_days : float, optional
        Warm-up length; passed to :func:`resolve_periods`.
    collection_days : float, optional
        Collection length; passed to :func:`resolve_periods`.
    run_length : float, optional
        Total horizon; passed to :func:`resolve_periods`.
    export_results : bool, optional
        Automatically write the four standard CSV reports.  Defaults to
        ``True``.  Set to ``False`` for internal calculations that must not
        create artefacts.
    output_root : str or pathlib.Path, optional
        Parent directory for collision-safe automatic exports.  Each
        simulation receives a new unique child directory, so existing files
        are never overwritten.

    Returns
    -------
    dict[str, Any]
        KPI summary plus ``rep``, ``scenario``, and horizon metadata.
    """
    warmup, collection, total = resolve_periods(warmup_days, collection_days, run_length)
    apply_run_horizons(experiment, warmup, collection)
    if experiment.use_fixed_seed:
        experiment.set_random_no_set(rep)

    env = simpy.Environment()
    system = AutismPathwaySystem(env, experiment)
    env.process(system.run())
    env.run(until=experiment.audit.window.end)

    result = compute_kpis(
        experiment.audit.finalize(),
        experiment.audit.window,
        experiment,
        system,
        experiment.audit.capacity_days,
    )
    summary = {
        **result.summary,
        "rep": rep,
        "scenario": experiment.scenario_name,
        "warmup_days": warmup,
        "collection_days": collection,
        "run_length": total,
    }
    experiment.last_result = result
    if export_results:
        paths = export_run_result(
            result,
            output_root=output_root,
            scenario=experiment.scenario_name,
            rep=rep,
            metadata={
                "warmup_days": warmup,
                "collection_days": collection,
                "run_length": total,
            },
        )
        experiment.last_export_paths = paths
    else:
        experiment.last_export_paths = {}
    return summary


def multiple_replications(
    experiment: Any,
    n_reps: int = N_REP,
    warmup_days: Optional[float] = None,
    collection_days: Optional[float] = None,
    run_length: Optional[float] = None,
    n_jobs: int = -1,
    export_results: bool = True,
    output_root: Union[str, Path] = "run_output/simulations",
) -> pd.DataFrame:
    """
    Run independent replications in parallel and return one row per rep.

    Parameters
    ----------
    experiment : Experiment
        Template scenario; each worker gets a fresh clone.
    n_reps : int, optional
        Number of replications. Default is ``N_REP``.
    warmup_days : float, optional
        Warm-up length; passed to :func:`single_run`.
    collection_days : float, optional
        Collection length; passed to :func:`single_run`.
    run_length : float, optional
        Total horizon; passed to :func:`single_run`.
    n_jobs : int, optional
        Joblib worker count. Default is -1 (all cores).
    export_results : bool, optional
        Whether each physical replication writes the four standard reports.
    output_root : str or pathlib.Path, optional
        Parent directory for unique per-replication export directories.

    Returns
    -------
    pandas.DataFrame
        One row per replication with KPI columns.
    """

    def _worker(i: int) -> Tuple[Dict[str, Any], Dict[str, str]]:
        exp = experiment.__class__(audit=Audit(), **experiment.to_kwargs())
        summary = single_run(
            exp,
            rep=i,
            warmup_days=warmup_days,
            collection_days=collection_days,
            run_length=run_length,
            export_results=export_results,
            output_root=output_root,
        )
        return summary, dict(exp.last_export_paths)

    outputs = Parallel(n_jobs=n_jobs)(
        delayed(_worker)(i) for i in range(int(n_reps))
    )
    rows, export_paths = zip(*outputs) if outputs else ([], [])
    frame = pd.DataFrame(rows)
    frame.attrs["export_paths"] = list(export_paths)
    return frame
