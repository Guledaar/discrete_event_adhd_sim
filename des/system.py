"""SimPy pathway engine with one shared clinical-hour pool."""

from __future__ import annotations

import itertools
from typing import Generator

import simpy

from des.experiment import Experiment
from des.patient import Patient
from des.workforce import WorkforceHoursResource
from des.workshop_manager import WorkshopManager


class AutismPathwaySystem:
    """
    SimPy pathway engine with a single shared clinical-hour pool.

    Assessment appointments and post-diagnosis clinical support (workshops)
    draw from the same weekday clinician-hour budget managed by
    :class:`~des.workforce.WorkforceHoursResource`.  Priority scheduling
    gives workshops precedence over returning assessments, then new
    assessments.

    Parameters
    ----------
    env : simpy.Environment
        SimPy discrete-event environment.
    experiment : Experiment
        Scenario configuration supplying distributions, workforce capacity,
        and the patient audit object.

    Attributes
    ----------
    env : simpy.Environment
        Owning SimPy environment.
    experiment : Experiment
        Active scenario configuration.
    audit : Audit
        Patient state recorder shared with all pathway processes.
    workforce : WorkforceHoursResource
        Shared weekday clinician-hour scheduler.
    workshop_manager : WorkshopManager
        Manages formation and execution of workshop groups.
    next_workshop_group_id : int
        Auto-incrementing counter for workshop group IDs.
    next_patient_id : int
        Auto-incrementing counter for patient IDs.
    """

    def __init__(self, env: simpy.Environment, experiment: Experiment) -> None:
        """
        Initialise the pathway engine and register the weekday scheduler.

        Parameters
        ----------
        env : simpy.Environment
            SimPy environment that will drive all events.
        experiment : Experiment
            Scenario configuration with distributions and workforce parameters.
        """
        self.env = env
        self.experiment = experiment
        self.audit = experiment.audit

        self.workforce = WorkforceHoursResource(
            env,
            experiment,
            audit=self.audit,
            name="clinical",
        )
        self.workshop_manager = WorkshopManager(env, self)
        self.next_workshop_group_id = 1
        self.next_patient_id = 1

    def run(self) -> Generator[simpy.Event, None, None]:
        """
        Generate patient arrivals and spawn pathway processes until halted.

        Inter-arrival times are sampled from the exponential distribution on
        the experiment.  Referrals that fall on a weekend are deferred to
        Monday morning to model weekday-only operation.

        Yields
        ------
        simpy.Event
            Timeout events for inter-arrival gaps and weekend deferrals.
        """
        for _ in itertools.count(start=1):
            yield self.env.timeout(float(self.experiment.iat_dist.sample()))
            current_week_time = self.env.now % 7
            if current_week_time >= 5.0:
                yield self.env.timeout(7.0 - current_week_time)
            patient = Patient(self.next_patient_id, self)
            self.next_patient_id += 1
            self.env.process(patient.process())
