"""Global model parameters and default simulation horizons.

Constants in this module define the baseline NHS pathway configuration used
by :class:`~des.experiment.Experiment` and :class:`~des.audit.Audit` when no
override is supplied.  Run-specific horizons (T*, decay windows) are set in
the runners or UI rather than here.
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
