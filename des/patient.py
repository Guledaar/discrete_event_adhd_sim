"""One patient through the NHS neurodevelopmental assessment pathway."""

from __future__ import annotations

from typing import TYPE_CHECKING, Generator

import simpy

from des.trace import (
    trace_admin_cleared,
    trace_admin_removed,
    trace_assessment_completed,
    trace_assessment_gap,
    trace_assessment_started,
    trace_assessment_waiting,
    trace_assessments_finished,
    trace_assessments_required,
    trace_diagnosis,
    trace_pathway_complete,
    trace_referral,
    trace_triage_accepted,
    trace_triage_rejected,
    trace_virtual_support,
)
from des.workforce import WorkforceHoursResource

if TYPE_CHECKING:
    from des.system import AutismPathwaySystem


class Patient:
    """
    Simulate one patient through the NHS neurodevelopmental assessment pathway.

    Stages: triage → admin review → assessment → diagnosis →
    virtual support or clinical workshop.

    Parameters
    ----------
    patient_id : int
        Unique patient identifier.
    system : AutismPathwaySystem
        Parent simulation system supplying env, experiment, and workforce.

    Attributes
    ----------
    appointments_completed : int
        Assessment appointments finished so far.
    appointments_required : int
        Total assessment appointments sampled for this patient.
    clinician_hours_consumed : float
        Clinician hours consumed by this patient's assessments.
    """

    def __init__(self, patient_id: int, system: AutismPathwaySystem) -> None:
        self.patient_id = patient_id
        self.system = system
        self.env = system.env
        self.experiment = system.experiment
        self.audit = self.experiment.audit
        self.appointments_completed = 0
        self.appointments_required = 0
        self.clinician_hours_consumed = 0.0

    def process(self) -> Generator[simpy.Event, None, None]:
        """
        SimPy generator driving the full patient pathway.

        Yields
        ------
        simpy.Event
            Workforce requests, appointment durations, and inter-appointment gaps.
        """
        audit = self.audit
        pid = self.patient_id

        arrival_time = self.env.now
        audit.update_patient(pid, arrival_time=arrival_time)
        trace_referral(arrival_time, pid)

        if self.experiment.referral_reject_dist.sample():
            audit.update_patient(
                pid,
                triage_outcome="rejected",
                exit_time=self.env.now,
                exit_route="referral_rejected",
            )
            trace_triage_rejected(self.env.now, pid)
            return

        audit.update_patient(pid, triage_outcome="accepted")
        trace_triage_accepted(self.env.now, pid)

        if self.experiment.admin_removal_dist.sample():
            audit.update_patient(
                pid,
                admin_removal=True,
                exit_time=self.env.now,
                exit_route="admin_removal",
            )
            trace_admin_removed(self.env.now, pid)
            return

        audit.update_patient(pid, admin_removal=False)
        trace_admin_cleared(self.env.now, pid)

        self.appointments_required = int(
            self.experiment.assessment_count_dist.sample()
        )
        audit.update_patient(pid, appointments_required=self.appointments_required)
        trace_assessments_required(self.env.now, pid, self.appointments_required)

        yield from self._run_assessments()
        self._run_post_assessment()

    def _run_assessments(self) -> Generator[simpy.Event, None, None]:
        """
        Run all required assessment appointments.

        Yields
        ------
        simpy.Event
            Workforce hour requests, service timeouts, and inter-appointment gaps.
        """
        audit = self.audit
        pid = self.patient_id

        for appointment in range(self.appointments_required):
            appointment_num = appointment + 1
            duration_hours = float(self.experiment.assessment_time_dist.sample())
            priority = (
                WorkforceHoursResource.PRIORITY_RETURNING
                if appointment > 0
                else WorkforceHoursResource.PRIORITY_NEW
            )
            queue_entry_time = self.env.now
            queue_pos = self.system.workforce.queue_position_for(priority)
            trace_assessment_waiting(
                queue_entry_time, pid, appointment_num, self.appointments_required, queue_pos
            )
            yield from self.system.workforce.request_hours(duration_hours, priority)
            service_start = self.env.now
            trace_assessment_started(
                service_start, pid, appointment_num, self.appointments_required, duration_hours
            )
            if audit.patients[pid].assessment_start is None:
                audit.update_patient(pid, assessment_start=service_start)
            audit.update_patient(pid, assessment_hours_add=duration_hours)
            yield self.env.timeout(duration_hours / 24.0)
            service_end = self.env.now
            audit.update_patient(pid, appointments_completed=appointment_num)
            self.appointments_completed += 1
            self.clinician_hours_consumed += duration_hours
            trace_assessment_completed(
                service_end, pid, appointment_num, self.appointments_required
            )
            if appointment < self.appointments_required - 1:
                trace_assessment_gap(
                    service_end, pid, self.experiment.assessment_gap_days
                )
                yield self.env.timeout(self.experiment.assessment_gap_days)

        audit.update_patient(pid, assessment_completion=self.env.now)
        trace_assessments_finished(self.env.now, pid, self.appointments_required)

    def _run_post_assessment(self) -> None:
        """
        Apply diagnosis and route to virtual support or clinical workshop.

        Notes
        -----
        No diagnosis or virtual support exits immediately; clinical support
        enrols the patient with :class:`~des.workshop_manager.WorkshopManager`.
        """
        audit = self.audit
        pid = self.patient_id

        if not self.experiment.diagnosis_dist.sample():
            audit.update_patient(
                pid,
                diagnosis=False,
                exit_time=self.env.now,
                exit_route="no_diagnosis",
            )
            trace_diagnosis(self.env.now, pid, diagnosed=False)
            return

        audit.update_patient(pid, diagnosis=True)
        trace_diagnosis(self.env.now, pid, diagnosed=True)

        if self.experiment.virtual_support_dist.sample():
            audit.update_patient(
                pid,
                support_type="virtual",
                exit_time=self.env.now,
                exit_route="virtual_support",
            )
            trace_virtual_support(self.env.now, pid)
            trace_pathway_complete(self.env.now, pid, "virtual support")
            return

        audit.update_patient(pid, support_type="clinical")
        self.system.workshop_manager.join(self)
