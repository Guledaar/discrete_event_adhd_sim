"""Global model parameters."""

# ============================================================
# GLOBAL MODEL PARAMETERS
# Iteration 4 workforce-hours DES — warm-up + collection cohort
# ============================================================


TRACE = False

# ── DEMAND & SIMULATION ──
REFERRALS_PER_DAY = 5.0
WARMUP_DAYS = 730
RUN_LENGTH = 1825
MAX_DRAIN_DAYS = 3650

# ── DEMAND ──

IAT_WEEKDAY = 1 / REFERRALS_PER_DAY

# ── APPOINTMENT DURATIONS (Hours - Triangular [min, mode, max]) ──
# Reflects clinical reality where complex cases consume more time
DURATION_SCREENING = [0.5, 0.75, 1.0]
DURATION_PRE_ASSESSMENT = [0.75, 1.0, 1.5]
DURATION_ASSESSMENT = [3.0, 4.0, 6.0]
DURATION_FURTHER_ASSESSMENT = [2.0, 3.0, 4.0]
DURATION_POST_DIAG_CLINICAL = [1.0, 1.5, 2.0]
DURATION_POST_DIAG_OTHER = [1.0, 1.5, 2.0]
DURATION_REVIEW = [0.25, 0.5, 0.75]

# ── PATHWAY BRANCHING ──
PCT_REFERRAL_REJECTED = 0.20           # 20% rejected at triage (triage rigor)
PCT_SCREENING_DISCHARGED = 0.15        # 15% filter at screening
PCT_PRE_ASS_REJECTED = 0.10            # 10% filter at pre-assessment
PCT_NON_DIAGNOSIS_AT_ASSESSMENT = 0.20 # 20% non-diag
PCT_NEEDS_FURTHER_ASSESSMENT = 0.40    # 40% complexity
PCT_NON_DIAGNOSIS_AT_FURTHER_ASSESSMENT = 0.10
PCT_NON_DIAGNOSIS_AT_OUTCOME = 0.05
PCT_POST_DIAG_CLINICAL = 0.70

# ── REVIEW LOOP ──

PCT_REVIEW_CONTINUE_SUPPORT = 0.20
PCT_REVIEW_FORMAL_DISCHARGE = 0.70
PCT_REVIEW_SELF_REMOVAL = 0.10
PCT_REMOVAL_DISCHARGE = 0.90  # legacy alias when review-continue params omitted
MAX_REVIEW_LOOPS = 50

# ── WORKFORCE HOURS PER WEEKDAY ──

WORKFORCE_HOURS_SCREENING = 5.0
WORKFORCE_HOURS_PRE_ASSESSMENT = 10.0
WORKFORCE_HOURS_ASSESSMENT = 24.0
WORKFORCE_HOURS_FURTHER_ASSESSMENT = 10.0
WORKFORCE_HOURS_POST_DIAG_CLINICAL = 8.0
WORKFORCE_HOURS_POST_DIAG_OTHER = 5.0
WORKFORCE_HOURS_REVIEW = 5.0


# ── PRIORITY PERCENTAGES ──
# Prioritizing clinical need (e.g., safeguarding or crisis cases)
PCT_PRIORITY_SCREENING = 0.10
PCT_PRIORITY_PRE_ASSESSMENT = 0.10
PCT_PRIORITY_ASSESSMENT = 0.15
PCT_PRIORITY_FURTHER_ASSESSMENT = 0.15
PCT_PRIORITY_POST_DIAG_CLINICAL = 0.05
PCT_PRIORITY_POST_DIAG_OTHER = 0.05
PCT_PRIORITY_REVIEW = 0.05

# ── RANDOMNESS ──

N_STREAMS = 25
DEFAULT_RND_SET = 42
N_REP = 20


STAGE_CAPACITY_KEYS = [
    ("screening", "workforce_hours_screening", "dur_screening", "slots_screening"),
    ("pre_assessment", "workforce_hours_pre_assessment", "dur_pre_assessment", "slots_pre_assessment"),
    ("assessment", "workforce_hours_assessment", "dur_assessment", "slots_assessment"),
    ("further_assessment", "workforce_hours_further_assessment", "dur_further_assessment", "slots_further_assessment"),
    ("post_diag_clinical", "workforce_hours_post_diag_clinical", "dur_post_diag_clinical", "slots_post_diag_clinical"),
    ("post_diag_other", "workforce_hours_post_diag_other", "dur_post_diag_other", "slots_post_diag_other"),
    ("review", "workforce_hours_review", "dur_review", "slots_review"),
]

PRIORITY_STAGE_KEYS = [
    ("screening", "pct_priority_screening", "screening_priority_dist"),
    ("pre_assessment", "pct_priority_pre_assessment", "pre_assessment_priority_dist"),
    ("assessment", "pct_priority_assessment", "assessment_priority_dist"),
    ("further_assessment", "pct_priority_further_assessment", "further_assessment_priority_dist"),
    ("post_diag_clinical", "pct_priority_post_diag_clinical", "post_diag_clinical_priority_dist"),
    ("post_diag_other", "pct_priority_post_diag_other", "post_diag_other_priority_dist"),
    ("review", "pct_priority_review", "review_priority_dist"),
]

