"""Confidence-interval helpers for multi-replication KPI summaries."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

# Two-sided Student-t critical values (df → t*). df ≥ 30 uses Normal z.
_T_95: Dict[int, float] = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    12: 2.179, 15: 2.131, 20: 2.086, 25: 2.060, 30: 2.042,
}
_Z = {0.90: 1.645, 0.95: 1.960, 0.99: 2.576}


def _t_critical(df: int, confidence_level: float) -> float:
    """
    Return the two-sided Student-t critical value for *df* degrees of freedom.

    Uses a hard-coded lookup table for common values up to ``df=30``; falls
    back to the standard-normal z-value for ``df >= 30`` or non-95% levels.

    Parameters
    ----------
    df : int
        Degrees of freedom (``n - 1`` for a sample of size *n*).
    confidence_level : float
        Target confidence level (e.g. ``0.95`` for a 95% CI).

    Returns
    -------
    float
        Critical value ``t*`` such that ``P(-t* < T < t*) = confidence_level``.
    """
    if df <= 0 or df >= 30 or round(confidence_level, 2) != 0.95:
        return _Z.get(round(confidence_level, 2), 1.960)
    if df in _T_95:
        return _T_95[df]
    keys = sorted(_T_95)
    lo = max(k for k in keys if k <= df)
    hi = min(k for k in keys if k >= df)
    w = (df - lo) / (hi - lo) if lo != hi else 0.0
    return _T_95[lo] * (1 - w) + _T_95[hi] * w


@dataclass
class IntervalSummary:
    """
    Summary statistics for one KPI across multiple replications.

    Attributes
    ----------
    kpi : str
        Name of the KPI.
    n : int
        Number of valid (non-NaN) observations.
    mean : float
        Sample mean.
    std : float
        Sample standard deviation (``ddof=1``); ``NaN`` when ``n <= 1``.
    ci_low : float
        Lower bound of the confidence interval.
    ci_high : float
        Upper bound of the confidence interval.
    confidence_level : float
        Requested confidence level (e.g. ``0.95``).
    """
    kpi: str
    n: int
    mean: float
    std: float
    ci_low: float
    ci_high: float
    confidence_level: float


class ConfidenceIntervalCalculator:
    """
    Compute Student-t confidence intervals across independent replications.

    Parameters
    ----------
    confidence_level : float, optional
        Confidence level for all intervals.  Must be in ``(0, 1)``.
        Default ``0.95``.

    Raises
    ------
    ValueError
        If *confidence_level* is not in the open interval ``(0, 1)``.
    """

    def __init__(self, confidence_level: float = 0.95) -> None:
        if not 0.0 < confidence_level < 1.0:
            raise ValueError("confidence_level must be in (0, 1)")
        self.confidence_level = float(confidence_level)

    def summarise_series(self, values: Sequence[float], *, kpi: str = "value") -> IntervalSummary:
        """
        Compute a confidence interval for a sequence of replication values.

        ``NaN`` and ``None`` values are excluded before computing statistics.

        Parameters
        ----------
        values : sequence[float]
            Per-replication KPI observations.
        kpi : str, optional
            Label for the KPI.  Default ``'value'``.

        Returns
        -------
        IntervalSummary
            Summary containing ``n``, ``mean``, ``std``, ``ci_low``,
            ``ci_high``, and ``confidence_level``.
        """
        arr = np.asarray([v for v in values if v is not None and not pd.isna(v)], dtype=float)
        n = int(arr.size)
        if n == 0:
            return IntervalSummary(
                kpi,
                0,
                float("nan"),
                float("nan"),
                float("nan"),
                float("nan"),
                self.confidence_level,
            )
        mean = float(arr.mean())
        if n == 1:
            return IntervalSummary(
                kpi, 1, mean, 0.0, mean, mean, self.confidence_level
            )
        std = float(arr.std(ddof=1))
        half = _t_critical(n - 1, self.confidence_level) * std / sqrt(n)
        return IntervalSummary(
            kpi, n, mean, std, mean - half, mean + half, self.confidence_level
        )

    def summarise_frame(
        self,
        df: pd.DataFrame,
        kpis: Optional[Iterable[str]] = None,
    ) -> pd.DataFrame:
        """
        Compute confidence intervals for multiple KPI columns in a DataFrame.

        Parameters
        ----------
        df : pandas.DataFrame
            One row per replication; numeric columns are summarised.
        kpis : iterable[str], optional
            Subset of column names to summarise.  When ``None`` all numeric
            columns are included.

        Returns
        -------
        pandas.DataFrame
            One row per KPI with columns: ``kpi``, ``n``, ``mean``, ``std``,
            ``ci_low``, ``ci_high``, ``confidence_level``.
        """
        if df is None or df.empty:
            return pd.DataFrame(
                columns=["kpi", "n", "mean", "std", "ci_low", "ci_high", "confidence_level"]
            )
        cols = list(kpis) if kpis is not None else [
            c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])
        ]
        rows: List[dict] = []
        for kpi in cols:
            if kpi in df.columns:
                rows.append(self.summarise_series(df[kpi].tolist(), kpi=kpi).__dict__)
        return pd.DataFrame(rows)
