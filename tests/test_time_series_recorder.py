"""Local smoke tests for the DES simulation and audit support."""

import pandas as pd

from des.audit import Audit
from des.experiment import Experiment
from des.runners import single_run


def test_audit_update_and_finalize():
    audit = Audit()
    audit.update_patient(1, arrival_time=0.0)
    audit.update_patient(1, triage_outcome="accepted")
    audit.update_patient(1, assessment_start=2.0)
    df = audit.finalize()

    assert list(df.columns) == [
        "patient_id",
        "arrival_time",
        "triage_outcome",
        "admin_removal",
        "assessment_start",
        "assessment_completion",
        "diagnosis",
        "support_type",
        "exit_time",
        "exit_route",
        "appointments_required",
        "appointments_completed",
        "clinician_hours_consumed",
        "assessment_hours_consumed",
        "workshop_hours_consumed",
        "workshop_join_time",
        "workshop_start_time",
        "workshop_completion",
        "workshop_group_id",
    ]
    assert df.loc[0, "arrival_time"] == 0.0
    assert df.loc[0, "triage_outcome"] == "accepted"
    assert df.loc[0, "assessment_start"] == 2.0


def test_single_run_smoke_creates_report():
    exp = Experiment(audit=Audit(), use_fixed_seed=True, iat=10.0)
    patients, capacity, model_params, report = single_run(
        exp,
        rep=0,
        run_length=30,
        warm_up=0,
        flow_window_days=30.0,
    )

    assert isinstance(patients, pd.DataFrame)
    assert isinstance(capacity, pd.DataFrame)
    assert "arrival_time" in patients.columns
    assert "hours_released" in capacity.columns
    assert hasattr(report, "pathway_funnel")
    assert hasattr(report, "activity_flow")
    assert report.sim_end == 30.0


def test_single_run_with_same_seed_is_reproducible():
    exp = Experiment(audit=Audit(), use_fixed_seed=True, iat=5.0)
    run1 = single_run(exp, rep=0, run_length=20, warm_up=0, flow_window_days=20.0)
    run2 = single_run(exp, rep=0, run_length=20, warm_up=0, flow_window_days=20.0)

    patients1, _, _, report1 = run1
    patients2, _, _, report2 = run2
    assert patients1.shape == patients2.shape
    assert report1.pathway_funnel.equals(report2.pathway_funnel)
    assert report1.capacity_utilisation.equals(report2.capacity_utilisation)


def test_record_includes_patients_in_system():
    auditor = Audit()
    exp = Experiment(auditor=auditor)
    exp.set_random_no_set(0)
    env = simpy.Environment()
    system = AutismPathwaySystem(env, exp, collection_start=0, arrival_stop=30)
    schedule = SimulationPhaseSchedule(warmup_days=0, run_length=30)
    recorder = TimeSeriesRecorder(schedule, TimeSeriesConfig(record_collection=True))
    exp.results["ARRIVED_ALL"] = 10
    exp.results["EXIT_ALL"] = 4
    obs = recorder.record(system)
    assert obs["patients_in_system"] == 6
