"""Autism pathway system."""

import itertools

import simpy

from adhd_simpy.Model.parameters import RUN_LENGTH
from adhd_simpy.Model.patient import Patient
from adhd_simpy.Model.resources import WorkforceHoursResource

class AutismPathwaySystem:
    """
    SimPy pathway engine: arrivals, resources, audit, and patient spawning.

    Creates seven ``WorkforceHoursResource`` stage resources from ``Experiment`` workforce settings, wires
    distribution objects, and runs weekday-only referral arrivals until
    ``arrival_stop``.

    Parameters
    ----------
    env : simpy.Environment
        SimPy simulation environment.
    experiment : Experiment
        Scenario configuration and flow counter store.
    collection_start : float, default 0
        Simulation day when collection-cohort KPIs begin.
    arrival_stop : float, optional
        Last day for new referrals; defaults to ``collection_start + RUN_LENGTH``.
    event_logger : optional
        ``PathwayEventLogger`` for animation / event export.

    Attributes
    ----------
    resources : dict
        Mapping stage name → resource instance.
    """

    def __init__(self, env, experiment, collection_start=0, arrival_stop=None, event_logger=None):
        self.env = env
        self.experiment = experiment
        self.args = experiment.results
        self.auditor = experiment.auditor
        self.event_logger = event_logger
        self.collection_start = collection_start
        self.arrival_stop = arrival_stop if arrival_stop is not None else (collection_start + RUN_LENGTH)

        for attr in [
            "referral_reject_dist", "screening_time_dist", "screening_discharge_dist",
            "pre_ass_time_dist", "pre_ass_reject_dist", "assessment_time_dist",
            "non_diag_at_assessment_dist", "needs_further_assessment_dist",
            "further_assessment_time_dist", "non_diag_at_further_assessment_dist",
            "non_diag_at_outcome_dist", "post_diag_clinical_dist",
            "post_diag_clinical_time_dist", "post_diag_other_time_dist", "review_time_dist",
            "review_outcome_dist", "screening_priority_dist", "pre_assessment_priority_dist",
            "assessment_priority_dist", "further_assessment_priority_dist",
            "post_diag_clinical_priority_dist", "post_diag_other_priority_dist", "review_priority_dist",
        ]:
            setattr(self, attr, getattr(experiment, attr))

        resource_specs = [
            ("screening", "slots_screening", "workforce_hours_screening"),
            ("pre_assessment", "slots_pre_assessment", "workforce_hours_pre_assessment"),
            ("assessment", "slots_assessment", "workforce_hours_assessment"),
            ("further_assessment", "slots_further_assessment", "workforce_hours_further_assessment"),
            ("post_diag_clinical", "slots_post_diag_clinical", "workforce_hours_post_diag_clinical"),
            ("post_diag_other", "slots_post_diag_other", "workforce_hours_post_diag_other"),
            ("review", "slots_review", "workforce_hours_review"),
        ]
        self.resources = {}
        # Capacity metrics use the full simulation window (through drain), not referral cohort end.
        capacity_collection_end = float("inf")
        for name, slot_attr, hours_attr in resource_specs:
            slots = getattr(experiment, slot_attr)
            hours = getattr(experiment, hours_attr)
            self.resources[name] = WorkforceHoursResource(
                env,
                hours,
                name=name,
                collection_start=self.collection_start,
                collection_end=capacity_collection_end,
                derived_slots_per_day=slots,
            )

        self.screening_resource = self.resources["screening"]
        self.pre_assessment_resource = self.resources["pre_assessment"]
        self.assessment_resource = self.resources["assessment"]
        self.further_assessment_resource = self.resources["further_assessment"]
        self.post_diag_clinical_resource = self.resources["post_diag_clinical"]
        self.post_diag_other_resource = self.resources["post_diag_other"]
        self.review_resource = self.resources["review"]

# --- Referral generator ---
    def run(self):
        """
        SimPy generator: referral arrivals and patient process spawning.

        Skips weekend arrival times by advancing to the next Monday. Stops
        generating referrals when ``env.now >= arrival_stop``.

        Yields
        ------
        simpy events
            Inter-arrival timeouts and weekend skips.
        """
        self.env.process(self._audit_loop())
        self.next_patient_id = 1
        for pid in itertools.count(start=1):
            if self.env.now >= self.arrival_stop:
                break
            delay = self.experiment.iat_dist.sample()
            yield self.env.timeout(delay)
            while True:
                if self.env.now >= self.arrival_stop:
                    break
                current_week_time = self.env.now % 7
                if current_week_time >= 5.0:
                    time_to_monday = 7.0 - current_week_time
                    yield self.env.timeout(time_to_monday)
                    delay = self.experiment.iat_dist.sample()
                    yield self.env.timeout(delay)
                else:
                    break
            if self.env.now < self.arrival_stop:
                patient = Patient(self.next_patient_id, self)
                self.next_patient_id += 1
                self.env.process(patient.process())

# --- Daily queue snapshots ---
    def _audit_loop(self):
        while True:
            yield self.env.timeout(1.0)
            if self.env.now >= self.collection_start:
                for name, res in self.resources.items():
                    self.auditor.record_queue_length(name, res.count_queue(), now=self.env.now)
