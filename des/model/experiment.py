"""Experiment configuration."""

import numpy as np

from des.model.distributions import Bernoulli, Choice, Exponential, Triangular, generate_seed_vector
from des.model.parameters import (
    DEFAULT_RND_SET,
    DURATION_ASSESSMENT,
    DURATION_FURTHER_ASSESSMENT,
    DURATION_POST_DIAG_CLINICAL,
    DURATION_POST_DIAG_OTHER,
    DURATION_PRE_ASSESSMENT,
    DURATION_REVIEW,
    DURATION_SCREENING,
    IAT_WEEKDAY,
    N_STREAMS,
    PCT_NEEDS_FURTHER_ASSESSMENT,
    PCT_NON_DIAGNOSIS_AT_ASSESSMENT,
    PCT_NON_DIAGNOSIS_AT_FURTHER_ASSESSMENT,
    PCT_NON_DIAGNOSIS_AT_OUTCOME,
    PCT_POST_DIAG_CLINICAL,
    PCT_PRE_ASS_REJECTED,
    PCT_PRIORITY_ASSESSMENT,
    PCT_PRIORITY_FURTHER_ASSESSMENT,
    PCT_PRIORITY_POST_DIAG_CLINICAL,
    PCT_PRIORITY_POST_DIAG_OTHER,
    PCT_PRIORITY_PRE_ASSESSMENT,
    PCT_PRIORITY_REVIEW,
    PCT_PRIORITY_SCREENING,
    PCT_REFERRAL_REJECTED,
    PCT_REMOVAL_DISCHARGE,
    PCT_REVIEW_CONTINUE_SUPPORT,
    PCT_REVIEW_FORMAL_DISCHARGE,
    PCT_REVIEW_SELF_REMOVAL,
    PCT_SCREENING_DISCHARGED,
    WORKFORCE_HOURS_ASSESSMENT,
    WORKFORCE_HOURS_FURTHER_ASSESSMENT,
    WORKFORCE_HOURS_POST_DIAG_CLINICAL,
    WORKFORCE_HOURS_POST_DIAG_OTHER,
    WORKFORCE_HOURS_PRE_ASSESSMENT,
    WORKFORCE_HOURS_REVIEW,
    WORKFORCE_HOURS_SCREENING,
)
from des.model.utils import derive_daily_slots, triangular_mean_hours

generate_seed_vector(one_seed_to_rule_them_all=42, size=20)

class Experiment:
    """
    Scenario configuration, RNG streams, and flow counter storage.

    Holds pathway branching probabilities, appointment duration triplets,
    workforce hours, derived slot counts, and
    seeded distribution objects consumed by :class:`AutismPathwaySystem`.

    Parameters
    ----------
    auditor : Audit
        KPI collector updated during simulation.
    random_number_set : int, default 42
        Master seed for reproducible stream spawning.
    n_streams : int, default 25
        Number of independent RNG streams.
    use_fixed_seed : bool, default True
        If ``True``, spawn deterministic child seeds per replication.
    iat : float, default ``IAT_WEEKDAY``
        Mean inter-arrival time between weekday referrals (simulation days).
    **kwargs
        Override any module default (durations, workforce hours, branching,
        workforce hour overrides, etc.).

    Attributes
    ----------
    results : dict
        Flow counters initialised by :meth:`init_results_variables`.
    derived_capacity : dict
        Per-stage workforce hours, mean duration, and derived slots.
    """

    def __init__(
        self,
        auditor,
        random_number_set=DEFAULT_RND_SET,
        n_streams=N_STREAMS,
        use_fixed_seed=True,
        iat=IAT_WEEKDAY,
        **kwargs,
    ):
        self.auditor = auditor
        self.random_number_set = random_number_set
        self.base_random_number_set = random_number_set
        self.n_streams = n_streams
        self.use_fixed_seed = use_fixed_seed
        self.iat = iat

        self.triage_rejected = kwargs.get("triage_rejected", PCT_REFERRAL_REJECTED)
        self.screening_discharge = kwargs.get("screening_discharge", PCT_SCREENING_DISCHARGED)
        self.pre_assessment_rejection = kwargs.get("pre_assessment_rejection", PCT_PRE_ASS_REJECTED)
        self.pct_non_diag_at_assessment = kwargs.get("pct_non_diag_at_assessment", PCT_NON_DIAGNOSIS_AT_ASSESSMENT)
        self.pct_needs_further_assessment = kwargs.get(
            "pct_needs_further_assessment", PCT_NEEDS_FURTHER_ASSESSMENT
        )
        self.pct_non_diag_at_further_assessment = kwargs.get(
            "pct_non_diag_at_further_assessment", PCT_NON_DIAGNOSIS_AT_FURTHER_ASSESSMENT
        )
        self.pct_non_diag_at_diagnostic_outcome = kwargs.get(
            "pct_non_diag_at_diagnostic_outcome", PCT_NON_DIAGNOSIS_AT_OUTCOME
        )
        self.pct_post_diag_clinical = kwargs.get("pct_post_diag_clinical", PCT_POST_DIAG_CLINICAL)
        if any(
            k in kwargs
            for k in (
                "pct_review_continue_support",
                "pct_review_formal_discharge",
                "pct_review_self_removal",
            )
        ):
            self.pct_review_continue_support = float(
                kwargs.get("pct_review_continue_support", PCT_REVIEW_CONTINUE_SUPPORT)
            )
            self.pct_review_formal_discharge = float(
                kwargs.get("pct_review_formal_discharge", PCT_REVIEW_FORMAL_DISCHARGE)
            )
            self.pct_review_self_removal = float(
                kwargs.get("pct_review_self_removal", PCT_REVIEW_SELF_REMOVAL)
            )
        else:
            rem = float(kwargs.get("pct_removal_discharge", PCT_REMOVAL_DISCHARGE))
            self.pct_review_continue_support = 0.0
            self.pct_review_formal_discharge = rem
            self.pct_review_self_removal = 1.0 - rem
        self.pct_removal_discharge = self.pct_review_formal_discharge

        self.dur_screening = kwargs.get("dur_screening", DURATION_SCREENING)
        self.dur_pre_assessment = kwargs.get("dur_pre_assessment", DURATION_PRE_ASSESSMENT)
        self.dur_assessment = kwargs.get("dur_assessment", DURATION_ASSESSMENT)
        self.dur_further_assessment = kwargs.get("dur_further_assessment", DURATION_FURTHER_ASSESSMENT)
        self.dur_post_diag_clinical = kwargs.get("dur_post_diag_clinical", DURATION_POST_DIAG_CLINICAL)
        self.dur_post_diag_other = kwargs.get("dur_post_diag_other", DURATION_POST_DIAG_OTHER)
        self.dur_review = kwargs.get("dur_review", DURATION_REVIEW)

        self.workforce_hours_screening = kwargs.get("workforce_hours_screening", WORKFORCE_HOURS_SCREENING)
        self.workforce_hours_pre_assessment = kwargs.get("workforce_hours_pre_assessment", WORKFORCE_HOURS_PRE_ASSESSMENT)
        self.workforce_hours_assessment = kwargs.get("workforce_hours_assessment", WORKFORCE_HOURS_ASSESSMENT)
        self.workforce_hours_further_assessment = kwargs.get(
            "workforce_hours_further_assessment", WORKFORCE_HOURS_FURTHER_ASSESSMENT
        )
        self.workforce_hours_post_diag_clinical = kwargs.get(
            "workforce_hours_post_diag_clinical", WORKFORCE_HOURS_POST_DIAG_CLINICAL
        )
        self.workforce_hours_post_diag_other = kwargs.get(
            "workforce_hours_post_diag_other", WORKFORCE_HOURS_POST_DIAG_OTHER
        )
        self.workforce_hours_review = kwargs.get("workforce_hours_review", WORKFORCE_HOURS_REVIEW)

        self.pct_priority_screening = kwargs.get("pct_priority_screening", PCT_PRIORITY_SCREENING)
        self.pct_priority_pre_assessment = kwargs.get("pct_priority_pre_assessment", PCT_PRIORITY_PRE_ASSESSMENT)
        self.pct_priority_assessment = kwargs.get("pct_priority_assessment", PCT_PRIORITY_ASSESSMENT)
        self.pct_priority_further_assessment = kwargs.get(
            "pct_priority_further_assessment", PCT_PRIORITY_FURTHER_ASSESSMENT
        )
        self.pct_priority_post_diag_clinical = kwargs.get(
            "pct_priority_post_diag_clinical", PCT_PRIORITY_POST_DIAG_CLINICAL
        )
        self.pct_priority_post_diag_other = kwargs.get("pct_priority_post_diag_other", PCT_PRIORITY_POST_DIAG_OTHER)
        self.pct_priority_review = kwargs.get("pct_priority_review", PCT_PRIORITY_REVIEW)

        self.compute_capacity_from_workforce()

        # Direct workforce-hour overrides (used by V&V infinite-capacity tests)
        workforce_overrides = [
            "workforce_hours_screening",
            "workforce_hours_pre_assessment",
            "workforce_hours_assessment",
            "workforce_hours_further_assessment",
            "workforce_hours_post_diag_clinical",
            "workforce_hours_post_diag_other",
            "workforce_hours_review",
        ]
        for attr in workforce_overrides:
            if attr in kwargs:
                setattr(self, attr, kwargs[attr])
        if any(k in kwargs for k in workforce_overrides):
            self.compute_capacity_from_workforce()

        self.init_results_variables()
        self.init_sampling()

# --- Capacity metadata ---
    def compute_capacity_from_workforce(self):
        """
        Build reporting metadata from workforce hours and duration triplets.

        Populates ``derived_capacity`` and ``slots_*`` for reporting.

        Does **not** change the hour budget used by
        :class:`WorkforceHoursResource`.
        """
        mapping = [
            ("workforce_hours_screening", "dur_screening", "slots_screening"),
            ("workforce_hours_pre_assessment", "dur_pre_assessment", "slots_pre_assessment"),
            ("workforce_hours_assessment", "dur_assessment", "slots_assessment"),
            ("workforce_hours_further_assessment", "dur_further_assessment", "slots_further_assessment"),
            ("workforce_hours_post_diag_clinical", "dur_post_diag_clinical", "slots_post_diag_clinical"),
            ("workforce_hours_post_diag_other", "dur_post_diag_other", "slots_post_diag_other"),
            ("workforce_hours_review", "dur_review", "slots_review"),
        ]
        self.derived_capacity = {}
        for hours_attr, dur_attr, slot_attr in mapping:
            hours = getattr(self, hours_attr)
            duration = getattr(self, dur_attr)
            slots = derive_daily_slots(hours, duration)
            setattr(self, slot_attr, slots)
            stage = slot_attr.replace("slots_", "")
            self.derived_capacity[stage] = {
                "workforce_hours_per_day": hours,
                "mean_duration_hours": triangular_mean_hours(duration),
                "derived_slots_per_day": slots,
            }

    def set_random_no_set(self, rep):
        """
        Advance the master seed for replication ``rep`` and rebuild distributions.

        Parameters
        ----------
        rep : int
            Replication index added to ``base_random_number_set``.
        """
        self.random_number_set = self.base_random_number_set + rep
        self.init_sampling()

# --- RNG streams ---
    def init_sampling(self):
        """
        Initialise or re-seed all stochastic distributions.

        Creates inter-arrival, duration, branching, review-outcome, and priority
        distributions using ``n_streams`` independent child seeds when
        ``use_fixed_seed`` is ``True``.
        """
        int_seeds = [None] * self.n_streams
        if self.use_fixed_seed:
            master_seq = np.random.SeedSequence(self.random_number_set)
            child_sequences = master_seq.spawn(self.n_streams)
            for i in range(self.n_streams):
                int_seeds[i] = int(child_sequences[i].generate_state(1)[0])

        def to_days(hours):
            return [h / 24.0 for h in hours]

        self.iat_dist = Exponential(self.iat, random_seed=int_seeds[0])
        self.screening_time_dist = Triangular(*to_days(self.dur_screening), random_seed=int_seeds[1])
        self.pre_ass_time_dist = Triangular(*to_days(self.dur_pre_assessment), random_seed=int_seeds[2])
        self.assessment_time_dist = Triangular(*to_days(self.dur_assessment), random_seed=int_seeds[3])
        self.referral_reject_dist = Bernoulli(self.triage_rejected, random_seed=int_seeds[4])
        self.screening_discharge_dist = Bernoulli(self.screening_discharge, random_seed=int_seeds[5])
        self.pre_ass_reject_dist = Bernoulli(self.pre_assessment_rejection, random_seed=int_seeds[6])
        self.non_diag_at_assessment_dist = Bernoulli(self.pct_non_diag_at_assessment, random_seed=int_seeds[7])
        self.needs_further_assessment_dist = Bernoulli(
            self.pct_needs_further_assessment, random_seed=int_seeds[8]
        )
        self.further_assessment_time_dist = Triangular(
            *to_days(self.dur_further_assessment), random_seed=int_seeds[9]
        )
        self.non_diag_at_further_assessment_dist = Bernoulli(
            self.pct_non_diag_at_further_assessment, random_seed=int_seeds[10]
        )
        self.non_diag_at_outcome_dist = Bernoulli(
            self.pct_non_diag_at_diagnostic_outcome, random_seed=int_seeds[11]
        )
        self.post_diag_clinical_dist = Bernoulli(self.pct_post_diag_clinical, random_seed=int_seeds[12])
        self.post_diag_clinical_time_dist = Triangular(
            *to_days(self.dur_post_diag_clinical), random_seed=int_seeds[13]
        )
        self.post_diag_other_time_dist = Triangular(*to_days(self.dur_post_diag_other), random_seed=int_seeds[14])
        self.review_time_dist = Triangular(*to_days(self.dur_review), random_seed=int_seeds[15])
        self.review_outcome_dist = Choice(
            ["continue", "formal_discharge", "self_removal"],
            [
                self.pct_review_continue_support,
                self.pct_review_formal_discharge,
                self.pct_review_self_removal,
            ],
            random_seed=int_seeds[16],
        )
        self.removal_discharge_dist = Bernoulli(self.pct_removal_discharge, random_seed=int_seeds[17])

        priority_specs = [
            (self.pct_priority_screening, 18, "screening_priority_dist"),
            (self.pct_priority_pre_assessment, 19, "pre_assessment_priority_dist"),
            (self.pct_priority_assessment, 20, "assessment_priority_dist"),
            (self.pct_priority_further_assessment, 21, "further_assessment_priority_dist"),
            (self.pct_priority_post_diag_clinical, 22, "post_diag_clinical_priority_dist"),
            (self.pct_priority_post_diag_other, 23, "post_diag_other_priority_dist"),
            (self.pct_priority_review, 24, "review_priority_dist"),
        ]
        for prob, seed_idx, attr in priority_specs:
            setattr(self, attr, Bernoulli(prob, random_seed=int_seeds[seed_idx]))

# --- Flow counters ---
    def init_results_variables(self):
        """
        Reset ``results`` flow counters to zero.

        Counters cover arrivals, service completions, branching flows, exits,
        and review-loop statistics for collection-cohort accounting.
        """
        self.results = {
            "ARRIVED_ALL": 0,
            "EXIT_ALL": 0,
            "ARRIVED_TOTAL": 0,
            "EXIT_TOTAL": 0,
            "CLINICAL_COMPLETED_TOTAL": 0,
            "ARRIVED_REFERRAL": 0,
            "FLOW_REFERRAL_ACCEPTED": 0,
            "EXIT_REFERRAL_REJECTED": 0,
            "ARRIVED_SCREENING": 0,
            "SERVICE_SCREENING_COMPLETED": 0,
            "FLOW_SCREENING_PASSED": 0,
            "EXIT_SCREENING_DISCHARGED": 0,
            "ARRIVED_PRE_ASSESS": 0,
            "SERVICE_PRE_ASSESS_COMPLETED": 0,
            "FLOW_PRE_ASSESS_PASSED": 0,
            "EXIT_PRE_ASSESS_REJECTED": 0,
            "ARRIVED_ASSESSMENT": 0,
            "SERVICE_ASSESSMENT_COMPLETED": 0,
            "FLOW_ASSESSMENT_PASSED": 0,
            "EXIT_ASSESSMENT_NON_DIAGNOSIS": 0,
            "FLOW_NEEDS_FURTHER_ASSESSMENT": 0,
            "FLOW_FURTHER_ASSESS_SKIPPED": 0,
            "ARRIVED_FURTHER_ASSESS": 0,
            "SERVICE_FURTHER_ASSESS_COMPLETED": 0,
            "FLOW_FURTHER_ASSESS_PASSED": 0,
            "EXIT_FURTHER_NON_DIAGNOSIS": 0,
            "ARRIVED_DIAGNOSTIC_OUTCOME": 0,
            "EXIT_OUTCOME_NON_DIAGNOSIS": 0,
            "FLOW_DIAGNOSIS_CONFIRMED": 0,
            "FLOW_POST_DIAG_CLINICAL_ACCEPTED": 0,
            "SERVICE_POST_DIAG_CLINICAL_COMPLETED": 0,
            "FLOW_POST_DIAG_OTHER_ACCEPTED": 0,
            "SERVICE_POST_DIAG_OTHER_COMPLETED": 0,
            "FLOW_POST_DIAG_SUPPORT_REVISIT": 0,
            "SERVICE_REVIEW_COMPLETED": 0,
            "FLOW_REVIEW_VISITS": 0,
            "FLOW_REVIEW_CONTINUE_SUPPORT": 0,
            "EXIT_FORMAL_DISCHARGE": 0,
            "EXIT_SELF_REMOVED": 0,
            "FLOW_PRIORITY_TOTAL": 0,
        }
