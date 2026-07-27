"""Run model V&V checks from :mod:`des.verification`."""

from des.verification import (
    run_demand_stress_verification,
    run_flow_conservation_verification,
    run_infinite_capacity_rtt_sanity_check,
    run_rtt_cohort_verification,
    run_seed_verification,
    run_workforce_accounting_verification,
)


def test_seed_reproducibility():
    run_seed_verification()


def test_flow_conservation():
    run_flow_conservation_verification()


def test_rtt_cohort():
    run_rtt_cohort_verification()


def test_workforce_accounting():
    run_workforce_accounting_verification()


def test_demand_stress():
    run_demand_stress_verification()


def test_infinite_capacity_rtt_sanity():
    run_infinite_capacity_rtt_sanity_check()
