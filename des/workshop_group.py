"""Clinical workshop programme for a formed patient group."""

from __future__ import annotations

from typing import TYPE_CHECKING, Generator, List

import simpy

from des.trace import (
    trace_pathway_complete,
    trace_workshop_session_completed,
    trace_workshop_session_started,
)
from des.workforce import WorkforceHoursResource

if TYPE_CHECKING:
    from des.patient import Patient
    from des.system import AutismPathwaySystem


class WorkshopGroup:
    """
    Run a multi-session clinical workshop programme for a formed patient group.

    Each session requests clinician hours from the shared workforce resource
    at the highest priority level.  Sessions are separated by
    ``workshop_session_interval_weeks * 7`` days.  When the final session
    completes, all patients are marked as exited and removed from the
    active-patient-ID set of :class:`~des.workshop_manager.WorkshopManager`.

    Parameters
    ----------
    group_id : int
        Unique identifier for this workshop group.
    patients : list[Patient]
        Patients enrolled in this group.
    system : AutismPathwaySystem
        Parent simulation system providing the environment and shared
        workforce resource.
    """

    def __init__(
        self,
        group_id: int,
        patients: List[Patient],
        system: AutismPathwaySystem,
    ) -> None:
        """
        Bind the group to its patients and owning simulation system.

        Parameters
        ----------
        group_id : int
            Unique group identifier assigned by
            :class:`~des.workshop_manager.WorkshopManager`.
        patients : list[Patient]
            Enrolled patients (at least one).
        system : AutismPathwaySystem
            Parent system supplying the SimPy environment and shared
            workforce resource.
        """
        self.group_id = group_id
        self.patients = patients
        self.system = system
        self.env = system.env
        self.experiment = system.experiment
        self.audit = system.experiment.audit

    def process(self) -> Generator[simpy.Event, None, None]:
        """
        SimPy generator running all workshop sessions for this group.

        For each session the group requests clinician hours at
        :data:`~des.workforce.WorkforceHoursResource.PRIORITY_WORKSHOP`,
        waits for service, records hours in the audit, then waits the
        inter-session interval before the next session.  After the final
        session all patients' audit records are finalised with exit times
        and route ``'workshop_complete'``.

        Yields
        ------
        simpy.Event
            Workforce-request and inter-session gap timeout events.
        """
        total_sessions = self.experiment.workshop_num_sessions
        interval_days = self.experiment.workshop_session_interval_weeks * 7
        share = 1.0 / len(self.patients)

        completion_time = None
        for session_num in range(1, total_sessions + 1):
            duration_hours = float(self.experiment.workshop_times_dis.sample())
            yield from self.system.workforce.request_hours(
                duration_hours,
                WorkforceHoursResource.PRIORITY_WORKSHOP,
            )
            service_start = self.env.now
            for patient in self.patients:
                trace_workshop_session_started(
                    service_start,
                    patient.patient_id,
                    session_num,
                    total_sessions,
                    self.group_id,
                )
            for patient in self.patients:
                self.audit.update_patient(
                    patient.patient_id,
                    workshop_hours_add=duration_hours * share,
                )
            yield self.env.timeout(duration_hours / 24.0)
            completion_time = self.env.now
            for patient in self.patients:
                trace_workshop_session_completed(
                    completion_time,
                    patient.patient_id,
                    session_num,
                    total_sessions,
                )
            if session_num < total_sessions:
                yield self.env.timeout(interval_days)

        # Programme finished: pathway exit = end of last session.
        for patient in self.patients:
            self.system.workshop_manager.active_patient_ids.discard(patient.patient_id)
            self.audit.update_patient(
                patient.patient_id,
                workshop_completion=completion_time,
                exit_time=completion_time,
                exit_route="workshop_complete",
            )
            trace_pathway_complete(
                completion_time,
                patient.patient_id,
                f"clinical workshops ({total_sessions} sessions)",
            )
