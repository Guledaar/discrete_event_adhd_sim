"""Waiting-list stock helper used by the three-run framework."""

from __future__ import annotations

import numpy as np

from des.audit import Audit


def count_waiting_list_all_in_system(audit: Audit, now: float) -> int:
    """
    Count incomplete pathways at simulation time *now* (all patients).

    Uses the same NHS RTT incomplete rules as :func:`des.kpi.compute_kpis`
    (:func:`des.kpi._enrich_rtt`), restricted to patients who have already
    arrived by *now*.

    Parameters
    ----------
    audit : Audit
        Audit holding patient records (typically after simulation ends).
    now : float
        Simulation time in days.

    Returns
    -------
    int
        Number of patients still in an incomplete pathway.
    """
    from des.kpi import _col, _enrich_rtt, _fcol

    patients = audit.finalize()
    if patients.empty:
        return 0

    now = float(now)
    arrival = _fcol(patients, "arrival_time")
    arrived = patients.loc[(~np.isnan(arrival)) & (arrival <= now)].copy()
    if arrived.empty:
        return 0

    enriched = _enrich_rtt(arrived, now)
    return int((_col(enriched, "rtt_pathway_status") == "incomplete").sum())
