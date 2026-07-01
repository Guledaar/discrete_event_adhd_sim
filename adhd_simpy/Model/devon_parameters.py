"""Devon adult autism assessment scenario parameters (public sources).

Figures are taken from NHS Devon / DAANA published statistics and calibrated
where the service does not publish operational capacity (workforce hours).

Sources
-------
- DAANA waiting list & referral volume (Dec 2025):
  https://www.dpt.nhs.uk/service-details/service/devon-adult-autism-and-adhd-service-daana-20/
- NHS Devon ICB average wait (Jun 2025, all ages):
  https://www.dartmouth-today.co.uk/news/patients-with-suspected-autism-referral-in-devon-wait-more-than-two-years-on-average-for-assessment-824203
- NICE recommended RTT target: 13 weeks (91 days)
- CFHD first-contact wait (Dec 2025, CYP Devon): 87 weeks — context only
"""

from __future__ import annotations

from adhd_simpy.Model.audit import Audit
from adhd_simpy.Model.experiment import Experiment
from adhd_simpy.Model.parameters import (
    WORKFORCE_HOURS_ASSESSMENT,
    WORKFORCE_HOURS_FURTHER_ASSESSMENT,
    WORKFORCE_HOURS_POST_DIAG_CLINICAL,
    WORKFORCE_HOURS_POST_DIAG_OTHER,
    WORKFORCE_HOURS_PRE_ASSESSMENT,
    WORKFORCE_HOURS_REVIEW,
    WORKFORCE_HOURS_SCREENING,
)

# ── Published Devon figures ────────────────────────────────────────────────

# DAANA quarterly update (Dec 2025): 177 new autism referrals since last update (~13 weeks)
DAANA_REFERRALS_PER_QUARTER = 177
DAANA_WEEKS_PER_QUARTER = 13
DAANA_WEEKDAYS_PER_QUARTER = DAANA_WEEKS_PER_QUARTER * 5

# Derived weekday referral rate for the local NHS DAANA pathway
DEVON_REFERRALS_PER_WEEKDAY = DAANA_REFERRALS_PER_QUARTER / DAANA_WEEKDAYS_PER_QUARTER  # ≈ 2.72

# DAANA autism waiting list (Dec 2025)
DAANA_AUTISM_WAITING_LIST = 3305

# NHS Devon ICB — average wait to assessment (Jun 2025, suspected autism, all ages)
DEVON_ICB_MEAN_WAIT_MONTHS = 26  # "two years and two months"
DEVON_ICB_MEAN_WAIT_DAYS = int(DEVON_ICB_MEAN_WAIT_MONTHS * 30.44)  # ≈ 791

# NICE RTT target
NICE_RTT_TARGET_DAYS = 91  # 13 weeks

# ── Simulation scenario (published + illustrative calibration) ─────────────

# Warm-up builds a backlog consistent with a service already under pressure
DEVON_WARMUP_DAYS = 730  # 2 years

# Collection window for KPI reporting
DEVON_RUN_LENGTH = 365

# Long drain horizon — Devon-like queues clear slowly
DEVON_MAX_DRAIN_DAYS = 7300

# DAANA does not publish clinician hours; scale default model capacity so that
# referral-to-diagnosis RTT is in the same order of magnitude as the ICB statistic
# (~790 days) at DAANA referral rate. Re-calibrate if local operational data becomes available.
DEVON_CAPACITY_SCALE = 0.25

_STAGE_HOURS = {
    "workforce_hours_screening": WORKFORCE_HOURS_SCREENING,
    "workforce_hours_pre_assessment": WORKFORCE_HOURS_PRE_ASSESSMENT,
    "workforce_hours_assessment": WORKFORCE_HOURS_ASSESSMENT,
    "workforce_hours_further_assessment": WORKFORCE_HOURS_FURTHER_ASSESSMENT,
    "workforce_hours_post_diag_clinical": WORKFORCE_HOURS_POST_DIAG_CLINICAL,
    "workforce_hours_post_diag_other": WORKFORCE_HOURS_POST_DIAG_OTHER,
    "workforce_hours_review": WORKFORCE_HOURS_REVIEW,
}

DEVON_WORKFORCE_OVERRIDES = {
    k: v * DEVON_CAPACITY_SCALE for k, v in _STAGE_HOURS.items()
}

DEVON_DATA_SOURCES = {
    "referrals_per_weekday": {
        "value": round(DEVON_REFERRALS_PER_WEEKDAY, 2),
        "source": "DAANA: 177 referrals per quarterly update (Dec 2025)",
        "url": "https://www.dpt.nhs.uk/service-details/service/devon-adult-autism-and-adhd-service-daana-20/",
    },
    "waiting_list": {
        "value": DAANA_AUTISM_WAITING_LIST,
        "source": "DAANA autism waiting list (Dec 2025)",
        "url": "https://www.dpt.nhs.uk/service-details/service/devon-adult-autism-and-adhd-service-daana-20/",
    },
    "icb_mean_wait_days": {
        "value": DEVON_ICB_MEAN_WAIT_DAYS,
        "source": "NHS Devon ICB average wait Jun 2025 (all ages)",
        "url": "https://www.dartmouth-today.co.uk/news/patients-with-suspected-autism-referral-in-devon-wait-more-than-two-years-on-average-for-assessment-824203",
    },
    "capacity_scale": {
        "value": DEVON_CAPACITY_SCALE,
        "source": "Illustrative calibration — DAANA workforce hours not published",
        "url": None,
    },
}


def devon_experiment(
    auditor: Audit | None = None,
    random_number_set: int = 42,
    capacity_scale: float | None = None,
) -> Experiment:
    """Build an Experiment configured with Devon published demand and calibrated capacity."""
    auditor = auditor or Audit()
    scale = DEVON_CAPACITY_SCALE if capacity_scale is None else capacity_scale
    overrides = {k: v * scale for k, v in _STAGE_HOURS.items()}

    return Experiment(
        auditor=auditor,
        random_number_set=random_number_set,
        iat=1.0 / DEVON_REFERRALS_PER_WEEKDAY,
        **overrides,
    )


def devon_run_kwargs() -> dict:
    """Keyword arguments for single_run / multiple_runs using the Devon scenario."""
    return {
        "warmup_days": DEVON_WARMUP_DAYS,
        "run_length": DEVON_RUN_LENGTH,
        "max_drain_days": DEVON_MAX_DRAIN_DAYS,
    }
