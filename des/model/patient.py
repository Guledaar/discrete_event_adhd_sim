"""Patient SimPy process."""

from des.model.parameters import MAX_REVIEW_LOOPS
from des.model.utils import trace

class Patient:
    """
    One patient through the NHS autism assessment pathway (SimPy process).

    Implements the flow described in **Section 8**: triage, seven
    capacity-constrained clinical stages, diagnostic outcome, post-diagnosis
    support, and review loop. See :meth:`process` for the full generator.

    Implements referral → triage → capacity-constrained clinical stages →
    diagnostic outcome → post-diagnostic support → review loop → discharge.
    Flow counters increment only for collection-cohort referrals when
    ``collect_stats`` is ``True``.

    Parameters
    ----------
    patient_id : int
        Unique identifier within a simulation run.
    system : AutismPathwaySystem
        Parent system providing resources, distributions, and audit hooks.

    Attributes
    ----------
    collect_stats : bool
        Set at referral time if referral falls in the collection window.
    """

    DAYS_OF_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    STAGE_QUEUE_LABELS = {
        "screening": "SCREENING",
        "pre_assessment": "PRE-ASSESSMENT",
        "assessment": "CORE ASSESSMENT",
        "further_assessment": "FURTHER ASSESSMENT",
        "post_diag_clinical": "POST-DIAG CLINICAL SUPPORT",
        "post_diag_other": "POST-DIAG OTHER SUPPORT",
        "review": "FINAL CASE DISCHARGE REVIEW",
    }

    STAGE_ENTER_LABELS = {
        "screening": "SCREENING",
        "pre_assessment": "PRE-ASSESSMENT",
        "assessment": "CORE ASSESSMENT",
        "further_assessment": "FURTHER ASSESSMENT",
        "post_diag_clinical": "POST-DIAG CLINICAL SUPPORT",
        "post_diag_other": "POST-DIAG OTHER SUPPORT",
        "review": "FINAL DISCHARGE REVIEW",
    }

    STAGES_WITH_QUEUE_POS = {
        "screening", "pre_assessment", "assessment", "further_assessment",
    }

    EXIT_TRACE_MESSAGES = {
        "referral_rejected": "Exit - Referral Rejected at Triage.",
        "screening_discharged": "Exit - Discharged after Screening.",
        "pre_assessment_rejected": "Exit - Rejected at Pre-Assessment stage.",
        "assessment_non_diagnosis": "Exit - Non-Diagnosis at Core Assessment.",
        "further_non_diagnosis": "Exit - Non-Diagnosis at Further Assessment.",
        "outcome_non_diagnosis": "Exit - Non-Diagnosis at Diagnostic Outcome.",
        "formal_discharge": "Complete - Formal Discharge.",
        "self_removed": "Complete - Self-Removal path.",
    }

    def __init__(self, patient_id, system):
        self.patient_id = patient_id
        self.system = system
        self.env = system.env
        self.args = system.args
        self.auditor = system.auditor
        self.event_logger = system.event_logger
        self.collect_stats = False  # set from referral time in process()
        self._current_stage = "referral"

    def _get_timestamp(self):
        day_name = self.DAYS_OF_WEEK[int(self.env.now % 7)]
        return f"[Time {self.env.now:.3f} | {day_name}]"

    def _inc(self, key, amount=1):
        if self.collect_stats:
            self.args[key] += amount
        if key == "ARRIVED_TOTAL":
            self.args["ARRIVED_ALL"] += amount
        elif key == "EXIT_TOTAL":
            self.args["EXIT_ALL"] += amount

    def _transition(self, to_stage: str) -> None:
        if self.event_logger and to_stage != self._current_stage:
            self.event_logger.log_stage_transition(
                self.patient_id, self._current_stage, to_stage
            )
        self._current_stage = to_stage

    def _complete_pathway(self) -> None:
        """Increment collection-cohort exit counters once at pathway end."""
        self._inc("CLINICAL_COMPLETED_TOTAL")
        self._inc("EXIT_TOTAL")

    def _exit_pathway(self, exit_reason: str) -> None:
        msg = self.EXIT_TRACE_MESSAGES.get(exit_reason)
        if msg:
            trace(f"{self._get_timestamp()} Patient {self.patient_id} {msg}")
        if self.event_logger:
            self.event_logger.log_pathway_exit(
                self.patient_id, exit_reason, self._current_stage
            )

# --- Capacity interaction ---
    def _wait_for_slot(self, stage_name, resource, priority_dist, service_duration_days=None):
        self._transition(stage_name)
        queue_pos = resource.count_queue()
        self.auditor.record_queue_length(stage_name, queue_pos, now=self.env.now)
        queue_label = self.STAGE_QUEUE_LABELS.get(stage_name, stage_name.upper())
        if stage_name in self.STAGES_WITH_QUEUE_POS:
            trace(
                f"{self._get_timestamp()} Patient {self.patient_id} "
                f"queued for {queue_label} (Queue pos: {queue_pos})."
            )
        else:
            trace(
                f"{self._get_timestamp()} Patient {self.patient_id} "
                f"queued for {queue_label}."
            )
        is_priority = priority_dist.sample() == 1
        if is_priority:
            self._inc("FLOW_PRIORITY_TOTAL")
        if self.event_logger:
            self.event_logger.log_queue_enter(
                self.patient_id, stage_name, priority=is_priority
            )
        queue_join = self.env.now
        request_kwargs = {}
        if service_duration_days is not None:
            request_kwargs["service_duration_days"] = service_duration_days
        yield resource.request(priority=is_priority, **request_kwargs)
        enter_label = self.STAGE_ENTER_LABELS.get(stage_name, stage_name.upper())
        trace(
            f"{self._get_timestamp()} >> Patient {self.patient_id} "
            f"officially ENTERED {enter_label} stage."
        )
        self.auditor.record_wait(
            stage_name,
            self.env.now - queue_join,
            now=self.env.now,
            referral_in_collection=self.collect_stats,
        )
        resource_id = 1
        if self.event_logger:
            resource_id = self.event_logger.log_appointment_start(
                self.patient_id, stage_name
            )
        return resource_id

    def _clinical_stage(self, stage_name, resource, priority_dist, time_dist):
        """
        Queue, receive service, and complete one capacity-constrained stage.

        Parameters
        ----------
        stage_name : str
            Clinical stage key for audit and logging.
        resource
            Stage resource (`WorkforceHoursResource`).
        priority_dist
            Bernoulli distribution for priority queue assignment.
        time_dist
            Duration distribution sampled once per visit.

        Yields
        ------
        simpy events
            Resource grant and service timeout events.
        """
        duration = time_dist.sample()
        wait_kwargs = {}
        if getattr(resource, "uses_workforce_hours", False):
            wait_kwargs["service_duration_days"] = duration
        rid = yield from self._wait_for_slot(
            stage_name, resource, priority_dist, **wait_kwargs
        )
        yield from self._complete_service(stage_name, rid, duration, resource=resource)

    def _complete_service(self, stage_name, resource_id, duration, resource=None):
        yield self.env.timeout(duration)
        if resource is not None and hasattr(resource, "notify_service_complete"):
            resource.notify_service_complete()
        if self.event_logger:
            self.event_logger.log_appointment_complete(
                self.patient_id, stage_name, resource_id
            )

# --- Branching gates ---
    def _diagnostic_outcome(self, referral_start_time) -> bool:
        """
        Apply final diagnostic decision (non-capacity stage).

        Parameters
        ----------
        referral_start_time : float
            Simulation time when the patient was referred.

        Returns
        -------
        bool
            ``True`` if diagnosis confirmed and pathway continues;
            ``False`` if patient exits as non-diagnosis at outcome.
        """
        self._inc("ARRIVED_DIAGNOSTIC_OUTCOME")
        self._transition("diagnostic_outcome")
        if self.system.non_diag_at_outcome_dist.sample() == 1:
            self._inc("EXIT_OUTCOME_NON_DIAGNOSIS")
            self._inc("EXIT_TOTAL")
            self._exit_pathway("outcome_non_diagnosis")
            return False
        self._inc("FLOW_DIAGNOSIS_CONFIRMED")
        self.auditor.record_rtt(
            "diagnosis",
            self.env.now - referral_start_time,
            now=self.env.now,
            referral_in_collection=self.collect_stats,
        )
        return True

    def _deliver_post_diag_support(self, clinical: bool, first_visit: bool):
        """
        Deliver one post-diagnostic support appointment (clinical or other).

        Parameters
        ----------
        clinical : bool
            Route to clinical vs non-clinical resource.
        first_visit : bool
            If ``True``, increment initial service counter; else revisit counter.

        Yields
        ------
        simpy events
        """
        if clinical:
            stage_name = "post_diag_clinical"
            resource = self.system.post_diag_clinical_resource
            priority_dist = self.system.post_diag_clinical_priority_dist
            time_dist = self.system.post_diag_clinical_time_dist
        else:
            stage_name = "post_diag_other"
            resource = self.system.post_diag_other_resource
            priority_dist = self.system.post_diag_other_priority_dist
            time_dist = self.system.post_diag_other_time_dist
        yield from self._clinical_stage(stage_name, resource, priority_dist, time_dist)
        if first_visit:
            if clinical:
                self._inc("SERVICE_POST_DIAG_CLINICAL_COMPLETED")
            else:
                self._inc("SERVICE_POST_DIAG_OTHER_COMPLETED")
            rtt_metric = "post_diag_clinical" if clinical else "post_diag_other"
            self.auditor.record_rtt(
                rtt_metric,
                self.env.now - self._referral_start_time,
                now=self.env.now,
                referral_in_collection=self.collect_stats,
            )
        else:
            self._inc("FLOW_POST_DIAG_SUPPORT_REVISIT")

# --- Post-diagnostic loop ---
    def _review_and_support_loop(self, post_diag_clinical: bool) -> None:
        """
        Run review appointments until formal discharge or self-removal.

        On ``continue`` outcome, return to the same post-diagnostic support
        stage. Loop capped at ``MAX_REVIEW_LOOPS`` (forced formal discharge).

        Parameters
        ----------
        post_diag_clinical : bool
            ``True`` if patient is on the clinical post-diagnostic pathway.

        Yields
        ------
        simpy events
            Review and optional post-diagnostic support stages.
        """
        loops = 0
        while loops < MAX_REVIEW_LOOPS:
            loops += 1
            yield from self._clinical_stage(
                "review",
                self.system.review_resource,
                self.system.review_priority_dist,
                self.system.review_time_dist,
            )
            self._inc("SERVICE_REVIEW_COMPLETED")
            self._inc("FLOW_REVIEW_VISITS")
            if loops == 1:
                self.auditor.record_rtt(
                    "review",
                    self.env.now - self._referral_start_time,
                    now=self.env.now,
                    referral_in_collection=self.collect_stats,
                )

            outcome = self.system.review_outcome_dist.sample()
            if outcome == "continue":
                self._inc("FLOW_REVIEW_CONTINUE_SUPPORT")
                yield from self._deliver_post_diag_support(post_diag_clinical, first_visit=False)
                continue
            if outcome == "formal_discharge":
                self._inc("EXIT_FORMAL_DISCHARGE")
                self._exit_pathway("formal_discharge")
                self._complete_pathway()
                return
            self._inc("EXIT_SELF_REMOVED")
            self._exit_pathway("self_removed")
            self._complete_pathway()
            return

        self._inc("EXIT_FORMAL_DISCHARGE")
        self._exit_pathway("formal_discharge")
        self._complete_pathway()

# --- Main pathway process ---
    def process(self):
        """
        SimPy generator — full pathway from referral to discharge.

        Sets ``collect_stats`` from collection window at referral time.

        Yields
        ------
        simpy events
            Inter-arrival delays, resource waits, and service timeouts.

        Notes
        -----
        See ``docs/pathway_stages.md`` for stage order, branching probabilities,
        and exit reasons. Collection-cohort flow counters use ``collect_stats``.
        """
        referral_start_time = self.env.now
        self._referral_start_time = referral_start_time
        self.collect_stats = (
            self.system.collection_start <= self.env.now < self.system.arrival_stop
        )
        self._inc("ARRIVED_TOTAL")
        self._inc("ARRIVED_REFERRAL")
        if self.event_logger:
            self.event_logger.log_patient_arrival(self.patient_id)
        trace(f"{self._get_timestamp()} Patient {self.patient_id} entered system. Referral submitted.")

        if self.system.referral_reject_dist.sample() == 1:
            self._inc("EXIT_REFERRAL_REJECTED")
            self._inc("EXIT_TOTAL")
            self._exit_pathway("referral_rejected")
            return
        self._inc("FLOW_REFERRAL_ACCEPTED")
        self._transition("screening")

        self._inc("ARRIVED_SCREENING")
        yield from self._clinical_stage(
            "screening",
            self.system.screening_resource,
            self.system.screening_priority_dist,
            self.system.screening_time_dist,
        )
        self._inc("SERVICE_SCREENING_COMPLETED")
        self.auditor.record_rtt(
            "screening",
            self.env.now - referral_start_time,
            now=self.env.now,
            referral_in_collection=self.collect_stats,
        )
        if self.system.screening_discharge_dist.sample() == 1:
            self._inc("EXIT_SCREENING_DISCHARGED")
            self._inc("EXIT_TOTAL")
            self._exit_pathway("screening_discharged")
            return
        self._inc("FLOW_SCREENING_PASSED")

        self._inc("ARRIVED_PRE_ASSESS")
        yield from self._clinical_stage(
            "pre_assessment",
            self.system.pre_assessment_resource,
            self.system.pre_assessment_priority_dist,
            self.system.pre_ass_time_dist,
        )
        self._inc("SERVICE_PRE_ASSESS_COMPLETED")
        self.auditor.record_rtt(
            "pre_assessment",
            self.env.now - referral_start_time,
            now=self.env.now,
            referral_in_collection=self.collect_stats,
        )
        if self.system.pre_ass_reject_dist.sample() == 1:
            self._inc("EXIT_PRE_ASSESS_REJECTED")
            self._inc("EXIT_TOTAL")
            self._exit_pathway("pre_assessment_rejected")
            return
        self._inc("FLOW_PRE_ASSESS_PASSED")

        self._inc("ARRIVED_ASSESSMENT")
        yield from self._clinical_stage(
            "assessment",
            self.system.assessment_resource,
            self.system.assessment_priority_dist,
            self.system.assessment_time_dist,
        )
        self._inc("SERVICE_ASSESSMENT_COMPLETED")
        self.auditor.record_rtt(
            "assessment",
            self.env.now - referral_start_time,
            now=self.env.now,
            referral_in_collection=self.collect_stats,
        )
        if self.system.non_diag_at_assessment_dist.sample() == 1:
            self._inc("EXIT_ASSESSMENT_NON_DIAGNOSIS")
            self._inc("EXIT_TOTAL")
            self._exit_pathway("assessment_non_diagnosis")
            return
        self._inc("FLOW_ASSESSMENT_PASSED")

        if self.system.needs_further_assessment_dist.sample() == 1:
            self._inc("FLOW_NEEDS_FURTHER_ASSESSMENT")
            self._inc("ARRIVED_FURTHER_ASSESS")
            yield from self._clinical_stage(
                "further_assessment",
                self.system.further_assessment_resource,
                self.system.further_assessment_priority_dist,
                self.system.further_assessment_time_dist,
            )
            self._inc("SERVICE_FURTHER_ASSESS_COMPLETED")
            self.auditor.record_rtt(
                "further_assessment",
                self.env.now - referral_start_time,
                now=self.env.now,
                referral_in_collection=self.collect_stats,
            )
            if self.system.non_diag_at_further_assessment_dist.sample() == 1:
                self._inc("EXIT_FURTHER_NON_DIAGNOSIS")
                self._inc("EXIT_TOTAL")
                self._exit_pathway("further_non_diagnosis")
                return
            self._inc("FLOW_FURTHER_ASSESS_PASSED")
        else:
            self._inc("FLOW_FURTHER_ASSESS_SKIPPED")

        if not self._diagnostic_outcome(referral_start_time):
            return

        post_diag_clinical = self.system.post_diag_clinical_dist.sample() == 1
        if post_diag_clinical:
            self._inc("FLOW_POST_DIAG_CLINICAL_ACCEPTED")
        else:
            self._inc("FLOW_POST_DIAG_OTHER_ACCEPTED")
        yield from self._deliver_post_diag_support(post_diag_clinical, first_visit=True)

        yield from self._review_and_support_loop(post_diag_clinical)
