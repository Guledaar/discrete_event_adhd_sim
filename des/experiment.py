"""Scenario configuration, RNG streams, and distribution objects.

See :class:`Experiment` for the public API. Distributions are constructed in
:meth:`Experiment.init_sampling` and re-seeded via :meth:`Experiment.set_random_no_set`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
from des.distributions import Bernoulli, Discrete, Exponential, Triangular

from des.audit import Audit
from des.collection_window import SimulationPhases
from des.config import (
    ASSESSMENT_APPOINTMENT_COUNTS,
    ASSESSMENT_APPOINTMENT_PROBS,
    ASSESSMENT_GAP_DAYS,
    DEFAULT_RND_SET,
    DURATION_ASSESSMENT,
    DURATION_WORKSHOP_SESSION,
    IAT_WEEKDAY,
    N_STREAMS,
    PCT_ADMIN_REMOVAL,
    PCT_DIAGNOSIS,
    PCT_REFERRAL_REJECTED,
    PCT_VIRTUAL_SUPPORT,
    WORKFORCE_HOURS_PER_DAY,
    WORKFORCE_HOURS_WORKSHOP_SESSION,
    WORKSHOP_GROUP_SIZE,
    WORKSHOP_MAX_WAIT_DAYS,
    WORKSHOP_NUM_SESSIONS,
    WORKSHOP_SESSION_INTERVAL_WEEKS,
)


class Experiment:
    """
    Scenario configuration, RNG streams, and sampled distribution objects.

    An ``Experiment`` bundles all model parameters for one scenario run
    (or replication) and owns the :class:`~des.audit.Audit` that collects
    patient state during the simulation.  Distribution objects are
    re-created whenever the random seed changes via :meth:`init_sampling`.

    Parameters
    ----------
    audit : Audit, optional
        Pre-constructed audit object.  A new :class:`~des.audit.Audit` is
        created when ``None`` (default).
    random_number_set : int, optional
        Base seed for the RNG stream generator.  Default
        :data:`~des.config.DEFAULT_RND_SET`.
    n_streams : int, optional
        Number of independent RNG streams to generate.
        Default :data:`~des.config.N_STREAMS`.
    use_fixed_seed : bool, optional
        When ``True`` (default) seeds are deterministic; ``False`` gives
        non-reproducible runs.
    iat : float, optional
        Mean inter-arrival time in days.  Default
        :data:`~des.config.IAT_WEEKDAY`.
    scenario_name : str, optional
        Human-readable scenario label.  Default ``'baseline'``.
    **kwargs : Any
        Optional overrides for any model parameter (e.g.
        ``pct_diagnosis``, ``workforce_hours_per_day``).  Unknown keys are
        silently ignored.
    """

    def __init__(
        self,
        audit: Optional[Audit] = None,
        random_number_set: int = DEFAULT_RND_SET,
        n_streams: int = N_STREAMS,
        use_fixed_seed: bool = True,
        iat: float = IAT_WEEKDAY,
        scenario_name: str = "baseline",
        **kwargs: Any,
    ) -> None:
        """
        Initialise scenario parameters and build seeded distribution objects.

        See the class docstring ``Parameters`` section for argument definitions.
        """
        self.audit = audit or Audit()
        self.last_result = None
        self.last_export_paths: Dict[str, str] = {}
        self.warmup_days: Optional[float] = None
        self.collection_days: Optional[float] = None
        self.run_length: Optional[float] = None
        self.scenario_name = scenario_name
        self.random_number_set = random_number_set
        self.base_random_number_set = random_number_set
        self.n_streams = n_streams
        self.use_fixed_seed = use_fixed_seed
        self.iat = iat

        self.pct_referral_rejected = kwargs.get("pct_referral_rejected", PCT_REFERRAL_REJECTED)
        self.pct_admin_removal = kwargs.get("pct_admin_removal", PCT_ADMIN_REMOVAL)
        self.pct_diagnosis = kwargs.get("pct_diagnosis", PCT_DIAGNOSIS)
        self.pct_virtual_support = kwargs.get("pct_virtual_support", PCT_VIRTUAL_SUPPORT)

        self.assessment_appointment_counts = kwargs.get(
            "assessment_appointment_counts", ASSESSMENT_APPOINTMENT_COUNTS
        )
        self.assessment_appointment_probs = kwargs.get(
            "assessment_appointment_probs", ASSESSMENT_APPOINTMENT_PROBS
        )
        self.assessment_gap_days = kwargs.get("assessment_gap_days", ASSESSMENT_GAP_DAYS)
        self.duration_assessment = kwargs.get("duration_assessment", DURATION_ASSESSMENT)

        self.workshop_group_size = kwargs.get("workshop_group_size", WORKSHOP_GROUP_SIZE)
        self.workshop_num_sessions = kwargs.get("workshop_num_sessions", WORKSHOP_NUM_SESSIONS)
        self.workshop_session_interval_weeks = kwargs.get(
            "workshop_session_interval_weeks", WORKSHOP_SESSION_INTERVAL_WEEKS
        )
        self.workshop_max_wait_days = kwargs.get(
            "workshop_max_wait_days", WORKSHOP_MAX_WAIT_DAYS
        )
        self.duration_workshop_session = kwargs.get(
            "duration_workshop_session", DURATION_WORKSHOP_SESSION
        )
        self.workforce_hours_workshop_session = kwargs.get(
            "workforce_hours_workshop_session", WORKFORCE_HOURS_WORKSHOP_SESSION
        )
        self.workforce_hours_per_day = kwargs.get(
            "workforce_hours_per_day",
            WORKFORCE_HOURS_PER_DAY,
        )
        if "workforce_hours_assessment" in kwargs and "workforce_hours_per_day" not in kwargs:
            self.workforce_hours_per_day = kwargs["workforce_hours_assessment"]
        # Single shared pool: assessment and post-diagnosis clinical support.
        self.workforce_hours_assessment = self.workforce_hours_per_day

        # Policy-switch state (Run 3 continuous branching)
        self.phase: str = "baseline"
        self.phases: Optional[SimulationPhases] = None
        self.switch_time: Optional[float] = None
        self._intervention_overrides: Dict[str, Any] = {}

        self.init_sampling()

    def configure_intervention(self, overrides: Dict[str, Any]) -> None:
        """
        Register parameter overrides to be applied at switch time in Run 3.

        The overrides are stored but not applied until :meth:`activate_intervention`
        is called at simulation time ``T*``.

        Parameters
        ----------
        overrides : dict[str, Any]
            Mapping of attribute name to new value (e.g.
            ``{'workforce_hours_per_day': 10.0}``).
        """
        self._intervention_overrides = dict(overrides)

    def activate_intervention(self, now: float) -> None:
        """
        Apply intervention overrides at simulation time *now* without resetting state.

        The method is a no-op when called before ``switch_time`` or when the
        experiment is already in the ``'intervention'`` phase.  After activation
        the phase is set to ``'intervention'`` and :meth:`init_sampling` is
        called so distribution objects reflect any updated parameters.

        Parameters
        ----------
        now : float
            Current simulation time (days).  Overrides are only applied when
            ``now >= switch_time``.
        """
        if self.switch_time is None or now < self.switch_time:
            return
        if self.phase == "intervention":
            return
        self.phase = "intervention"
        for key, value in self._intervention_overrides.items():
            setattr(self, key, value)
        if "workforce_hours_per_day" in self._intervention_overrides:
            self.workforce_hours_assessment = self.workforce_hours_per_day
        self.init_sampling()

    def set_random_no_set(self, rep: int) -> None:
        """
        Advance the random seed to replication *rep* and reinitialise sampling.

        The effective seed is ``base_random_number_set + rep``, which ensures
        each replication uses independent RNG streams while remaining
        reproducible across identical runs.

        Parameters
        ----------
        rep : int
            Replication index (0-based).
        """
        self.random_number_set = self.base_random_number_set + rep
        self.init_sampling()

    def init_sampling(self) -> None:
        """
        (Re-)create all distribution objects from the current seed state.

        Uses a hierarchical SeedSequence to derive independent child seeds for
        each RNG stream, then constructs one distribution object per stream.
        Called automatically by ``__init__``, :meth:`set_random_no_set`, and
        :meth:`activate_intervention`.
        """
        int_seeds: List[Optional[int]] = [None] * self.n_streams
        if self.use_fixed_seed:
            master_seq = np.random.SeedSequence(self.random_number_set)
            child_seqs = master_seq.spawn(self.n_streams)
            for i in range(self.n_streams):
                int_seeds[i] = int(child_seqs[i].generate_state(1)[0])

        self.iat_dist = Exponential(self.iat, int_seeds[0])
        self.referral_reject_dist = Bernoulli(self.pct_referral_rejected, int_seeds[1])
        self.admin_removal_dist = Bernoulli(self.pct_admin_removal, int_seeds[2])
        self.diagnosis_dist = Bernoulli(self.pct_diagnosis, int_seeds[3])
        self.virtual_support_dist = Bernoulli(self.pct_virtual_support, int_seeds[4])
        da = list(np.array(self.duration_assessment, dtype=float))
        self.assessment_time_dist = Triangular(
            float(da[0]), float(da[1]), float(da[2]), random_seed=int_seeds[5]
        )
        dw = list(np.array(self.duration_workshop_session, dtype=float))
        self.workshop_time_dist = Triangular(
            float(dw[0]), float(dw[1]), float(dw[2]), random_seed=int_seeds[6]
        )
        self.assessment_count_dist = Discrete(
            self.assessment_appointment_counts, self.assessment_appointment_probs, int_seeds[7]
        )

    def to_kwargs(self) -> Dict[str, Any]:
        """
        Return a serialisable dict of scenario parameters for worker processes.

        The returned dict can be unpacked as ``**kwargs`` into the
        :class:`Experiment` constructor to recreate an equivalent scenario,
        which is used when spawning parallel replication workers.

        Returns
        -------
        dict[str, Any]
            Current scenario parameters (excludes ``audit`` and RNG state).
        """
        return {
            "random_number_set": self.base_random_number_set,
            "use_fixed_seed": self.use_fixed_seed,
            "iat": self.iat,
            "scenario_name": self.scenario_name,
            "pct_referral_rejected": self.pct_referral_rejected,
            "pct_admin_removal": self.pct_admin_removal,
            "pct_diagnosis": self.pct_diagnosis,
            "pct_virtual_support": self.pct_virtual_support,
            "assessment_appointment_counts": self.assessment_appointment_counts,
            "assessment_appointment_probs": self.assessment_appointment_probs,
            "assessment_gap_days": self.assessment_gap_days,
            "duration_assessment": self.duration_assessment,
            "workshop_group_size": self.workshop_group_size,
            "workshop_num_sessions": self.workshop_num_sessions,
            "workshop_session_interval_weeks": self.workshop_session_interval_weeks,
            "workshop_max_wait_days": self.workshop_max_wait_days,
            "duration_workshop_session": self.duration_workshop_session,
            "workforce_hours_workshop_session": self.workforce_hours_workshop_session,
            "workforce_hours_per_day": self.workforce_hours_per_day,
        }
