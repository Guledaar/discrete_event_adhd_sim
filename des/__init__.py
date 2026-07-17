"""NHS neurodevelopmental assessment pathway discrete-event simulation.

Calibration / baseline / policy analysis use the independent three-run
framework in ``des.runs`` (see ``scripts/run1_*.py`` … ``run3_*.py``).
"""

from des.audit import Audit, RTT_18_WEEKS_DAYS
from des.collection_window import CollectionWindow, SimulationPhases
from des.config import (
    ASSESSMENT_APPOINTMENT_COUNTS,
    ASSESSMENT_APPOINTMENT_PROBS,
    ASSESSMENT_GAP_DAYS,
    CALIBRATED_WORKFORCE_HOURS_PER_DAY,
    COLLECTION_DAYS,
    DEFAULT_RESULTS_COLLECTION_PERIOD,
    DEFAULT_RND_SET,
    DURATION_ASSESSMENT,
    DURATION_WORKSHOP_SESSION,
    IAT_WEEKDAY,
    N_REP,
    N_STREAMS,
    PCT_ADMIN_REMOVAL,
    PCT_DIAGNOSIS,
    PCT_REFERRAL_REJECTED,
    PCT_VIRTUAL_SUPPORT,
    REFERRALS_PER_DAY,
    SCENARIO_PRESETS,
    WARMUP_DAYS,
    WARM_UP_PERIOD,
    WORKFORCE_HOURS_PER_DAY,
    WORKFORCE_HOURS_WORKSHOP_SESSION,
    WORKSHOP_GROUP_SIZE,
    WORKSHOP_MAX_WAIT_DAYS,
    WORKSHOP_NUM_SESSIONS,
    WORKSHOP_SESSION_INTERVAL_WEEKS,
)
from des.experiment import Experiment
from des.patient import Patient
from des.kpi import (
    KPIValidationError,
    RTT_52_WEEKS_DAYS,
    RunResult,
    compute_kpis,
    kpi_from_audit,
)
from des.reporting import export_run_result
from des.kpi_docs import (
    KPI_CALCULATIONS,
    KPI_GLOSSARY,
    display_kpi_results_reference,
    display_rtt_kpi_definitions,
    kpi_glossary_table,
    kpi_results_reference,
    rtt_kpi_definitions_table,
)
from des.model_docs import (
    MODEL_GLOSSARY,
    MODEL_PARAMETER_DEFINITIONS,
    model_glossary_table,
    model_parameter_table,
)
from des.runner import multiple_replications, single_run
from des.runs import (
    ProviderRunConfig,
    load_matching_period,
    load_provider_run_config,
    save_baseline_results,
    save_matching_period,
    save_policy_results,
)
from des.system import AutismPathwaySystem
from des.trace import disable_trace, enable_trace, is_tracing, tracing
from des.workforce import WorkforceHoursResource
from des.workshop_group import WorkshopGroup


def run_all_verifications() -> None:
    """
    Run every built-in verification suite.

    Notes
    -----
    Thin wrapper around :func:`des.verification.run_all_verifications`.
    """
    from des.verification import run_all_verifications as _run_all_verifications

    _run_all_verifications()


__all__ = [
    "Audit",
    "KPI_GLOSSARY",
    "KPI_CALCULATIONS",
    "MODEL_GLOSSARY",
    "MODEL_PARAMETER_DEFINITIONS",
    "kpi_glossary_table",
    "model_glossary_table",
    "model_parameter_table",
    "rtt_kpi_definitions_table",
    "display_rtt_kpi_definitions",
    "kpi_results_reference",
    "display_kpi_results_reference",
    "RunResult",
    "KPIValidationError",
    "compute_kpis",
    "kpi_from_audit",
    "export_run_result",
    "AutismPathwaySystem",
    "CollectionWindow",
    "SimulationPhases",
    "Experiment",
    "Patient",
    "WorkforceHoursResource",
    "WorkshopGroup",
    "multiple_replications",
    "run_all_verifications",
    "single_run",
    "ProviderRunConfig",
    "load_provider_run_config",
    "load_matching_period",
    "save_matching_period",
    "save_baseline_results",
    "save_policy_results",
    "enable_trace",
    "disable_trace",
    "is_tracing",
    "tracing",
    "ASSESSMENT_APPOINTMENT_COUNTS",
    "ASSESSMENT_APPOINTMENT_PROBS",
    "ASSESSMENT_GAP_DAYS",
    "CALIBRATED_WORKFORCE_HOURS_PER_DAY",
    "COLLECTION_DAYS",
    "DEFAULT_RESULTS_COLLECTION_PERIOD",
    "DEFAULT_RND_SET",
    "DURATION_ASSESSMENT",
    "DURATION_WORKSHOP_SESSION",
    "IAT_WEEKDAY",
    "N_REP",
    "N_STREAMS",
    "PCT_ADMIN_REMOVAL",
    "PCT_DIAGNOSIS",
    "PCT_REFERRAL_REJECTED",
    "PCT_VIRTUAL_SUPPORT",
    "REFERRALS_PER_DAY",
    "SCENARIO_PRESETS",
    "WARMUP_DAYS",
    "WARM_UP_PERIOD",
    "WORKFORCE_HOURS_PER_DAY",
    "WORKFORCE_HOURS_WORKSHOP_SESSION",
    "WORKSHOP_GROUP_SIZE",
    "WORKSHOP_MAX_WAIT_DAYS",
    "WORKSHOP_NUM_SESSIONS",
    "WORKSHOP_SESSION_INTERVAL_WEEKS",
    "RTT_18_WEEKS_DAYS",
    "RTT_52_WEEKS_DAYS",
]
