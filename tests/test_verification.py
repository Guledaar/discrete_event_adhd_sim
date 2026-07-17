"""Run packaged V&V checks from iteration4.ipynb Section 21."""

from adhd_simpy.Model.verification import (
    run_demand_stress_verification,
    run_flow_conservation_verification,
    run_infinite_capacity_rtt_sanity_check,
    run_rtt_cohort_verification,
    run_rtt_cohort_with_warmup_verification,
    run_rtt_percentile_order_verification,
    run_seed_verification,
    run_triage_boundary_verification,
    run_workforce_accounting_verification,
)


def test_seed_reproducibility():
    run_seed_verification()


def test_flow_conservation():
    run_flow_conservation_verification()


def test_rtt_cohort():
    run_rtt_cohort_verification()


def test_rtt_cohort_with_warmup():
    run_rtt_cohort_with_warmup_verification()


def test_workforce_accounting():
    run_workforce_accounting_verification()


def test_rtt_percentile_order():
    run_rtt_percentile_order_verification()


def test_triage_boundary():
    run_triage_boundary_verification()


def test_infinite_capacity_rtt_sanity():
    run_infinite_capacity_rtt_sanity_check()


def test_demand_stress():
    run_demand_stress_verification()
