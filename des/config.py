"""Global model parameters and default simulation horizons.

This module defines baseline NHS pathway configuration used when
:class:`~des.experiment.Experiment` and :class:`~des.audit.Audit` are
constructed without explicit overrides.  Run-specific horizons (**T\\***,
decay windows) are set in :mod:`des.runners` or the Streamlit app, not here.

Attributes
----------
WARM_UP_PERIOD, WARMUP_DAYS : float
    Default warm-up length (days) before KPI collection.
DEFAULT_RESULTS_COLLECTION_PERIOD, COLLECTION_DAYS : float
    Default KPI collection window length (days).
IAT_WEEKDAY : float
    Mean inter-arrival time between referrals (weekday exponential).
REFERRALS_PER_DAY : float
    Implied mean referrals per calendar day from ``IAT_WEEKDAY``.
PCT_REFERRAL_REJECTED, PCT_ADMIN_REMOVAL : float
    Triage and admin-removal probabilities.
PCT_DIAGNOSIS, PCT_VIRTUAL_SUPPORT : float
    Post-assessment branching probabilities.
WORKFORCE_HOURS_PER_DAY : float
    Clinician hours released each simulated weekday (shared pool).
WORKSHOP_GROUP_SIZE, WORKSHOP_NUM_SESSIONS, WORKSHOP_MAX_WAIT_DAYS : int/float
    Workshop programme rules.
SCENARIO_PRESETS : dict
    Named ``Experiment`` overrides (e.g. ``high_demand``, ``low_capacity``).
TRACE : bool
    Initial state for :mod:`des.trace` (usually ``False``).
"""

from __future__ import annotations

TRACE = False

REFERRALS_PER_DAY = 1.89

# Model parameters — simulation time horizons (calendar days, all 7 days of the week)
#   warm-up period              — system runs, KPIs are NOT collected
#   results collection period   — KPIs collected after warm-up
# Matching period T* and policy decay horizons are set in :mod:`des.runners` or the UI.
WARM_UP_PERIOD = 365 * 3
DEFAULT_RESULTS_COLLECTION_PERIOD = 365 * 5

# Backward-compatible aliases used by Audit defaults
WARMUP_DAYS = WARM_UP_PERIOD
COLLECTION_DAYS = DEFAULT_RESULTS_COLLECTION_PERIOD

IAT_WEEKDAY = 1 / REFERRALS_PER_DAY

PCT_REFERRAL_REJECTED = 0.369
PCT_ADMIN_REMOVAL = 0.05

ASSESSMENT_APPOINTMENT_COUNTS = [2, 3, 4, 5, 6]
ASSESSMENT_APPOINTMENT_PROBS = [0.435, 0.261, 0.174, 0.087, 0.043]
ASSESSMENT_GAP_DAYS = 7

DURATION_ASSESSMENT = [2.0, 2.5, 3.0]
DURATION_WORKSHOP_SESSION = [1.5, 2.0, 2.5]

PCT_DIAGNOSIS = 0.75
PCT_VIRTUAL_SUPPORT = 0.30

WORKSHOP_GROUP_SIZE = 8
WORKSHOP_NUM_SESSIONS = 6
WORKSHOP_SESSION_INTERVAL_WEEKS = 1
WORKSHOP_MAX_WAIT_DAYS = 28

# One shared weekday pool for assessment and post-diagnosis clinical support.
WORKFORCE_HOURS_PER_DAY = 7
WORKFORCE_HOURS_WORKSHOP_SESSION = 2.0
CALIBRATED_WORKFORCE_HOURS_PER_DAY = 4.33

N_STREAMS = 15
DEFAULT_RND_SET = 42

SCENARIO_PRESETS: dict[str, dict[str, float]] = {
    "high_demand": {
        "iat": IAT_WEEKDAY / 1.25,
        "workforce_hours_per_day": WORKFORCE_HOURS_PER_DAY,
    },
    "low_demand": {
        "iat": IAT_WEEKDAY * 1.25,
        "workforce_hours_per_day": WORKFORCE_HOURS_PER_DAY,
    },
    "high_capacity": {
        "iat": IAT_WEEKDAY,
        "workforce_hours_per_day": WORKFORCE_HOURS_PER_DAY * 1.25,
    },
    "low_capacity": {
        "iat": IAT_WEEKDAY,
        "workforce_hours_per_day": CALIBRATED_WORKFORCE_HOURS_PER_DAY,
    },
}
