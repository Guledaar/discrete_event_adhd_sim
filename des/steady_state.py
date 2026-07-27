"""Backlog (PTL) stock helper for the three-run framework."""

from __future__ import annotations

import pandas as pd

from des.audit import Audit
from des.run_report import enrich_rtt


def count_backlog_in_system(audit: Audit, now: float) -> int:
    """
    Count incomplete RTT pathways in the system at simulation time *now*.

    Parameters
    ----------
    audit : Audit
        Live or finalised audit object; :meth:`~des.audit.Audit.finalize` is
        called internally.
    now : float
        Simulation time in days at which to snapshot the backlog / PTL.

    Returns
    -------
    int
        Number of patients with ``rtt_status == "incomplete"`` who have arrived
        on or before *now*.
    """
    patients = audit.finalize()
    if patients.empty:
        return 0

    now = float(now)
    arrival = pd.to_numeric(patients["arrival_time"], errors="coerce")
    arrived = patients.loc[(arrival.notna()) & (arrival <= now)].copy()
    if arrived.empty:
        return 0

    enriched = enrich_rtt(arrived, now)
    return int((enriched["rtt_status"] == "incomplete").sum())
