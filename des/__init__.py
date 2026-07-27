"""NHS neurodevelopmental assessment pathway — discrete-event simulation.

Overview
--------
This package implements a **discrete-event simulation (DES)** of the NHS
neurodevelopmental (autism/ADHD) assessment pathway using SimPy. Referrals
arrive over time, consume shared weekday **clinician hours**, and progress
through triage, assessment, diagnosis, and exit routes (virtual support or
clinical workshops).

Data flow during a run:

1. :class:`~des.system.AutismPathwaySystem` generates referrals and spawns
   :class:`~des.patient.Patient` processes.
2. :class:`~des.audit.Audit` records milestones and daily capacity balances.
3. :func:`~des.run_report.build_run_report` derives KPI tables from audit
   exports (stock at horizon + flow in a rolling window).
4. :mod:`des.runners` wraps replication, calibration (Run 1), baseline CIs
   (Run 2), and policy decay (Run 3).

Submodules
----------
audit
    :class:`~des.audit.PatientRecord` and :class:`~des.audit.Audit`.
collection_window
    :class:`~des.collection_window.CollectionWindow` and
    :class:`~des.collection_window.SimulationPhases` (Run 3).
config
    Default model parameters and :data:`~des.config.SCENARIO_PRESETS`.
distributions
    Seeded wrappers around NumPy RNGs (:class:`~des.distributions.Exponential`, …).
experiment
    :class:`~des.experiment.Experiment` — scenario, RNG streams, Run 3 overrides.
patient
    Single-patient pathway SimPy generator.
system
    :class:`~des.system.AutismPathwaySystem`.
workforce
    :class:`~des.workforce.WorkforceHoursResource` — priority hour scheduling.
workshop_manager, workshop_group
    Workshop waiting list, group formation, and session series.
run_report
    :class:`~des.run_report.RunReport`, :func:`~des.run_report.build_run_report`,
    :func:`~des.run_report.kpi_snapshot`.
runners
    ``single_run``, ``multiple_replication``, ``run1``, ``run2``, ``run3``.
steady_state
    :func:`~des.steady_state.count_backlog_in_system`.
verification
    :func:`~des.verification.run_all_verifications` and structural suites.
trace
    Optional pathway debug logging (:func:`~des.trace.enable_trace`).

Notes
-----
Human-readable KPI and parameter names: ``GLOSSARY.md`` at the repository root.
Docstrings in this package follow the **NumPy** convention (``Parameters``,
``Returns``, ``Attributes``, ``Raises``, ``Notes``).
"""

__version__ = "1.0.0"
