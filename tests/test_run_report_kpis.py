import numpy as np
import pandas as pd

from des.config import DURATION_ASSESSMENT
from des.runners import _summary, summarise_policy_kpi_time_series
from des.run_report import (
    build_run_report,
    enrich_rtt,
    flow_counts_with_waits_table,
    kpi_snapshot,
    run_report_summary,
    utilisation_summary,
    waits_flow_mean_median_table,
    waits_stock_mean_median_table,
)


def test_config_duration_assessment_is_correct():
    assert DURATION_ASSESSMENT == [2.0, 2.5, 3.0]


def test_enrich_rtt_uses_exit_time_for_workshop_completion():
    patients = pd.DataFrame(
        [
            {
                "patient_id": 1,
                "arrival_time": 0.0,
                "triage_outcome": "accepted",
                "admin_removal": False,
                "assessment_start": 1.0,
                "assessment_completion": 10.0,
                "diagnosis": True,
                "support_type": "clinical",
                "workshop_join_time": 15.0,
                "workshop_start_time": 20.0,
                "workshop_completion": 60.0,
                "exit_time": 60.0,
                "exit_route": "workshop_complete",
            }
        ]
    )

    rtt = enrich_rtt(patients, sim_end=100.0)
    assert rtt.loc[0, "rtt_status"] == "completed"
    assert rtt.loc[0, "rtt_clock_stop"] == 60.0
    assert rtt.loc[0, "rtt_wait_days"] == 60.0


def test_build_run_report_produces_expected_kpi_tables():
    patients = pd.DataFrame(
        [
            {
                "patient_id": 1,
                "arrival_time": 0.0,
                "triage_outcome": "rejected",
                "admin_removal": False,
                "exit_time": 0.0,
                "exit_route": "referral_rejected",
            },
            {
                "patient_id": 2,
                "arrival_time": 1.0,
                "triage_outcome": "accepted",
                "admin_removal": True,
                "exit_time": 10.0,
                "exit_route": "admin_removal",
            },
            {
                "patient_id": 3,
                "arrival_time": 2.0,
                "triage_outcome": "accepted",
                "admin_removal": False,
                "assessment_start": 5.0,
                "assessment_completion": 15.0,
                "diagnosis": True,
                "support_type": "virtual",
                "exit_time": 15.0,
                "exit_route": "virtual_support",
            },
            {
                "patient_id": 4,
                "arrival_time": 3.0,
                "triage_outcome": "accepted",
                "admin_removal": False,
                "assessment_start": 6.0,
                "assessment_completion": 16.0,
                "diagnosis": True,
                "support_type": "clinical",
                "workshop_join_time": 20.0,
                "workshop_start_time": 30.0,
                "workshop_completion": 50.0,
                "exit_time": 50.0,
                "exit_route": "workshop_complete",
            },
        ]
    )

    capacity = pd.DataFrame(
        [
            {
                "hours_released": 7.0,
                "hours_used": 5.0,
                "hours_unused": 2.0,
                "assessment_hours_used": 3.0,
                "workshop_hours_used": 2.0,
            }
        ]
    )

    report = build_run_report(patients, capacity, sim_end=100.0, flow_window_days=100.0)

    assert "workshop_complete" in report.pathway_exits["exit_route"].tolist()
    assert report.capacity_utilisation.iloc[0]["hours_used_pct"] == 5.0 / 7.0 * 100.0
    assert report.pathway_funnel.loc["workshop_completed", "count"] == 1
    assert report.activity_flow.loc["all_exits_in_window", "count_in_window"] == 4
    completed_clinical = report.rtt_waits_stock.loc[
        report.rtt_waits_stock["cohort"] == "completed_clinical", "mean"
    ].iloc[0]
    assert completed_clinical == 30.0
    snapshot = kpi_snapshot(report)
    assert snapshot["backlog_patients_at_horizon"] == 0
    assert snapshot["overall_clinician_utilisation"] == report.capacity_utilisation.iloc[0]["hours_used_pct"] / 100.0
    assert set(snapshot.keys()) >= {
        "backlog_patients_at_horizon",
        "backlog_mean_wait_days",
        "backlog_median_wait_days",
        "waiting_list_size",
        "diagnoses_per_month",
        "capacity_used_pct",
    }


def test_run_report_summary_wait_and_flow_table_helpers():
    stock = pd.DataFrame(
        [
            {
                "stage": "wait_referral_to_first_assessment",
                "label": "Referral → first assessment",
                "eligible_n": 10,
                "complete_n": 6,
                "still_waiting_n": 4,
                "completed_mean_days": 100.0,
                "completed_median_days": 90.0,
                "still_waiting_mean_days": 200.0,
                "still_waiting_median_days": 180.0,
            }
        ]
    )
    flow_w = pd.DataFrame(
        [
            {
                "stage": "wait_referral_to_first_assessment",
                "label": "Referral → first assessment",
                "window_days": 365.0,
                "n": 3,
                "mean": 50.0,
                "median": 48.0,
            }
        ]
    )
    activity = pd.DataFrame(
        [
            {
                "metric": "assessments_started_in_window",
                "label": "Assessments started",
                "count_in_window": 3,
                "per_month": 0.25,
            }
        ]
    ).set_index("metric")

    horizon = waits_stock_mean_median_table(stock)
    assert "still_waiting_median_days" in horizon.columns
    flow_tbl = waits_flow_mean_median_table(flow_w)
    assert flow_tbl["completions_in_window"].iloc[0] == 3
    assert flow_tbl["mean_wait_days"].iloc[0] == 50.0
    combined = flow_counts_with_waits_table(activity, flow_w)
    assert combined["mean_wait_days"].iloc[0] == 50.0
    assert combined["count_in_window"].iloc[0] == 3


def test_build_run_report_includes_expected_kpi_tables():
    patients = pd.DataFrame(
        [
            {
                "patient_id": 1,
                "arrival_time": 0.0,
                "triage_outcome": "rejected",
                "admin_removal": False,
                "diagnosis": False,
                "support_type": "virtual",
                "assessment_start": None,
                "assessment_completion": None,
                "workshop_join_time": None,
                "workshop_start_time": None,
                "workshop_completion": None,
                "exit_time": 0.0,
                "exit_route": "referral_rejected",
            }
        ]
    )
    capacity = pd.DataFrame(
        [
            {
                "hours_released": 7.0,
                "hours_used": 5.0,
                "hours_unused": 2.0,
                "assessment_hours_used": 3.0,
                "workshop_hours_used": 2.0,
            }
        ]
    )

    report = build_run_report(patients, capacity, sim_end=10.0, flow_window_days=10.0)
    assert report.pathway_funnel.index.name == "stage"
    assert "count" in report.pathway_funnel.columns
    assert "exit_route" in report.pathway_exits.columns
    assert "hours_used_pct" in report.capacity_utilisation.columns
    assert "stage" in report.waits_stock_by_stage.columns
    assert "cohort" in report.rtt_waits_stock.columns
    assert "cohort" in report.rtt_breaches_stock.columns
    assert "stage" in report.waits_flow_by_stage.columns
    assert report.activity_flow.index.name == "metric"
    assert "referrals_in_window" in report.activity_flow.index
    assert set(report.as_dict().keys()) == {
        "sim_end",
        "flow_window_days",
        "pathway_funnel",
        "pathway_exits",
        "waits_stock_by_stage",
        "waits_flow_by_stage",
        "rtt_waits_stock",
        "rtt_breaches_stock",
        "capacity_utilisation",
        "assessment_adherence",
        "workshop_group_stats",
        "activity_flow",
        "model_params",
    }


def test_utilisation_summary_returns_expected_percentages():
    capacity = pd.DataFrame(
        [
            {
                "hours_released": 10.0,
                "hours_used": 7.5,
                "hours_unused": 2.5,
                "assessment_hours_used": 4.0,
                "workshop_hours_used": 3.5,
            },
            {
                "hours_released": 10.0,
                "hours_used": 6.0,
                "hours_unused": 4.0,
                "assessment_hours_used": 3.0,
                "workshop_hours_used": 3.0,
            },
        ]
    )

    output = utilisation_summary(capacity)
    assert output.iloc[0]["hours_released"] == 20.0
    assert output.iloc[0]["hours_used_pct"] == (13.5 / 20.0) * 100.0
    assert output.iloc[0]["assessment_pct_of_released"] == (7.0 / 20.0) * 100.0
    assert output.iloc[0]["workshop_pct_of_released"] == (6.5 / 20.0) * 100.0


def test_summary_includes_mean_when_all_values_are_nan():
    stats = _summary(pd.Series([np.nan, np.nan]))
    assert "mean" in stats.index
    assert np.isnan(stats["mean"])
    assert int(stats["n"]) == 0


def test_summarise_policy_kpi_time_series_with_mismatched_columns():
    base = {"sim_day": 1, "days_since_switch": 0, "years_since_switch": 0.0}
    a = pd.DataFrame([{**base, "backlog_patients_at_horizon": 100.0}])
    b = pd.DataFrame(
        [{**base, "backlog_patients_at_horizon": 98.0, "backlog_median_wait_days": 500.0}]
    )
    out = summarise_policy_kpi_time_series([a, b])
    assert len(out) == 1
    assert "backlog_patients_at_horizon" in out.columns
    assert "backlog_median_wait_days" in out.columns
