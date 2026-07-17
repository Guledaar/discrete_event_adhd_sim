"""NHS KPI glossary, methodology notes, aliases, and display helpers.

The glossary distinguishes three reporting bases used by the DES:

* **arrival cohort** — referrals arriving in the collection window;
* **event window** — activity occurring in the collection window regardless
  of referral date; and
* **end-of-run snapshot** — pathway stock at the reporting horizon.

Legacy aliases remain documented because notebooks and saved run artefacts use
them, but each duplicated quantity has one canonical calculation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from des.audit import RTT_18_WEEKS_DAYS

RTT_52_WEEKS_DAYS = 52 * 7

KPI_GLOSSARY: Dict[str, str] = {
    # Flow
    "referrals": "Patients entering the system during collection",
    "referrals_accepted": "Referrals passing triage",
    "referrals_rejected": "Referrals rejected at triage",
    "admin_removals": (
        "Administrative removals with exit_time in the KPI window (any arrival date)"
    ),
    "assessment_appointments_completed": (
        "Assessment appointments delivered for pathways whose assessment_completion "
        "falls in the KPI window (any arrival date; absolute throughput)"
    ),
    "patients_completed_assessment": (
        "Legacy alias of assessments_completed_in_window: patients whose "
        "assessment_completion falls in the KPI window (any arrival date)"
    ),
    "diagnoses": (
        "Legacy alias of diagnoses_completed_in_window: positive diagnosis "
        "decisions with assessment_completion in the KPI event window"
    ),
    "diagnoses_completed_in_window": (
        "Canonical positive-diagnosis throughput: assessment_completion in "
        "the KPI event window, for any referral date"
    ),
    "diagnoses_per_month": (
        "Absolute throughput: positive diagnoses per month "
        "(by assessment_completion time in window, not arrival cohort)"
    ),
    "no_diagnosis": (
        "No-diagnosis exits with assessment_completion in the KPI window "
        "(any arrival date)"
    ),
    "virtual_supports": (
        "Virtual-support completions with exit_time in the KPI window "
        "(any arrival date)"
    ),
    "clinical_supports_enrolled": (
        "Patients diagnosed in the KPI window who entered the workshop/clinical path"
    ),
    "clinical_supports_completed": (
        "Workshop completions with exit_time in the KPI window (any arrival date)"
    ),
    "clinical_supports_in_pathway": (
        "Clinical-support patients still active at the KPI horizon (system stock)"
    ),
    "workshop_groups": (
        "Distinct workshop groups with workshop_start_time in the KPI window"
    ),
    "workshop_sessions": (
        "Workshop sessions for groups that started in the KPI window"
    ),
    # Capacity / utilisation
    "clinician_hours_released": "Weekday clinician hours available during collection",
    "clinician_hours_used": "Clinician hours consumed during collection",
    "clinician_hours_unused": "Unused clinician hours during collection",
    "overall_clinician_utilisation": "Used / released hours (shared pool)",
    "assessment_utilisation": "Assessment hours / released hours",
    "workshop_utilisation": "Workshop hours / released hours",
    # Throughput rates
    "assessments_completed_in_window": (
        "Assessment completions with assessment_completion in [start, end), "
        "any arrival date"
    ),
    "assessments_per_month": (
        "Absolute throughput: assessments completed per month "
        "(by completion time in window, not arrival cohort)"
    ),
    # RTT clock counts
    "rtt_clocks_started": "RTT clocks started (accepted referrals)",
    "rtt_clocks_nullified": "RTT clocks nullified (rejected referrals)",
    "rtt_completed_pathways": (
        "RTT pathways whose clock stop falls in the KPI window (any arrival date)"
    ),
    "cohort_incomplete_pathways": (
        "Incomplete RTT pathways among arrivals in the KPI window"
    ),
    "rtt_incomplete_pathways": (
        "Deprecated alias of cohort_incomplete_pathways"
    ),
    "rtt_completed_stop_treatment": (
        "Completed RTT in window stopped for treatment (virtual or workshop)"
    ),
    "rtt_completed_stop_not_treat": (
        "Completed RTT in window stopped for clinical decision not to treat"
    ),
    "rtt_completed_stop_admin": (
        "Completed RTT in window stopped for administrative removal"
    ),
    # Waiting list
    "waiting_list_size": (
        "Collection-cohort waiting list: incomplete RTT pathways at the horizon "
        "among patients who arrived during the collection window only "
        "(undercounts the true census by excluding warm-up arrivals still waiting)"
    ),
    "waiting_list_size_all_in_system": (
        "NHS waiting list (PTL census): incomplete RTT pathways at the horizon "
        "for ALL patients still in the system, including warm-up arrivals — "
        "the NHS-methodology incomplete-pathway stock measure"
    ),
    "overall_waiting_list_size": (
        "Explicit alias of waiting_list_size_all_in_system: all patients currently "
        "in the service who have not completed the pathway"
    ),
    "first_assessment_waiting_list_size": (
        "Accepted patients still in the service who have not started their first "
        "assessment appointment"
    ),
    "first_workshop_waiting_list_size": (
        "Patients routed to clinical workshop support who have joined the workshop "
        "queue but have not attended their first workshop"
    ),
    "mean_waiting_list_size": (
        "Deprecated alias of waiting_list_snapshot. It is not a mean; retained "
        "for backwards compatibility"
    ),
    "waiting_list_snapshot": (
        "Canonical end-of-run snapshot of incomplete RTT pathways among the "
        "arrival cohort. This is not the full NHS PTL; use "
        "waiting_list_size_all_in_system for the PTL census"
    ),
    "cohort_under_18_weeks_pct": "% of cohort incomplete pathways ≤ 18 weeks",
    "cohort_over_18_weeks_pct": "% of cohort incomplete pathways > 18 weeks",
    "cohort_under_52_weeks_pct": "% of cohort incomplete pathways ≤ 52 weeks",
    "cohort_over_52_weeks_pct": "% of cohort incomplete pathways > 52 weeks",
    "ptl_size": "All incomplete pathways at the reporting horizon (NHS PTL)",
    "ptl_under_18_weeks_pct": "% of the full PTL waiting ≤ 18 weeks",
    "ptl_over_18_weeks_pct": "% of the full PTL waiting > 18 weeks",
    "ptl_under_52_weeks_pct": "% of the full PTL waiting ≤ 52 weeks",
    "ptl_over_52_weeks_pct": "% of the full PTL waiting > 52 weeks",
    "ptl_mean_wait_days": "Mean current wait across the full PTL",
    "ptl_median_wait_days": "Median current wait across the full PTL",
    "ptl_p90_wait_days": "90th-percentile current wait across the full PTL",
    "cohort_mean_wait_days": "Mean wait among cohort incomplete pathways",
    "cohort_median_wait_days": "Median wait among cohort incomplete pathways",
    "cohort_p90_wait_days": (
        "90th-percentile wait among cohort incomplete pathways"
    ),
    "rtt_incomplete_under_18_weeks_pct": (
        "Deprecated alias of cohort_under_18_weeks_pct"
    ),
    "rtt_incomplete_over_18_weeks_pct": (
        "Deprecated alias of cohort_over_18_weeks_pct"
    ),
    "rtt_incomplete_under_52_weeks_pct": (
        "Deprecated alias of cohort_under_52_weeks_pct"
    ),
    "rtt_incomplete_over_52_weeks_pct": (
        "Deprecated alias of cohort_over_52_weeks_pct"
    ),
    # RTT wait times (days)
    "rtt_completed_mean_days": "Mean RTT for completed pathways",
    "rtt_completed_median_days": "Median RTT for completed pathways",
    "rtt_completed_p90_days": "90th percentile RTT for completed pathways",
    "rtt_completed_max_days": "Maximum RTT for completed pathways",
    "rtt_incomplete_mean_days": "Deprecated alias of cohort_mean_wait_days",
    "rtt_incomplete_mode_days": "Deprecated cohort incomplete-wait alias",
    "rtt_incomplete_median_days": "Deprecated alias of cohort_median_wait_days",
    "rtt_incomplete_p90_days": "Deprecated alias of cohort_p90_wait_days",
    "rtt_incomplete_max_days": "Deprecated cohort incomplete-wait alias",
    "rtt_incomplete_ci95_low_days": "95% CI lower bound for mean incomplete RTT",
    "rtt_incomplete_ci95_high_days": "95% CI upper bound for mean incomplete RTT",
    "rtt_first_treatment_mean_days": "Mean RTT to first definitive treatment",
    "rtt_first_treatment_median_days": "Median RTT to first definitive treatment",
    "rtt_first_treatment_p90_days": "90th percentile RTT to first treatment",
    "rtt_first_treatment_max_days": "Maximum RTT to first treatment",
    "mean_overall_rtt_days": (
        "Legacy alias of rtt_completed_mean_days; retained for backwards compatibility"
    ),
    # Pathway segment waits
    "referral_to_first_assessment_mean_days": (
        "Mean referral→first assessment for patients who started assessment "
        "in the window (any arrival date)"
    ),
    "referral_to_first_assessment_mode_days": (
        "Modal referral→first assessment (nearest-day bin, starts in window)"
    ),
    "referral_to_first_assessment_median_days": (
        "Median referral→first assessment (starts in window)"
    ),
    "referral_to_first_assessment_ci95_low_days": (
        "95% CI lower bound for mean referral→first assessment"
    ),
    "referral_to_first_assessment_ci95_high_days": (
        "95% CI upper bound for mean referral→first assessment"
    ),
    "assessment_to_diagnosis_mean_days": "First assessment to diagnosis decision (mean)",
    "diagnosis_to_first_treatment_mean_days": "Diagnosis to first treatment (mean)",
    # Run metadata (from single_run)
    "warmup_days": "Warm-up period length (days)",
    "collection_days": "KPI collection period length (days)",
    "run_length": "Total simulation horizon (days)",
    "rep": "Replication index",
    "scenario": "Scenario preset name",
}

# How each KPI is computed from patient records and collection window [start, end).
_COHORT = "collection cohort (arrival_time ≥ warmup end, < sim end)"
_DONE = "rtt_clock_stop in [start, end)"

KPI_CALCULATIONS: Dict[str, str] = {
    "rtt_clocks_started": (
        f"COUNT({_COHORT}, triage accepted).\n"
        "= referrals − referrals_rejected."
    ),
    "rtt_clocks_nullified": (
        f"COUNT({_COHORT}, exit_route = referral_rejected).\n"
        "RTT clock does not start (nullified)."
    ),
    "rtt_completed_pathways": (
        f"COUNT(all patient records, rtt_pathway_status = completed, {_DONE}).\n"
        "Uses clock-stop event time, including referrals before the collection window."
    ),
    "cohort_incomplete_pathways": (
        f"COUNT({_COHORT}, rtt_pathway_status = incomplete at sim end).\n"
        "= waiting_list_size."
    ),
    "rtt_completed_stop_treatment": (
        "COUNT(completed in collection, exit_route ∈ {virtual_support, workshop_complete})."
    ),
    "rtt_completed_stop_not_treat": (
        "COUNT(completed in collection, exit_route = no_diagnosis)."
    ),
    "rtt_completed_stop_admin": (
        "COUNT(completed in collection, exit_route = admin_removal)."
    ),
    "cohort_under_18_weeks_pct": (
        f"100 × COUNT({_COHORT}, incomplete, wait ≤ {RTT_18_WEEKS_DAYS}) "
        "÷ cohort_incomplete_pathways."
    ),
    "cohort_over_18_weeks_pct": (
        f"100 × COUNT({_COHORT}, incomplete, wait > {RTT_18_WEEKS_DAYS}) "
        "÷ cohort_incomplete_pathways."
    ),
    "cohort_under_52_weeks_pct": (
        f"100 × COUNT({_COHORT}, incomplete, wait ≤ {RTT_52_WEEKS_DAYS}) "
        "÷ cohort_incomplete_pathways."
    ),
    "cohort_over_52_weeks_pct": (
        f"100 × COUNT({_COHORT}, incomplete, wait > {RTT_52_WEEKS_DAYS}) "
        "÷ cohort_incomplete_pathways."
    ),
    "ptl_under_18_weeks_pct": (
        f"100 × COUNT(all incomplete at end, wait ≤ {RTT_18_WEEKS_DAYS}) ÷ ptl_size."
    ),
    "ptl_over_18_weeks_pct": (
        f"100 × COUNT(all incomplete at end, wait > {RTT_18_WEEKS_DAYS}) ÷ ptl_size."
    ),
    "ptl_under_52_weeks_pct": (
        f"100 × COUNT(all incomplete at end, wait ≤ {RTT_52_WEEKS_DAYS}) ÷ ptl_size."
    ),
    "ptl_over_52_weeks_pct": (
        f"100 × COUNT(all incomplete at end, wait > {RTT_52_WEEKS_DAYS}) ÷ ptl_size."
    ),
    "ptl_mean_wait_days": "MEAN(end − arrival_time) across all incomplete pathways.",
    "ptl_median_wait_days": "MEDIAN(end − arrival_time) across all incomplete pathways.",
    "ptl_p90_wait_days": (
        "90th percentile(end − arrival_time) across all incomplete pathways."
    ),
    "cohort_mean_wait_days": (
        f"MEAN(end − arrival_time) among incomplete pathways in {_COHORT}."
    ),
    "cohort_median_wait_days": (
        f"MEDIAN(end − arrival_time) among incomplete pathways in {_COHORT}."
    ),
    "cohort_p90_wait_days": (
        f"90th percentile(end − arrival_time) among incomplete pathways in {_COHORT}."
    ),
    "rtt_completed_mean_days": (
        "MEAN(rtt_wait_days) for all pathways whose clock stop is in the event window,\n"
        "excluding admin_removal.\n"
        "rtt_wait_days = rtt_clock_stop − arrival;\n"
        "stop: admin→exit_time, no_diagnosis→assessment_completion,\n"
        "virtual→exit_time, workshop→workshop_start_time."
    ),
    "rtt_completed_median_days": "MEDIAN(rtt_wait_days) — same cohort as rtt_completed_mean_days.",
    "rtt_completed_p90_days": "90th percentile(rtt_wait_days) — same cohort.",
    "rtt_completed_max_days": "MAX(rtt_wait_days) — same cohort.",
    "rtt_incomplete_mean_days": (
        "Deprecated alias of cohort_mean_wait_days."
    ),
    "rtt_incomplete_median_days": "Deprecated alias of cohort_median_wait_days.",
    "rtt_incomplete_p90_days": "Deprecated alias of cohort_p90_wait_days.",
    "rtt_incomplete_max_days": "Deprecated cohort maximum-wait alias.",
    "rtt_first_treatment_mean_days": (
        "MEAN(rtt_wait_days) on treatment completions in collection\n"
        "(virtual_support or workshop_complete)."
    ),
    "rtt_first_treatment_median_days": (
        "MEDIAN(rtt_wait_days) — same treatment cohort as rtt_first_treatment_mean_days."
    ),
    "rtt_first_treatment_p90_days": (
        "90th percentile(rtt_wait_days) — same treatment cohort."
    ),
    "rtt_first_treatment_max_days": (
        "MAX(rtt_wait_days) — same treatment cohort."
    ),
    "waiting_list_size": (
        "COUNT(collection cohort, rtt_pathway_status = incomplete at sim end).\n"
        "= rtt_incomplete_pathways. Cohort-restricted stock (undercounts the\n"
        "full census; use waiting_list_size_all_in_system for NHS PTL)."
    ),
    "waiting_list_size_all_in_system": (
        "COUNT(all patients at sim end with rtt_pathway_status = incomplete,\n"
        "including warm-up arrivals). NHS incomplete-pathway census (PTL)."
    ),
    "overall_waiting_list_size": (
        "Same value as waiting_list_size_all_in_system: COUNT(all patients at "
        "the horizon whose pathway remains incomplete)."
    ),
    "first_assessment_waiting_list_size": (
        "COUNT(all patients at the horizon where triage_outcome = accepted,\n"
        "rtt_pathway_status = incomplete, and assessment_start is missing)."
    ),
    "first_workshop_waiting_list_size": (
        "COUNT(all patients at the horizon where diagnosis = True,\n"
        "support_type = clinical, workshop_join_time is recorded, and\n"
        "workshop_start_time is missing)."
    ),
    "mean_waiting_list_size": (
        "Deprecated alias of waiting_list_snapshot. Single end-of-run snapshot,\n"
        "not a time-averaged mean."
    ),
    "waiting_list_snapshot": (
        "Canonical alias target: FLOAT(waiting_list_size).\n"
        "Arrival-cohort end-of-run snapshot, not the full NHS PTL."
    ),
    "mean_overall_rtt_days": "Same as rtt_completed_mean_days (KPI map alias).",
}


def kpi_glossary_table(keys: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Build a KPI glossary table for notebooks and docs.

    Parameters
    ----------
    keys : list of str, optional
        Subset of KPI names. When ``None``, include the full glossary.

    Returns
    -------
    pandas.DataFrame
        Columns ``kpi``, ``description``, ``how_calculated``.
    """
    rows = []
    for k, description in KPI_GLOSSARY.items():
        if keys is not None and k not in keys:
            continue
        rows.append(
            {
                "kpi": k,
                "description": description,
                "how_calculated": KPI_CALCULATIONS.get(k, ""),
            }
        )
    return pd.DataFrame(rows)


def rtt_kpi_definitions_table() -> pd.DataFrame:
    """
    Return the RTT-only subset of the KPI glossary.

    Returns
    -------
    pandas.DataFrame
        Rows whose KPI name starts with ``rtt_``.
    """
    return kpi_glossary_table(
        keys=[k for k in KPI_GLOSSARY if k.startswith("rtt_")]
    )


def display_rtt_kpi_definitions():
    """
    Display a styled RTT KPI glossary table in a Jupyter notebook.

    Returns
    -------
    styler
        Pandas Styler shown via IPython ``display``.
    """
    from IPython.display import display

    styled = (
        rtt_kpi_definitions_table()
        .set_index("kpi")[["description", "how_calculated"]]
        .style.set_properties(
            **{"white-space": "pre-wrap", "text-align": "left", "vertical-align": "top"}
        )
        .set_table_styles(
            [
                {"selector": "th", "props": [("text-align", "left")]},
                {"selector": "td", "props": [("max-width", "480px")]},
            ]
        )
    )
    display(styled)
    return styled


def kpi_results_reference(
    results: Dict[str, Any],
    keys: List[str],
) -> pd.DataFrame:
    """
    Join simulated KPI values with glossary text.

    Parameters
    ----------
    results : dict
        Flat KPI summary (e.g. from ``single_run``).
    keys : list of str
        KPI names to include when present in *results*.

    Returns
    -------
    pandas.DataFrame
        Columns ``value``, ``description``, ``how_calculated``.
    """
    defs = kpi_glossary_table().set_index("kpi")
    values = pd.Series({k: results[k] for k in keys if k in results})
    matched = defs.reindex(values.index)
    return pd.DataFrame(
        {
            "value": values,
            "description": matched["description"],
            "how_calculated": matched["how_calculated"],
        }
    )


def display_kpi_results_reference(
    results: Dict[str, Any],
    keys: List[str],
):
    """
    Display KPI values beside glossary definitions in a notebook.

    Parameters
    ----------
    results : dict
        Flat KPI summary.
    keys : list of str
        KPI names to show.

    Returns
    -------
    pandas.DataFrame
        Underlying reference table (also displayed styled).
    """
    from IPython.display import display

    df = kpi_results_reference(results, keys)
    styled = (
        df.style.format({"value": "{:,.4g}"})
        .set_properties(
            **{"white-space": "pre-wrap", "text-align": "left", "vertical-align": "top"}
        )
        .set_table_styles(
            [
                {"selector": "th", "props": [("text-align", "left")]},
                {"selector": "td", "props": [("max-width", "480px")]},
            ]
        )
    )
    display(styled)
    return df
