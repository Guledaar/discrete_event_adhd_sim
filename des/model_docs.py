"""Model parameter definitions and three-run framework glossary.

Used by Streamlit reference pages and notebooks. KPI metric glossary lives in
``des.kpi_docs``; this module covers pathway parameters and run terminology.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

# parameter_key → {label, category, unit, definition, notes}
MODEL_PARAMETER_DEFINITIONS: Dict[str, Dict[str, str]] = {
    # Demand / triage
    "referrals_per_day": {
        "label": "Referrals per day",
        "category": "Demand & triage",
        "unit": "patients / day",
        "definition": (
            "Mean referral arrival rate. Converted to inter-arrival time "
            "IAT = 1 / referrals_per_day for the exponential arrival process."
        ),
        "notes": "Provider-facing demand input.",
    },
    "iat": {
        "label": "Inter-arrival time (IAT)",
        "category": "Demand & triage",
        "unit": "days",
        "definition": "Mean time between consecutive referrals (exponential).",
        "notes": "Usually derived from referrals_per_day; can be overridden in policies.",
    },
    "accept_rate": {
        "label": "Accept rate",
        "category": "Demand & triage",
        "unit": "probability",
        "definition": "Share of referrals accepted at triage.",
        "notes": "Maps to pct_referral_rejected = 1 − accept_rate.",
    },
    "pct_referral_rejected": {
        "label": "Referral rejection rate",
        "category": "Demand & triage",
        "unit": "probability",
        "definition": "Probability a referral is rejected at triage (RTT clock nullified).",
        "notes": "Experiment kwargs form of (1 − accept_rate).",
    },
    "admin_removal_probability": {
        "label": "Admin removal probability",
        "category": "Demand & triage",
        "unit": "probability",
        "definition": (
            "Probability an accepted patient is removed administratively "
            "before completing assessment."
        ),
        "notes": "Alias: admin_removal → pct_admin_removal.",
    },
    "pct_admin_removal": {
        "label": "Admin removal rate",
        "category": "Demand & triage",
        "unit": "probability",
        "definition": "Same as admin_removal_probability in Experiment kwargs.",
        "notes": "Stops RTT as administrative completion.",
    },
    "workforce_hours_per_day": {
        "label": "Clinician hours / weekday",
        "category": "Capacity",
        "unit": "hours / weekday",
        "definition": (
            "Shared weekday clinician capacity for assessment and post-diagnosis "
            "clinical support."
        ),
        "notes": "Primary capacity lever for policy scenarios.",
    },
    # Assessment pathway
    "assessment_appointment_counts": {
        "label": "Appointment counts",
        "category": "Assessment pathway",
        "unit": "count options",
        "definition": "Discrete set of how many assessment appointments a patient may need.",
        "notes": "Paired with assessment_appointment_probs.",
    },
    "assessment_appointment_probs": {
        "label": "Appointment count probabilities",
        "category": "Assessment pathway",
        "unit": "probabilities",
        "definition": "Probability mass over appointment_counts (auto-normalised if needed).",
        "notes": "Must match length of appointment_counts.",
    },
    "duration_assessment": {
        "label": "Assessment duration triangle",
        "category": "Assessment pathway",
        "unit": "hours [min, mode, max]",
        "definition": "Triangular distribution of clinician time per assessment appointment.",
        "notes": "Must satisfy min ≤ mode ≤ max.",
    },
    "assessment_gap_days": {
        "label": "Assessment gap",
        "category": "Assessment pathway",
        "unit": "days",
        "definition": "Calendar gap between successive assessment appointments for a patient.",
        "notes": "",
    },
    # Clinical outcomes
    "pct_diagnosis": {
        "label": "Diagnosis rate",
        "category": "Clinical outcomes",
        "unit": "probability",
        "definition": "Probability of positive diagnosis after assessment completion.",
        "notes": "Complement exits as no_diagnosis.",
    },
    "pct_virtual_support": {
        "label": "Virtual support rate",
        "category": "Clinical outcomes",
        "unit": "probability",
        "definition": (
            "Given diagnosis, probability of virtual post-diagnosis support "
            "instead of workshop/clinical support."
        ),
        "notes": "",
    },
    # Workshop
    "workshop_group_size": {
        "label": "Workshop group size",
        "category": "Workshop",
        "unit": "patients",
        "definition": "Target number of patients per workshop group.",
        "notes": "",
    },
    "workshop_num_sessions": {
        "label": "Workshop sessions",
        "category": "Workshop",
        "unit": "sessions",
        "definition": "Number of sessions in a workshop programme.",
        "notes": "",
    },
    "workshop_session_interval_weeks": {
        "label": "Session interval",
        "category": "Workshop",
        "unit": "weeks",
        "definition": "Weeks between consecutive workshop sessions.",
        "notes": "",
    },
    "workshop_max_wait_days": {
        "label": "Max wait to form workshop",
        "category": "Workshop",
        "unit": "days",
        "definition": "Maximum wait before a partial group may start.",
        "notes": "",
    },
    "duration_workshop_session": {
        "label": "Workshop session duration triangle",
        "category": "Workshop",
        "unit": "hours [min, mode, max]",
        "definition": "Triangular distribution of workshop session length.",
        "notes": "Must satisfy min ≤ mode ≤ max.",
    },
    "workforce_hours_workshop_session": {
        "label": "Clinician hours per workshop session",
        "category": "Workshop",
        "unit": "hours",
        "definition": "Clinician time charged to the shared pool per workshop session.",
        "notes": "",
    },
    # RNG / run meta
    "random_number_set": {
        "label": "Base random seed",
        "category": "RNG",
        "unit": "integer",
        "definition": "Base seed for RNG streams (replication seeds offset from this).",
        "notes": "Alias in nested config: random_seed.",
    },
    "use_fixed_seed": {
        "label": "Fixed seeds",
        "category": "RNG",
        "unit": "boolean",
        "definition": "If true, runs are reproducible for a given seed.",
        "notes": "",
    },
    # Calibration / runs
    "match_tolerance": {
        "label": "Match tolerance (MAPE)",
        "category": "Run 1 calibration",
        "unit": "relative error",
        "definition": "Stop when waiting-list MAPE ≤ this tolerance (e.g. 0.05 = 5%).",
        "notes": "",
    },
    "step_days": {
        "label": "Calibration step",
        "category": "Run 1 calibration",
        "unit": "days",
        "definition": "Horizon increment when searching for Optimal Matching Period T*.",
        "notes": "",
    },
    "min_period_days": {
        "label": "Min matching period",
        "category": "Run 1 calibration",
        "unit": "days",
        "definition": "Earliest candidate horizon for T*.",
        "notes": "",
    },
    "max_period_days": {
        "label": "Max matching period",
        "category": "Run 1 calibration",
        "unit": "days",
        "definition": "Latest candidate horizon; used as best-effort T* if never matched.",
        "notes": "",
    },
    "rolling_window_days": {
        "label": "Rolling KPI window",
        "category": "Run 1 calibration",
        "unit": "days",
        "definition": "Length of the KPI collection window ending at each candidate T.",
        "notes": "",
    },
    "n_reps": {
        "label": "Baseline replications",
        "category": "Run 2 baseline",
        "unit": "count",
        "definition": "Number of independent seeds for stochastic baseline CIs.",
        "notes": "",
    },
    "confidence_level": {
        "label": "Confidence level",
        "category": "Run 2 baseline",
        "unit": "probability",
        "definition": "CI level for baseline KPI means (typically 0.95).",
        "notes": "",
    },
    "decay_period_days": {
        "label": "Policy decay period",
        "category": "Run 3 policy",
        "unit": "days",
        "definition": "Simulated time after SwitchTime T* under the policy package.",
        "notes": "Often expressed in years in the UI (× 365).",
    },
}

# Framework / pathway term glossary
MODEL_GLOSSARY: Dict[str, str] = {
    "DES": (
        "Discrete-event simulation: the system state changes only at event times "
        "(arrivals, appointments, workshop sessions)."
    ),
    "Optimal Matching Period (T*)": (
        "Horizon found in Run 1 where simulated KPIs best match provider targets "
        "(minimum aggregate MAPE within search grid)."
    ),
    "MAPE": (
        "Mean Absolute Percentage Error: |sim − target| / |target|. "
        "Aggregate MAPE is the weighted average across selected targets."
    ),
    "SwitchTime": (
        "Instant T* in Run 3 when policy parameter overrides are applied; "
        "the same continuous SimPy environment continues into the decay period."
    ),
    "Policy package": (
        "Named set of Experiment overrides (e.g. higher workforce_hours_per_day) "
        "applied at SwitchTime."
    ),
    "Control arm": (
        "Same-seed continuous run with empty overrides, used to compare backlog "
        "decay against the policy arm."
    ),
    "Backlog decay": (
        "Change in waiting list (and related clearance) between SwitchTime and "
        "the end of the decay period."
    ),
    "Collection window": (
        "Time interval over which KPIs are summarised (typically a rolling window "
        "ending at the evaluation horizon)."
    ),
    "Warm-up": (
        "Initial simulation period used to populate the system before KPI collection "
        "(classic single_run design; three-run calibration uses live growth to T*)."
    ),
    "RTT clock": (
        "Referral-to-treatment waiting-time clock: starts on accept, stops on "
        "treatment / clinical exit / admin removal, or remains incomplete at horizon."
    ),
    "Waiting list (all in system)": (
        "Count of incomplete RTT pathways at the horizon, including patients who "
        "arrived before the collection window (stock measure)."
    ),
    "Waiting list (collection cohort)": (
        "Incomplete pathways among patients who arrived during the collection window."
    ),
    "Shared clinician pool": (
        "Weekday clinician hours used for both assessment and workshop/clinical "
        "support (workforce_hours_per_day)."
    ),
    "Provider targets": (
        "Observed or contractual KPI levels used as Run 1 calibration targets."
    ),
    "Artefacts": (
        "JSON/CSV files written under output_dir linking independent runs "
        "(optimal_matching_period.json, stochastic_baseline.json, policy_*.json)."
    ),
}


def model_parameter_table(
    categories: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Build a model-parameter definition table for Streamlit / notebooks.

    Parameters
    ----------
    categories : list of str, optional
        Keep only these category labels. When ``None``, include all.

    Returns
    -------
    pandas.DataFrame
        Columns ``parameter``, ``label``, ``category``, ``unit``,
        ``definition``, ``notes``.
    """
    rows = []
    for key, meta in MODEL_PARAMETER_DEFINITIONS.items():
        if categories is not None and meta["category"] not in categories:
            continue
        rows.append(
            {
                "parameter": key,
                "label": meta["label"],
                "category": meta["category"],
                "unit": meta["unit"],
                "definition": meta["definition"],
                "notes": meta.get("notes", ""),
            }
        )
    return pd.DataFrame(rows)


def model_glossary_table() -> pd.DataFrame:
    """
    Return the framework / pathway term glossary as a table.

    Returns
    -------
    pandas.DataFrame
        Columns ``term``, ``definition``.
    """
    return pd.DataFrame(
        [{"term": k, "definition": v} for k, v in MODEL_GLOSSARY.items()]
    )


def parameter_categories() -> List[str]:
    """
    Return distinct parameter categories in definition order.

    Returns
    -------
    list of str
        Unique category labels from ``MODEL_PARAMETER_DEFINITIONS``.
    """
    seen: List[str] = []
    for meta in MODEL_PARAMETER_DEFINITIONS.values():
        cat = meta["category"]
        if cat not in seen:
            seen.append(cat)
    return seen
