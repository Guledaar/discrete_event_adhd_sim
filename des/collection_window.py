"""
Warm-up, collection, and intervention time windows.

:class:`CollectionWindow` is the KPI window for plain runs.
:class:`SimulationPhases` adds a policy switch for Run 3.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CollectionWindow:
    """
    KPI collection window ``[warmup_days, warmup_days + collection_days)``.

    Attributes
    ----------
    warmup_days : float
        Simulation time at which KPI collection starts.
    collection_days : float
        Length of the collection interval in days.
    """

    warmup_days: float
    collection_days: float

    @property
    def start(self) -> float:
        """Start of the collection window (same as ``warmup_days``)."""
        return self.warmup_days

    @property
    def end(self) -> float:
        """End of the collection window (exclusive upper bound)."""
        return self.warmup_days + self.collection_days

    @property
    def run_length(self) -> float:
        """Total horizon through the end of collection."""
        return self.end

    def contains(self, time: float) -> bool:
        """
        Return whether *time* falls inside the collection window.

        Parameters
        ----------
        time : float
            Simulation time in days.

        Returns
        -------
        bool
            ``True`` when ``start <= time < end``.
        """
        return self.start <= time < self.end


@dataclass
class SimulationPhases:
    """
    Tri-phase timeline for Run 3 policy branching.

    Timeline: warm-up → baseline collection → intervention collection.

    Attributes
    ----------
    warmup_end : float
        Simulation time when warm-up ends and baseline collection starts.
    baseline_collection_days : float
        Baseline collection length after warm-up.
    intervention_collection_days : float, optional
        Post-switch intervention collection length. Default is 0.
    """

    warmup_end: float
    baseline_collection_days: float
    intervention_collection_days: float = 0.0

    @property
    def switch_time(self) -> float:
        """Simulation time when the policy switch occurs."""
        return self.warmup_end + self.baseline_collection_days

    @property
    def end(self) -> float:
        """End of the full tri-phase horizon."""
        return self.switch_time + self.intervention_collection_days

    @property
    def run_length(self) -> float:
        """Total tri-phase horizon length."""
        return self.end

    @property
    def is_tri_phase(self) -> bool:
        """``True`` when an intervention collection period is configured."""
        return self.intervention_collection_days > 0

    def baseline_window(self) -> CollectionWindow:
        """
        Return the baseline KPI collection window.

        Returns
        -------
        CollectionWindow
            Window covering baseline collection after warm-up.
        """
        return CollectionWindow(self.warmup_end, self.baseline_collection_days)

    def intervention_window(self) -> CollectionWindow:
        """
        Return the intervention KPI collection window.

        Returns
        -------
        CollectionWindow
            Window covering post-switch intervention collection.
        """
        return CollectionWindow(self.switch_time, self.intervention_collection_days)

    def contains_collection(self, time: float) -> bool:
        """
        Return whether *time* is in baseline or intervention collection.

        Parameters
        ----------
        time : float
            Simulation time in days.

        Returns
        -------
        bool
            ``True`` if *time* is in either collection window.
        """
        if self.baseline_window().contains(time):
            return True
        return self.is_tri_phase and self.intervention_window().contains(time)

    def phase_at(self, time: float) -> str:
        """
        Return the phase label at simulation time *time*.

        Parameters
        ----------
        time : float
            Simulation time in days.

        Returns
        -------
        str
            One of ``'warmup'``, ``'baseline'``, ``'intervention'``, or ``'ended'``.
        """
        if time < self.warmup_end:
            return "warmup"
        if time < self.switch_time:
            return "baseline"
        if time < self.end:
            return "intervention"
        return "ended"
