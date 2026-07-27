"""Patient state collection during simulation — no KPI or event logging."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from des.collection_window import CollectionWindow, SimulationPhases
from des.config import COLLECTION_DAYS, WARMUP_DAYS

RTT_18_WEEKS_DAYS = 18 * 7


@dataclass
class PatientRecord:
    """
    Patient pathway milestones recorded during simulation.

    Attributes
    ----------
    patient_id : int
        Unique patient identifier.
    arrival_time : float, optional
        Simulation time (days) at which the referral arrived.
    triage_outcome : str, optional
        Result of triage: ``'accepted'`` or ``'rejected'``.
    admin_removal : bool, optional
        ``True`` if the patient was removed administratively before assessment.
    assessment_start : float, optional
        Simulation time of the first assessment appointment.
    assessment_completion : float, optional
        Simulation time the final assessment appointment ended.
    diagnosis : bool, optional
        ``True`` if the patient received a positive diagnosis.
    support_type : str, optional
        Post-diagnosis support pathway: ``'virtual'`` or ``'clinical'``.
    exit_time : float, optional
        Simulation time the patient left the pathway.
    exit_route : str, optional
        Reason for exit (e.g. ``'referral_rejected'``, ``'workshop_complete'``).
    appointments_required : int, optional
        Total assessment appointments sampled from the distribution.
    appointments_completed : int
        Number of assessment appointments finished so far.
    clinician_hours_consumed : float
        Total clinician hours used across all activities.
    assessment_hours_consumed : float
        Clinician hours consumed by assessment appointments only.
    workshop_hours_consumed : float
        Clinician hours consumed by workshop sessions only.
    workshop_join_time : float, optional
        Simulation time the patient joined the workshop waiting list.
    workshop_start_time : float, optional
        Simulation time the patient's workshop group held its first session.
    workshop_completion : float, optional
        Simulation time the patient's final workshop session ended.
    workshop_group_id : int, optional
        Identifier of the workshop group the patient belongs to.
    """

    patient_id: int
    arrival_time: Optional[float] = None
    triage_outcome: Optional[str] = None
    admin_removal: Optional[bool] = None
    assessment_start: Optional[float] = None
    assessment_completion: Optional[float] = None
    diagnosis: Optional[bool] = None
    support_type: Optional[str] = None
    exit_time: Optional[float] = None
    exit_route: Optional[str] = None
    appointments_required: Optional[int] = None
    appointments_completed: int = 0
    clinician_hours_consumed: float = 0.0
    assessment_hours_consumed: float = 0.0
    workshop_hours_consumed: float = 0.0
    workshop_join_time: Optional[float] = None
    workshop_start_time: Optional[float] = None
    workshop_completion: Optional[float] = None
    workshop_group_id: Optional[int] = None


class Audit:
    """
    Accumulate patient pathway state during simulation.

    KPI computation is deferred to :meth:`finalize`, which converts the
    internal record store into a single :class:`pandas.DataFrame`.  The
    ``Audit`` object is owned by an :class:`~des.experiment.Experiment` and
    shared with all SimPy processes via ``experiment.audit``.

    Attributes
    ----------
    window : CollectionWindow
        Active KPI collection window (start / end times in simulation days).
    phases : SimulationPhases, optional
        Three-phase timeline for policy-branching runs (Run 3); ``None`` for
        single-window runs.
    patients : dict[int, PatientRecord]
        Live patient records keyed by patient ID.
    capacity_days : list[dict]
        Per-weekday clinician-hour balance rows recorded during collection.
    monitoring : bool
        When ``True``, capacity records are written regardless of the
        collection window (used during the live calibration phase in Run 1).
    """

    def __init__(self) -> None:
        """
        Initialise an empty audit with default collection windows from config.

        Sets ``window`` from :data:`~des.config.WARMUP_DAYS` and
        :data:`~des.config.COLLECTION_DAYS`, clears patient and capacity stores,
        and disables live monitoring until explicitly enabled.
        """
        self.window = CollectionWindow(WARMUP_DAYS, COLLECTION_DAYS)
        self.phases: Optional[SimulationPhases] = None
        self.patients: Dict[int, PatientRecord] = {}
        self.capacity_days: List[Dict[str, Any]] = []
        self.monitoring: bool = False

    def set_phases(self, phases: SimulationPhases) -> None:
        """
        Switch to tri-phase mode using a :class:`SimulationPhases` timeline.

        Parameters
        ----------
        phases : SimulationPhases
            Tri-phase timeline describing warm-up, baseline, and intervention
            periods.  The baseline :class:`CollectionWindow` is used as the
            active window.
        """
        self.phases = phases
        self.window = phases.baseline_window()

    def reset(
        self,
        warmup_days: Optional[float] = None,
        collection_days: Optional[float] = None,
        phases: Optional[SimulationPhases] = None,
    ) -> None:
        """
        Clear all stored state and re-configure the collection window.

        Parameters
        ----------
        warmup_days : float, optional
            Length of the warm-up period in simulation days.  Defaults to
            the module-level :data:`~des.config.WARMUP_DAYS` constant.
        collection_days : float, optional
            Length of the KPI collection window in simulation days.  Defaults
            to :data:`~des.config.COLLECTION_DAYS`.
        phases : SimulationPhases, optional
            When provided the audit is configured for tri-phase (policy
            branching) mode, overriding ``warmup_days`` and ``collection_days``.
        """
        if phases is not None:
            self.phases = phases
            self.window = phases.baseline_window()
        else:
            warmup = WARMUP_DAYS if warmup_days is None else warmup_days
            collection = COLLECTION_DAYS if collection_days is None else collection_days
            self.window = CollectionWindow(warmup, collection)
            self.phases = None
        self.patients = {}
        self.capacity_days = []
        self.monitoring = False

    def _in_collection_window(self, day: float) -> bool:
        """
        Return ``True`` when *day* falls inside the active collection window.

        Parameters
        ----------
        day : float
            Simulation time to test (in days).

        Returns
        -------
        bool
            ``True`` if *day* is within the baseline or (when applicable)
            intervention collection window.
        """
        if self.phases is not None:
            return self.phases.contains_collection(day)
        return self.window.contains(day)

    def record_capacity_day(
        self,
        day: float,
        *,
        hours_released: float,
        hours_used: float,
        hours_unused: float,
        assessment_hours_used: float,
        workshop_hours_used: float,
    ) -> None:
        """
        Record the weekday clinician-hour balance for one simulation day.

        The record is only appended when *day* is inside the active collection
        window or when :attr:`monitoring` is ``True``.

        Parameters
        ----------
        day : float
            Simulation time of the weekday being recorded (in days).
        hours_released : float
            Total clinician hours released at the start of this weekday.
        hours_used : float
            Total clinician hours consumed by all activities.
        hours_unused : float
            Clinician hours left unused at end-of-day (not carried over).
        assessment_hours_used : float
            Subset of *hours_used* attributable to assessment appointments.
        workshop_hours_used : float
            Subset of *hours_used* attributable to workshop sessions.
        """
        if not self.monitoring and not self._in_collection_window(day):
            return
        record: Dict[str, Any] = {
            "day": float(day),
            "hours_released": float(hours_released),
            "hours_used": float(hours_used),
            "hours_unused": float(hours_unused),
            "assessment_hours_used": float(assessment_hours_used),
            "workshop_hours_used": float(workshop_hours_used),
        }
        if self.phases is not None:
            record["phase"] = self.phases.phase_at(day)
        self.capacity_days.append(record)

    def update_patient(self, patient_id: int, **kwargs: Any) -> None:
        """
        Create or update a patient record by patient ID.

        On the first call for a given *patient_id*, a new
        :class:`PatientRecord` is created using ``arrival_time`` (which is
        required for the first call).  Subsequent calls update named fields.

        Special keyword arguments
        -------------------------
        arrival_time : float
            Required on the first call; silently ignored on later calls.
        clinician_hours_add : float
            Increment ``clinician_hours_consumed`` by this amount.
        assessment_hours_add : float
            Increment both ``assessment_hours_consumed`` and
            ``clinician_hours_consumed`` by this amount.
        workshop_hours_add : float
            Increment both ``workshop_hours_consumed`` and
            ``clinician_hours_consumed`` by this amount.

        Parameters
        ----------
        patient_id : int
            Patient to create or update.
        **kwargs : Any
            Field name / value pairs to set on the :class:`PatientRecord`.

        Raises
        ------
        ValueError
            If *arrival_time* is not provided on the first call.
        """
        if patient_id not in self.patients:
            arrival_time = kwargs.pop("arrival_time", None)
            if arrival_time is None:
                raise ValueError("First update for a patient must include arrival_time")
            self.patients[patient_id] = PatientRecord(
                patient_id=patient_id, arrival_time=arrival_time
            )
        else:
            kwargs.pop("arrival_time", None)

        hours_add = kwargs.pop("clinician_hours_add", 0.0)
        assessment_add = kwargs.pop("assessment_hours_add", 0.0)
        workshop_add = kwargs.pop("workshop_hours_add", 0.0)
        patient = self.patients[patient_id]
        for key, value in kwargs.items():
            setattr(patient, key, value)
        if hours_add:
            patient.clinician_hours_consumed += hours_add
        if assessment_add:
            patient.assessment_hours_consumed += assessment_add
            patient.clinician_hours_consumed += assessment_add
        if workshop_add:
            patient.workshop_hours_consumed += workshop_add
            patient.clinician_hours_consumed += workshop_add

    def finalize(self) -> pd.DataFrame:
        """
        Convert stored patient records into a single :class:`~pandas.DataFrame`.

        Rows are sorted by ``patient_id`` and the index is reset.  Returns an
        empty :class:`~pandas.DataFrame` when no patients have been recorded.

        Returns
        -------
        pandas.DataFrame
            One row per patient with columns matching :class:`PatientRecord`
            field names.
        """
        if not self.patients:
            return pd.DataFrame()
        return pd.DataFrame([asdict(p) for p in self.patients.values()]).sort_values(
            "patient_id"
        ).reset_index(drop=True)
