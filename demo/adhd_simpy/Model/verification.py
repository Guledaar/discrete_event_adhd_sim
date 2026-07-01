"""Automated verification and validation tests."""

from adhd_simpy.Model.audit import Audit
from adhd_simpy.Model.experiment import Experiment
from adhd_simpy.Model.parameters import (
    DURATION_ASSESSMENT,
    DURATION_FURTHER_ASSESSMENT,
    DURATION_PRE_ASSESSMENT,
    DURATION_SCREENING,
    RUN_LENGTH,
)
from adhd_simpy.Model.simulation import single_run

def print_header(title):
    print("\n" + "=" * 65)
    print(f" SUITE: {title}")
    print("=" * 65)


def triangular_mean_days(duration_triplet):
    return sum(duration_triplet) / 3.0 / 24.0


def run_seed_verification():
    print_header("1. SEED CONTROL & REPRODUCIBILITY VERIFICATION")
    exp1 = Experiment(auditor=Audit(), use_fixed_seed=True, random_number_set=101)
    res1 = single_run(exp1, rep=0, run_length=365, warmup_days=0)
    exp2 = Experiment(auditor=Audit(), use_fixed_seed=True, random_number_set=101)
    res2 = single_run(exp2, rep=0, run_length=365, warmup_days=0)
    assert res1["ARRIVED_TOTAL"] == res2["ARRIVED_TOTAL"]
    assert res1["ACCESS_REFERRAL_TO_PRE_ASSESSMENT_RTT_DAYS"] == res2["ACCESS_REFERRAL_TO_PRE_ASSESSMENT_RTT_DAYS"]
    print(" -> SUCCESS: Fixed seeds are deterministic and reproducible.")


def run_flow_conservation_verification():
    print_header("2. PATIENT FLOW MASS-CONSERVATION VERIFICATION")
    exp = Experiment(auditor=Audit(), use_fixed_seed=True, random_number_set=42)
    results = single_run(exp, rep=1, run_length=RUN_LENGTH, warmup_days=0)
    arrived = results["ARRIVED_TOTAL"]
    exited = results["EXIT_TOTAL"]
    trapped = results["IN_SYSTEM_END"]
    print(f"  Arrived: {arrived} | Exited: {exited} | In system: {trapped}")
    assert arrived == exited + trapped
    print(" -> SUCCESS: Mass balance verified (arrivals = exits + in system).")


def run_rtt_cohort_verification():
    print_header("3. RTT COHORT COMPLETENESS VERIFICATION")
    exp = Experiment(auditor=Audit(), use_fixed_seed=True, random_number_set=42)
    results = single_run(exp, rep=1, run_length=RUN_LENGTH, warmup_days=0)
    assert results["COHORT_DRAIN_COMPLETE"], "Drain must clear all collection-cohort patients"
    assert results["IN_SYSTEM_END"] == 0, f"Backlog in system must be zero, got {results['IN_SYSTEM_END']}"
    assert results["QUEUE_TOTAL_BACKLOG"] == 0, f"Queue backlog must be zero, got {results['QUEUE_TOTAL_BACKLOG']}"
    assert results["COHORT_RTT_VALID"], "RTT KPIs require zero in-system backlog at simulation end"
    assert results["KPI_SAMPLE_N_RTT_DIAGNOSIS"] == results["FLOW_DIAGNOSIS_CONFIRMED"]
    print(
        f"  Diagnosis RTT samples: {results['KPI_SAMPLE_N_RTT_DIAGNOSIS']} | "
        f"Diagnoses confirmed: {results['FLOW_DIAGNOSIS_CONFIRMED']} | "
        f"In system: {results['IN_SYSTEM_END']}"
    )
    print(" -> SUCCESS: Cohort RTT computed after full drain (zero backlog).")


def run_math_convergence_verification():
    print_header("4. WORKFORCE-HOURS MATHEMATICAL CONVERGENCE")
    inf_settings = {
        "workforce_hours_screening": 1e6,
        "workforce_hours_pre_assessment": 1e6,
        "workforce_hours_assessment": 1e6,
        "workforce_hours_further_assessment": 1e6,
        "workforce_hours_post_diag_clinical": 1e6,
        "workforce_hours_post_diag_other": 1e6,
        "workforce_hours_review": 1e6,
    }
    exp = Experiment(auditor=Audit(), use_fixed_seed=True, random_number_set=77, **inf_settings)
    res = single_run(exp, rep=0, run_length=365 * 2, warmup_days=0)
    assessment_pathway = [DURATION_SCREENING, DURATION_PRE_ASSESSMENT, DURATION_ASSESSMENT]
    assessment_service_days = sum(triangular_mean_days(s) for s in assessment_pathway)
    assessment_empirical_rtt = res["ACCESS_REFERRAL_TO_ASSESSMENT_RTT_DAYS"]
    assessment_calendar_delay = assessment_empirical_rtt - assessment_service_days
    assessment_delay_per_stage = assessment_calendar_delay / len(assessment_pathway)
    diagnosis_pathway = assessment_pathway + [DURATION_FURTHER_ASSESSMENT]
    diagnosis_service_days = sum(triangular_mean_days(s) for s in diagnosis_pathway)
    diagnosis_theoretical_rtt = diagnosis_service_days + assessment_delay_per_stage * len(diagnosis_pathway)
    diagnosis_empirical_rtt = res["ACCESS_REFERRAL_TO_DIAGNOSIS_RTT_DAYS"]
    diagnosis_delta = abs(diagnosis_theoretical_rtt - diagnosis_empirical_rtt)
    print(f"  Assessment RTT: {assessment_empirical_rtt:.3f} d | Diagnosis RTT: {diagnosis_empirical_rtt:.3f} d | Delta: {diagnosis_delta:.3f}")
    assert 0.0 < assessment_delay_per_stage < 2.0
    assert diagnosis_delta < 2.0, f"Diagnosis convergence failed (delta={diagnosis_delta:.3f})"
    print(" -> SUCCESS: Infinite-capacity scheduler validation passed.")


def assert_monotonic_increasing(values, label, levels):
    """Require strictly increasing values across demand levels."""
    for i in range(len(values) - 1):
        if not values[i] < values[i + 1]:
            raise AssertionError(
                f"{label} not monotonically increasing: "
                f"{values[i]:.4f} at {levels[i]} rpd -> "
                f"{values[i + 1]:.4f} at {levels[i + 1]} rpd"
            )


def assert_stress_utilisation(utilisations, demand_levels, saturation_pct=60.0, plateau_tol_pct=3.0):
    """
    Utilisation should rise as demand increases, but may plateau once capacity-bound.

    Below saturation, each step must strictly increase. Above saturation, a small
    dip is allowed because extreme queues can reduce completed services per released
    hour within the collection window.
    """
    if utilisations[-1] < utilisations[0]:
        raise AssertionError(
            f"System utilisation at highest demand ({utilisations[-1]:.1f}%) "
            f"should exceed lowest demand ({utilisations[0]:.1f}%)"
        )
    for i in range(len(utilisations) - 1):
        if utilisations[i] >= saturation_pct:
            if utilisations[i + 1] < utilisations[i] - plateau_tol_pct:
                raise AssertionError(
                    "System utilisation dropped more than allowed once saturated: "
                    f"{utilisations[i]:.4f}% at {demand_levels[i]} rpd -> "
                    f"{utilisations[i + 1]:.4f}% at {demand_levels[i + 1]} rpd "
                    f"(tolerance {plateau_tol_pct:.1f}%-points)"
                )
        elif utilisations[i + 1] <= utilisations[i]:
            raise AssertionError(
                f"System utilisation not increasing below saturation: "
                f"{utilisations[i]:.4f}% at {demand_levels[i]} rpd -> "
                f"{utilisations[i + 1]:.4f}% at {demand_levels[i + 1]} rpd"
            )


def run_demand_stress_verification(
    demand_levels=(5, 10, 20),
    run_length=365,
    random_number_set=42,
):
    """
    Demand stress test: higher referral rates should increase pressure on the system.

    Runs fixed-capacity scenarios at increasing weekday referral rates and checks
    that peak queue and diagnosis RTT rise monotonically, and that utilisation
    increases with demand (allowing a small plateau once capacity is saturated).
    """
    print_header("5. DEMAND STRESS TEST")

    peak_queues = []
    diagnosis_rtts = []
    utilisations = []

    for rpd in demand_levels:
        exp = Experiment(
            auditor=Audit(),
            use_fixed_seed=True,
            random_number_set=random_number_set,
            iat=1.0 / rpd,
        )
        results = single_run(exp, rep=0, run_length=run_length, warmup_days=0)

        assert results["COHORT_DRAIN_COMPLETE"], (
            f"Drain incomplete at {rpd} referrals/day "
            f"(in system={results['IN_SYSTEM_END']})"
        )
        assert results["COHORT_RTT_VALID"], (
            f"RTT invalid at {rpd} referrals/day — backlog not cleared"
        )

        peak_queues.append(float(results["QUEUE_PEAK_ANY_STAGE"]))
        diagnosis_rtts.append(float(results["ACCESS_REFERRAL_TO_DIAGNOSIS_RTT_DAYS"]))
        utilisations.append(float(results["OVERALL_SYSTEM_UTILISATION"]))

        print(
            f"  {rpd:2d} rpd: peak queue={peak_queues[-1]:,.0f} | "
            f"diagnosis RTT={diagnosis_rtts[-1]:,.1f} d | "
            f"utilisation={utilisations[-1]:,.1f}%"
        )

    assert_monotonic_increasing(peak_queues, "Peak queue", demand_levels)
    assert_monotonic_increasing(diagnosis_rtts, "Diagnosis RTT", demand_levels)
    assert_stress_utilisation(utilisations, demand_levels)

    print(" -> SUCCESS: Queue and RTT increase with demand; utilisation shows expected stress response.")
