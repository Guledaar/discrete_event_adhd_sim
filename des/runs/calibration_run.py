"""
Shim for Run 1 (matching / calibration to find T*).

Prefer::

    from des.runs import run1, execute_run1
"""
from des.runs.config import MATCHABLE_KPI_MAP
from des.runs.run import execute_run1, find_optimal_matching_period, run1

MATCHABLE_KPIS = sorted(set(MATCHABLE_KPI_MAP) | set(MATCHABLE_KPI_MAP.values()))

__all__ = ["run1", "execute_run1", "find_optimal_matching_period", "MATCHABLE_KPIS"]
