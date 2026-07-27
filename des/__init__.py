"""NHS neurodevelopmental assessment pathway — discrete-event simulation.

This package implements a SimPy-based DES of referral → triage → assessment →
diagnosis → support, with KPI reporting via :mod:`des.run_report` and the
three-run calibration / baseline / policy framework in :mod:`des.runners`.

Submodules
----------
experiment
    Scenario configuration and parameter overrides.
system
    SimPy processes and pathway logic.
run_report
    KPI tables and :func:`~des.run_report.build_run_report`.
runners
    Run 1 (calibration), Run 2 (baseline), Run 3 (policy) entry points.
"""
