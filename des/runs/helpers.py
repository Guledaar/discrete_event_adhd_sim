"""
Shim helpers for legacy imports (matching I/O and MAPE).

Prefer::

    from des.runs import save_matching_period, setup_experiment
"""
from des.runs.config import ProviderRunConfig, setup_experiment
from des.runs.run import (
    _mape as mape_against_targets,
    load_matching_period,
    save_baseline_results,
    save_json,
    save_matching_period,
    save_policy_results,
)


def mape_components(summary, config: ProviderRunConfig, *, collection_days=None):
    """
    Compute per-KPI MAPE errors against the provider targets in *config*.

    Parameters
    ----------
    summary : dict[str, Any]
        Simulated KPI summary (e.g. from :func:`~des.runs.run.nhs_kpis`).
    config : ProviderRunConfig
        Provider configuration supplying ``provider_targets`` and
        ``mape_weights``.
    collection_days : float, optional
        Unused; kept for backward compatibility.

    Returns
    -------
    tuple[dict[str, float], float]
        Per-KPI error dict and aggregate MAPE (from :func:`~des.runs.run._mape`).
    """
    return mape_against_targets(
        summary,
        config.provider_targets,
        config.mape_weights or None,
    )


__all__ = [
    "setup_experiment",
    "load_matching_period",
    "save_matching_period",
    "save_baseline_results",
    "save_policy_results",
    "save_json",
    "mape_against_targets",
    "mape_components",
]
