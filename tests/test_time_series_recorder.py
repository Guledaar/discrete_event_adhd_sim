"""Tests for TimeSeriesRecorder and monitor_process."""

import math

import pandas as pd
import pytest
import simpy

from adhd_simpy.Model.audit import Audit
from adhd_simpy.Model.experiment import Experiment
from adhd_simpy.Model.simulation import single_run
from adhd_simpy.Model.system import AutismPathwaySystem
from adhd_simpy.Model.time_series_recorder import (
    SimulationPhaseSchedule,
    TimeSeriesConfig,
    TimeSeriesRecorder,
    determine_current_phase,
    monitor_process,
    resolve_timeseries_interval,
)


def test_resolve_timeseries_interval_presets():
    assert resolve_timeseries_interval("daily") == 1.0
    assert resolve_timeseries_interval("weekly") == 7.0
    assert resolve_timeseries_interval("monthly") == 30.0
    assert resolve_timeseries_interval(None) == 30.0


def test_timeseries_config_should_record():
    default = TimeSeriesConfig()
    assert default.should_record("COLLECTION")
    assert not default.should_record("WARMUP")
    assert not default.should_record("DRAIN")

    full = TimeSeriesConfig.entire_simulation()
    for phase in ("WARMUP", "COLLECTION", "COOLDOWN", "DRAIN"):
        assert full.should_record(phase)


def test_determine_current_phase():
    schedule = SimulationPhaseSchedule(warmup_days=30, run_length=60, cooldown_days=10)
    assert determine_current_phase(0, schedule) == "WARMUP"
    assert determine_current_phase(30, schedule) == "COLLECTION"
    assert determine_current_phase(89, schedule) == "COLLECTION"
    assert determine_current_phase(90, schedule) == "COOLDOWN"
    assert determine_current_phase(99, schedule) == "COOLDOWN"
    assert determine_current_phase(100, schedule) == "DRAIN"

    no_cooldown = SimulationPhaseSchedule(warmup_days=0, run_length=20, cooldown_days=0)
    assert determine_current_phase(19, no_cooldown) == "COLLECTION"
    assert determine_current_phase(20, no_cooldown) == "DRAIN"


def test_recorder_rtt_nan_when_no_completions():
    auditor = Audit()
    schedule = SimulationPhaseSchedule(warmup_days=0, run_length=100)
    recorder = TimeSeriesRecorder(schedule, TimeSeriesConfig(interval_days=7))
    mean, median, count = recorder._rtt_snapshot(auditor, 50.0)
    assert math.isnan(mean)
    assert math.isnan(median)
    assert count == 0


def test_recorder_rtt_from_audit_events():
    auditor = Audit()
    auditor.rtt_events = [(10, "diagnosis", 400.0), (20, "diagnosis", 420.0), (5, "screening", 30.0)]
    schedule = SimulationPhaseSchedule(warmup_days=0, run_length=100)
    recorder = TimeSeriesRecorder(schedule, TimeSeriesConfig(interval_days=7))
    mean, median, count = recorder._rtt_snapshot(auditor, 25.0)
    assert mean == 410.0
    assert median == 410.0
    assert count == 2


def test_recorder_export_schema():
    schedule = SimulationPhaseSchedule(warmup_days=730, run_length=1825)
    recorder = TimeSeriesRecorder(schedule, TimeSeriesConfig(interval_days=30))
    recorder.observations = [
        {
            "day": 730,
            "phase": "COLLECTION",
            "queue_total": 2450,
            "queue_screening": 100,
            "queue_preassessment": 200,
            "queue_assessment": 800,
            "queue_further": 300,
            "queue_postdiagnosis": 400,
            "queue_other": 350,
            "queue_review": 300,
            "mean_rtt": 410.0,
            "median_rtt": 405.0,
            "completed_rtt_count": 12,
            "assessment_utilisation": 91.2,
            "screening_utilisation": 88.0,
            "preassessment_utilisation": 90.0,
            "further_utilisation": 85.0,
            "postdiagnosis_utilisation": 80.0,
            "other_utilisation": 75.0,
            "review_utilisation": 70.0,
            "arrivals": 500,
            "diagnoses_completed": 12,
            "patients_in_system": 120,
        }
    ]
    df = recorder.to_dataframe()
    assert list(df.columns) == list(
        TimeSeriesRecorder(
            SimulationPhaseSchedule(warmup_days=0, run_length=1),
            TimeSeriesConfig(),
        ).to_dataframe().columns
    )
    csv_text = recorder.to_csv(compact=True)
    assert "Day,Queue,RTT,Assessment Utilisation" in csv_text
    assert "730,2450,410.0,91.2" in csv_text


def test_monitor_samples_only_during_collection_by_default():
    auditor = Audit()
    experiment = Experiment(auditor=auditor)
    results = single_run(
        experiment,
        rep=0,
        warmup_days=30.0,
        run_length=60.0,
        max_drain_days=30.0,
        timeseries_interval=10,
    )
    monitor = results["_timeseries_monitor"]
    df = monitor["timeseries_monitor"]
    assert not df.empty
    assert (df["phase"] == "COLLECTION").all()
    assert (df["day"] >= 30).all()
    assert (df["day"] < 90).all()


def test_monitor_records_drain_when_enabled():
    auditor = Audit()
    experiment = Experiment(auditor=auditor)
    config = TimeSeriesConfig(interval_days=5, record_drain=True, record_collection=False)
    results = single_run(
        experiment,
        rep=0,
        warmup_days=0.0,
        run_length=5.0,
        max_drain_days=200.0,
        timeseries_config=config,
    )
    df = results["_timeseries_monitor"]["timeseries_monitor"]
    assert (df["phase"] == "DRAIN").all()
    assert df["day"].min() >= 5


def test_monitor_disabled_when_config_none():
    auditor = Audit()
    experiment = Experiment(auditor=auditor)
    results = single_run(
        experiment,
        rep=0,
        warmup_days=0.0,
        run_length=20.0,
        max_drain_days=10.0,
        timeseries_config=None,
    )
    assert "_timeseries_monitor" not in results


def test_monitor_records_warmup_when_enabled():
    auditor = Audit()
    experiment = Experiment(auditor=auditor)
    config = TimeSeriesConfig(interval_days=10, record_warmup=True, record_collection=False)
    results = single_run(
        experiment,
        rep=0,
        warmup_days=30.0,
        run_length=30.0,
        max_drain_days=10.0,
        timeseries_config=config,
    )
    df = results["_timeseries_monitor"]["timeseries_monitor"]
    assert (df["phase"] == "WARMUP").all()
    assert df["day"].max() < 30


def test_monitor_records_cooldown_phase():
    auditor = Audit()
    experiment = Experiment(auditor=auditor)
    config = TimeSeriesConfig(interval_days=5, record_cooldown=True, record_collection=False)
    results = single_run(
        experiment,
        rep=0,
        warmup_days=0.0,
        run_length=20.0,
        cooldown_days=10.0,
        max_drain_days=5.0,
        timeseries_config=config,
    )
    df = results["_timeseries_monitor"]["timeseries_monitor"]
    assert (df["phase"] == "COOLDOWN").all()
    assert df["day"].min() >= 20
    assert df["day"].max() < 30


@pytest.mark.parametrize("interval", ["daily", "weekly", "monthly", 15])
def test_monitor_accepts_interval_presets(interval):
    auditor = Audit()
    experiment = Experiment(auditor=auditor)
    results = single_run(
        experiment,
        rep=0,
        warmup_days=0.0,
        run_length=45.0,
        max_drain_days=10.0,
        timeseries_interval=interval,
    )
    meta = results["_timeseries_monitor"]["timeseries_monitor_meta"]
    assert meta["interval_days"] == resolve_timeseries_interval(interval)
    assert isinstance(results["_timeseries_monitor"]["timeseries_monitor"], pd.DataFrame)


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
