"""Three-run NHS DES API — prefer Experiment: ``run1`` / ``run2`` / ``run3``."""

from des.runs.config import (
    FIXED_INPUT_KPIS,
    MATCHABLE_KPI_MAP,
    ProviderRunConfig,
    load_provider_run_config,
    setup_experiment,
)
from des.runs.run import (
    execute_run1,
    execute_run2,
    execute_run3,
    find_optimal_matching_period,
    load_matching_period,
    nhs_kpis,
    run1,
    run2,
    run3,
    save_baseline_results,
    save_matching_period,
    save_policy_results,
    single_run,
)

MATCHABLE_KPIS = sorted(set(MATCHABLE_KPI_MAP) | set(MATCHABLE_KPI_MAP.values()))

__all__ = [
    "ProviderRunConfig",
    "load_provider_run_config",
    "setup_experiment",
    "single_run",
    "run1",
    "run2",
    "run3",
    "nhs_kpis",
    "execute_run1",
    "execute_run2",
    "execute_run3",
    "load_matching_period",
    "save_matching_period",
    "save_baseline_results",
    "save_policy_results",
    "MATCHABLE_KPI_MAP",
    "MATCHABLE_KPIS",
    "FIXED_INPUT_KPIS",
    "find_optimal_matching_period",
]
