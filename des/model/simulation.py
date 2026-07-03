"""Simulation run functions."""

import copy
import secrets

import pandas as pd
import simpy
from joblib import Parallel, delayed

from des.model.parameters import MAX_DRAIN_DAYS, N_REP, RUN_LENGTH, WARMUP_DAYS
from des.model.system import AutismPathwaySystem

def single_run(
    experiment,
    rep=0,
    warmup_days=WARMUP_DAYS,
    run_length=RUN_LENGTH,
    max_drain_days=MAX_DRAIN_DAYS,
):
    """
    Run one replication: warm-up, collection, then drain until empty.

    Parameters
    ----------
    experiment : Experiment
        Scenario configuration (reset at start of each call).
    rep : int, default 0
        Replication index added to the base random seed.
    warmup_days : float, default ``WARMUP_DAYS``
        Days ``[0, warmup_days)`` where referrals flow but ``collect_stats=False``.
        Set to ``0`` for empty-start (no warm-up).
    run_length : float, default ``RUN_LENGTH``
        Collection window length in days.
    max_drain_days : float, default ``MAX_DRAIN_DAYS``
        Maximum days after collection ends to clear all patients.

    Returns
    -------
    dict
        Flow counters, KPIs from :class:`Audit`, and run metadata
        (``WARMUP_DAYS``, ``COHORT_RTT_VALID``, etc.).

    Notes
    -----
    KPI cohort = referrals in ``[warmup_days, warmup_days + run_length)``.
    Warm-up patients count toward ``ARRIVED_ALL`` / ``EXIT_ALL`` only.
    Referrals stop at ``collection_end``; drain runs immediately after.
    """
    experiment.auditor.reset()
    experiment.init_results_variables()

    if experiment.use_fixed_seed:
        experiment.set_random_no_set(rep)

    warmup_days = float(warmup_days)
    collection_start = warmup_days
    arrival_stop = warmup_days + float(run_length)
    experiment.auditor.collection_start = collection_start
    experiment.auditor.collection_end = arrival_stop

    env = simpy.Environment()
    system = AutismPathwaySystem(
        env,
        experiment,
        collection_start=collection_start,
        arrival_stop=arrival_stop,
        event_logger=None,
    )
    env.process(system.run())
    env.run(until=arrival_stop)

    # Drain until all patients (warm-up + cohort) have exited.
    drain_limit = arrival_stop + float(max_drain_days)
    while (
        experiment.results["ARRIVED_ALL"] - experiment.results["EXIT_ALL"] > 0
        and env.now < drain_limit
    ):
        env.run(until=min(env.now + 30.0, drain_limit))

    for stage_name, resource in system.resources.items():
        resource.flush_end_of_horizon()
        resource.final_validate(strict=True)
        experiment.auditor.capture_resource_stats(stage_name, resource)

    trapped_cohort = experiment.results["ARRIVED_TOTAL"] - experiment.results["EXIT_TOTAL"]
    trapped_all = experiment.results["ARRIVED_ALL"] - experiment.results["EXIT_ALL"]
    experiment.results["IN_SYSTEM_END"] = trapped_cohort
    experiment.results["IN_SYSTEM_ALL"] = trapped_all
    experiment.results["COHORT_DRAIN_COMPLETE"] = trapped_cohort == 0
    experiment.results["SYSTEM_DRAIN_COMPLETE"] = trapped_all == 0
    experiment.results["SYSTEM_COMPLETED_TOTAL"] = experiment.results["EXIT_TOTAL"]
    experiment.results["WARMUP_DAYS"] = warmup_days
    experiment.results["COLLECTION_START_DAYS"] = collection_start
    experiment.results["COLLECTION_WINDOW_DAYS"] = run_length
    experiment.results["COLLECTION_END_DAYS"] = arrival_stop
    experiment.results["MAX_DRAIN_DAYS"] = max_drain_days
    experiment.results["DRAIN_LIMIT_DAYS"] = drain_limit
    experiment.results["SIM_END_DAYS"] = env.now
    experiment.results["DRAIN_DAYS"] = env.now - arrival_stop

    results = experiment.results.copy()
    results["SEED_USED"] = experiment.random_number_set
    results.update(experiment.auditor.summarize(results, run_length))
    results.update(
        {
            f"SLOTS_{k.upper()}": v["derived_slots_per_day"]
            for k, v in experiment.derived_capacity.items()
        }
    )
    return results


def multiple_runs(
    experiment,
    n_reps=N_REP,
    warmup_days=WARMUP_DAYS,
    run_length=RUN_LENGTH,
    n_jobs=1,
    use_fixed_seed=True,
):
    """
    Run independent replications in parallel.

    Parameters
    ----------
    experiment : Experiment
        Base scenario (deep-copied per replication).
    n_reps : int, default ``N_REP``
        Number of replications.
    warmup_days : float, default ``WARMUP_DAYS``
        Passed to :func:`single_run`.
    run_length : float, default ``RUN_LENGTH``
        Collection window length.
    n_jobs : int, default 1
        Parallel workers (-1 = all cores).
    use_fixed_seed : bool, default True
        If True, each rep uses ``base_seed + rep``.

    Returns
    -------
    pandas.DataFrame
        One row per replication with all KPI columns.
    """

    def _run_worker(rep_idx):
        local_exp = copy.deepcopy(experiment)
        local_exp.use_fixed_seed = use_fixed_seed
        if use_fixed_seed:
            local_exp.set_random_no_set(rep_idx)
        else:
            local_exp.random_number_set = secrets.randbits(31)
            local_exp.init_sampling()
        return single_run(
            experiment=local_exp,
            rep=rep_idx,
            warmup_days=warmup_days,
            run_length=run_length,
        )

    all_results = Parallel(n_jobs=n_jobs)(
        delayed(_run_worker)(rep_idx=rep) for rep in range(n_reps)
    )
    for rep, result in enumerate(all_results):
        result["Replication"] = rep
        result["Seeded_Execution"] = use_fixed_seed
    return pd.DataFrame(all_results)
