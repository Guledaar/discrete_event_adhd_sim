"""Run packaged V&V checks from iteration4.ipynb Section 21."""

from adhd_simpy.Model.verification import (
    run_demand_stress_verification,
    run_flow_conservation_verification,
    run_math_convergence_verification,
    run_rtt_cohort_verification,
    run_seed_verification,
)


def test_seed_reproducibility():
    run_seed_verification()


def test_flow_conservation():
    run_flow_conservation_verification()


def test_rtt_cohort():
    run_rtt_cohort_verification()


def test_math_convergence():
    run_math_convergence_verification()


def test_demand_stress():
    run_demand_stress_verification()
