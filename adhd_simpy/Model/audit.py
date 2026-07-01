"""KPI audit collector."""

import numpy as np

class Audit:
    """
    Collect pathway KPIs with explicit collection-cohort filtering.

    Primary RTT and wait metrics include only patients whose **referral** falls
    in the collection window (``referral_in_collection=True``). Legacy stores
    retain warm-up referral completions for audit comparison. Queue snapshots
    are taken during the collection window only
    (``collection_start <= now < collection_end``).

    Attributes
    ----------
    STAGE_NAMES : list of str
        Capacity-constrained clinical stages tracked for wait and queue KPIs.
    RTT_METRICS : list of str
        Referral-to-milestone RTT keys (includes ``diagnosis`` at outcome).

    Notes
    -----
    Primary KPIs are exposed as ``ACCESS_*`` keys from :meth:`summarize`.
    ``*_LEGACY`` and ``FLOW_WARMUP_REFERRAL_*`` support forensic audit.
    """

    STAGE_NAMES = [
        "screening",
        "pre_assessment",
        "assessment",
        "further_assessment",
        "post_diag_clinical",
        "post_diag_other",
        "review",
    ]

    def __init__(self):
        """Initialise empty KPI stores via :meth:`reset`."""
        self.reset()

# --- RTT and wait recording ---
    RTT_METRICS = [
        "screening",
        "pre_assessment",
        "assessment",
        "further_assessment",
        "diagnosis",
        "post_diag_clinical",
        "post_diag_other",
        "review",
    ]

    def reset(self):
        """
        Clear all RTT, wait, queue, and resource statistic stores.

        Resets ``collection_start`` to 0 and ``collection_end`` to infinity until
        set by :func:`single_run`.
        """
        self.collection_start = 0.0
        self.collection_end = float("inf")
        self.rtt_days = {k: [] for k in self.RTT_METRICS}
        self.rtt_days_legacy = {k: [] for k in self.RTT_METRICS}
        self.wait_days = {stage: [] for stage in self.STAGE_NAMES}
        self.wait_days_legacy = {stage: [] for stage in self.STAGE_NAMES}
        self.warmup_referral_rtt_completions = {k: 0 for k in self.RTT_METRICS}
        self.warmup_referral_wait_events = {stage: 0 for stage in self.STAGE_NAMES}
        self.queue_lengths = {stage: [] for stage in self.STAGE_NAMES}
        self.resource_stats = {}

    def _event_in_collection_window(self, now):
        """Event occurred after warm-up; Cohort patients may still complete pathway stages during the drain phase."""
        return now >= self.collection_start

    def _snapshot_in_collection_window(self, now):
        """Queue snapshots during the formal collection (arrival) window only."""
        return self.collection_start <= now < self.collection_end

    def record_rtt(self, metric_name, value_days, now=None, referral_in_collection=True):
        """
        Record referral-to-milestone RTT for a completing patient.

        Parameters
        ----------
        metric_name : str
            Key in :attr:`RTT_METRICS` (e.g. ``"diagnosis"``).
        value_days : float
            Elapsed simulation days since referral.
        now : float, optional
            Event time; events before ``collection_start`` are ignored.
        referral_in_collection : bool, default True
            If ``False``, increment warm-up referral completion counter instead
            of the primary cohort store.
        """
        if metric_name not in self.rtt_days:
            return
        if now is not None and not self._event_in_collection_window(now):
            return
        value = float(value_days)
        self.rtt_days_legacy[metric_name].append(value)
        if referral_in_collection:
            self.rtt_days[metric_name].append(value)
        else:
            self.warmup_referral_rtt_completions[metric_name] += 1

    def record_wait(self, stage_name, value_days, now=None, referral_in_collection=True):
        """
        Record queue wait time at resource grant for a clinical stage.

        Parameters
        ----------
        stage_name : str
            Stage key in :attr:`STAGE_NAMES`.
        value_days : float
            Time spent waiting in queue before service starts.
        now : float, optional
            Grant time; events before ``collection_start`` are ignored.
        referral_in_collection : bool, default True
            Cohort filter for primary vs warm-up referral accounting.
        """
        if stage_name not in self.wait_days:
            return
        if now is not None and not self._event_in_collection_window(now):
            return
        value = float(value_days)
        self.wait_days_legacy[stage_name].append(value)
        if referral_in_collection:
            self.wait_days[stage_name].append(value)
        else:
            self.warmup_referral_wait_events[stage_name] += 1

    def record_queue_length(self, stage_name, queue_length, now=None):
        """
        Append a daily queue-length snapshot for a stage.

        Parameters
        ----------
        stage_name : str
            Stage key in :attr:`STAGE_NAMES`.
        queue_length : int or float
            Current waiting-list depth.
        now : float, optional
            Snapshot time; recorded only if inside the collection window.
        """
        if stage_name in self.queue_lengths and (now is None or self._snapshot_in_collection_window(now)):
            self.queue_lengths[stage_name].append(float(queue_length))

# --- Resource utilisation ---
    def capture_resource_stats(self, stage_name, resource):
        """
        Store end-of-run utilisation summary from a stage resource.

        Parameters
        ----------
        stage_name : str
            Clinical stage identifier.
        resource
            Resource instance exposing :meth:`get_summary`.
        """
        summary = resource.get_summary()
        self.resource_stats[stage_name] = {
            "utilisation": float(summary.get("utilisation_pct", 0)) / 100.0,
            "slots_used": float(summary.get("collection_used_slots", 0)),
            "slots_released": float(summary.get("collection_released_slots", 0)),
            "full_run_utilisation": float(summary.get("full_run_utilisation_pct", 0)) / 100.0,
            "max_queue_length": float(summary.get("max_queue_length", 0)),
            "queue_backlog": float(summary.get("queue_backlog", 0)),
            "workforce_hours_per_day": float(summary.get("workforce_hours_per_day", 0)),
            "derived_slots_per_day": float(summary.get("derived_slots_per_day", 0)),
        }

# --- KPI aggregation ---
    def summarize(self, flow_results, run_length):
        """
        Aggregate primary and legacy KPIs from collected observations.

        Parameters
        ----------
        flow_results : dict
            Flow counters from ``Experiment.results`` (e.g. ``FLOW_DIAGNOSIS_CONFIRMED``).
        run_length : int or float
            Collection window length in days (metadata; unused in aggregation).

        Returns
        -------
        dict
            KPI dictionary with ``ACCESS_*``, ``QUEUE_*``, ``CAPACITY_*``,
            sample counts, and warm-up referral completion tallies.
        """
        resource_stats = list(self.resource_stats.values())
        total_slots_used = sum(stat.get("slots_used", 0) for stat in resource_stats)
        total_slots_released = sum(stat.get("slots_released", 0) for stat in resource_stats)
        queue_backlog_total = sum(stat.get("queue_backlog", 0) for stat in resource_stats)
        in_system_end = float(flow_results.get("IN_SYSTEM_END", 0))
        cohort_drain_complete = bool(flow_results.get("COHORT_DRAIN_COMPLETE", False))
        cohort_rtt_valid = cohort_drain_complete and in_system_end == 0 and queue_backlog_total == 0
        system_utilization = (
            (total_slots_used / total_slots_released * 100) if total_slots_released > 0 else 0.0
        )

        def get_mean(store, stage):
            data = store.get(stage, [])
            return float(np.mean(data)) if data else 0.0

        def get_percentile(store, stage, pct):
            data = store.get(stage, [])
            return float(np.percentile(data, pct)) if data else 0.0

        summary = {
            "ACCESS_REFERRAL_TO_SCREENING_RTT_DAYS": get_mean(self.rtt_days, "screening"),
            "ACCESS_REFERRAL_TO_PRE_ASSESSMENT_RTT_DAYS": get_mean(self.rtt_days, "pre_assessment"),
            "ACCESS_REFERRAL_TO_ASSESSMENT_RTT_DAYS": get_mean(self.rtt_days, "assessment"),
            "ACCESS_REFERRAL_TO_FURTHER_ASSESSMENT_RTT_DAYS": get_mean(self.rtt_days, "further_assessment"),
            "ACCESS_REFERRAL_TO_DIAGNOSIS_RTT_DAYS": get_mean(self.rtt_days, "diagnosis"),
            "ACCESS_REFERRAL_TO_POST_DIAG_CLINICAL_RTT_DAYS": get_mean(
                self.rtt_days, "post_diag_clinical"
            ),
            "ACCESS_REFERRAL_TO_POST_DIAG_OTHER_RTT_DAYS": get_mean(
                self.rtt_days, "post_diag_other"
            ),
            "ACCESS_REFERRAL_TO_REVIEW_RTT_DAYS": get_mean(self.rtt_days, "review"),
            "ACCESS_REFERRAL_TO_DIAGNOSIS_RTT_DAYS_MEDIAN": get_percentile(
                self.rtt_days, "diagnosis", 50
            ),
            "ACCESS_REFERRAL_TO_DIAGNOSIS_RTT_DAYS_P90": get_percentile(
                self.rtt_days, "diagnosis", 90
            ),
            "ACCESS_SCREENING_WAIT_DAYS": get_mean(self.wait_days, "screening"),
            "ACCESS_PRE_ASSESSMENT_WAIT_DAYS": get_mean(self.wait_days, "pre_assessment"),
            "ACCESS_ASSESSMENT_WAIT_DAYS": get_mean(self.wait_days, "assessment"),
            "ACCESS_ASSESSMENT_WAIT_DAYS_MEDIAN": get_percentile(self.wait_days, "assessment", 50),
            "ACCESS_ASSESSMENT_WAIT_DAYS_P90": get_percentile(self.wait_days, "assessment", 90),
            "ACCESS_FURTHER_ASSESSMENT_WAIT_DAYS": get_mean(self.wait_days, "further_assessment"),
            "ACCESS_REFERRAL_TO_SCREENING_RTT_DAYS_LEGACY": get_mean(self.rtt_days_legacy, "screening"),
            "ACCESS_REFERRAL_TO_PRE_ASSESSMENT_RTT_DAYS_LEGACY": get_mean(self.rtt_days_legacy, "pre_assessment"),
            "ACCESS_REFERRAL_TO_ASSESSMENT_RTT_DAYS_LEGACY": get_mean(self.rtt_days_legacy, "assessment"),
            "ACCESS_REFERRAL_TO_FURTHER_ASSESSMENT_RTT_DAYS_LEGACY": get_mean(self.rtt_days_legacy, "further_assessment"),
            "ACCESS_REFERRAL_TO_DIAGNOSIS_RTT_DAYS_LEGACY": get_mean(self.rtt_days_legacy, "diagnosis"),
            "ACCESS_REFERRAL_TO_POST_DIAG_CLINICAL_RTT_DAYS_LEGACY": get_mean(
                self.rtt_days_legacy, "post_diag_clinical"
            ),
            "ACCESS_REFERRAL_TO_POST_DIAG_OTHER_RTT_DAYS_LEGACY": get_mean(
                self.rtt_days_legacy, "post_diag_other"
            ),
            "ACCESS_REFERRAL_TO_REVIEW_RTT_DAYS_LEGACY": get_mean(self.rtt_days_legacy, "review"),
            "ACCESS_SCREENING_WAIT_DAYS_LEGACY": get_mean(self.wait_days_legacy, "screening"),
            "ACCESS_PRE_ASSESSMENT_WAIT_DAYS_LEGACY": get_mean(self.wait_days_legacy, "pre_assessment"),
            "ACCESS_ASSESSMENT_WAIT_DAYS_LEGACY": get_mean(self.wait_days_legacy, "assessment"),
            "ACCESS_FURTHER_ASSESSMENT_WAIT_DAYS_LEGACY": get_mean(self.wait_days_legacy, "further_assessment"),
            "QUEUE_TOTAL_BACKLOG": float(queue_backlog_total),
            "COHORT_DRAIN_COMPLETE": cohort_drain_complete,
            "COHORT_RTT_VALID": cohort_rtt_valid,
            "CAPACITY_TOTAL_SLOT_USAGE": float(total_slots_used),
            "CAPACITY_TOTAL_SLOT_RELEASED": float(total_slots_released),
            "OVERALL_SYSTEM_UTILISATION": float(system_utilization),
            "FLOW_DIAGNOSIS_RATE_PCT": (
                100.0 * flow_results.get("FLOW_DIAGNOSIS_CONFIRMED", 0)
                / max(flow_results.get("ARRIVED_TOTAL", 1), 1)
            ),
        }

        for metric in self.RTT_METRICS:
            key = metric.upper()
            summary[f"KPI_SAMPLE_N_RTT_{key}"] = len(self.rtt_days.get(metric, []))

        peak_queues = []
        for stage in self.STAGE_NAMES:
            queue_values = self.queue_lengths.get(stage, [])
            stat = self.resource_stats.get(stage, {})
            peak = float(stat.get("max_queue_length", 0))
            peak_queues.append(peak)
            summary[f"QUEUE_MEAN_{stage.upper()}"] = float(np.mean(queue_values)) if queue_values else 0.0
            summary[f"QUEUE_PEAK_{stage.upper()}"] = peak
            summary[f"QUEUE_BACKLOG_{stage.upper()}"] = float(stat.get("queue_backlog", 0))
            summary[f"CAPACITY_UTILISATION_{stage.upper()}"] = stat.get("utilisation", 0.0)
            summary[f"DERIVED_SLOTS_{stage.upper()}"] = stat.get("derived_slots_per_day", 0.0)

        summary["QUEUE_PEAK_ANY_STAGE"] = float(max(peak_queues)) if peak_queues else 0.0

        n_days = max(
            (len(self.queue_lengths[s]) for s in self.STAGE_NAMES if self.queue_lengths[s]),
            default=0,
        )
        daily_totals = []
        for day_idx in range(n_days):
            daily_totals.append(
                sum(
                    self.queue_lengths[s][day_idx]
                    for s in self.STAGE_NAMES
                    if day_idx < len(self.queue_lengths[s])
                )
            )
        summary["QUEUE_MEAN_TOTAL"] = float(np.mean(daily_totals)) if daily_totals else 0.0

        for metric in self.RTT_METRICS:
            key = metric.upper()
            summary[f"KPI_SAMPLE_N_RTT_{key}"] = len(self.rtt_days.get(metric, []))
            summary[f"KPI_SAMPLE_N_RTT_{key}_LEGACY"] = len(self.rtt_days_legacy.get(metric, []))
            summary[f"FLOW_WARMUP_REFERRAL_RTT_{key}"] = int(
                self.warmup_referral_rtt_completions.get(metric, 0)
            )

        for stage in self.STAGE_NAMES:
            key = stage.upper()
            summary[f"KPI_SAMPLE_N_WAIT_{key}"] = len(self.wait_days.get(stage, []))
            summary[f"FLOW_WARMUP_REFERRAL_WAIT_{key}"] = int(
                self.warmup_referral_wait_events.get(stage, 0)
            )

        return summary

