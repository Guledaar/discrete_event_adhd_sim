"""Optional JSON config → Experiment kwargs (CLI / legacy). Prefer Experiment API."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from des.audit import Audit
from des.experiment import Experiment

PathLike = Union[str, Path]

# Re-export aliases used by matching (kept here so run.py stays focused on the engine).
MATCHABLE_KPI_MAP = {
    "waiting_list_size": "waiting_list_size_all_in_system",
    "waiting_list_stock": "waiting_list_size_all_in_system",
    "waiting_list": "waiting_list_size_all_in_system",
    "waiting_list_size_all_in_system": "waiting_list_size_all_in_system",
    "rtt_incomplete_mean_days": "rtt_incomplete_mean_days",
    "rtt_incomplete": "rtt_incomplete_mean_days",
    "rtt_complete_mean_days": "mean_overall_rtt_days",
    "mean_overall_rtt_days": "mean_overall_rtt_days",
    "referral_to_first_assessment_mean_days": "referral_to_first_assessment_mean_days",
    "assessments_per_month": "assessments_per_month",
    "diagnoses_per_month": "diagnoses_per_month",
    "utilisation": "overall_clinician_utilisation",
    "utilization": "overall_clinician_utilisation",
    "overall_clinician_utilisation": "overall_clinician_utilisation",
    "workshop_utilisation": "workshop_utilisation",
}
DEFAULT_KPI_MAP = dict(MATCHABLE_KPI_MAP)
FIXED_INPUT_KPIS = frozenset({
    "referrals_per_day", "accept_rate", "reject_rate", "iat",
    "pct_referral_rejected", "pct_admin_removal", "admin_removal",
    "pct_diagnosis", "pct_virtual_support", "workforce_hours_per_day", "capacity",
})


@dataclass
class ProviderRunConfig:
    """
    All parameters needed to execute the three-run framework for one provider.

    A ``ProviderRunConfig`` is typically loaded from a JSON file via
    :func:`load_provider_run_config` and passed to ``execute_run1/2/3``.

    Attributes
    ----------
    provider_id : str
        Identifier for the provider (used in output filenames).
    operational : dict[str, Any]
        Flat operational parameters that override experiment defaults
        (e.g. ``referrals_per_day``, ``workforce_hours_per_day``).
    provider_targets : dict[str, float]
        KPI targets used for MAPE calibration in Run 1.
    mape_weights : dict[str, float]
        Per-KPI weights for the aggregate MAPE calculation.
    kpi_map : dict[str, str]
        Alias map from user-friendly names to internal KPI keys.
    step_days : float
        Calibration horizon step size in days.
    min_period_days : float
        Minimum candidate matching period in days.
    max_period_days : float
        Maximum candidate matching period (best-effort cap) in days.
    rolling_window_days : float
        Length of the rolling KPI window used during calibration.
    calibration_seed : int
        RNG seed used for the single calibration run.
    match_tolerance : float
        Aggregate MAPE threshold; calibration stops when MAPE ≤ tolerance.
    n_reps : int
        Number of independent replication seeds for Run 2.
    confidence_level : float
        Confidence level for Run 2 KPI intervals (e.g. ``0.95``).
    baseline_seeds : list[int], optional
        Explicit seed list for Run 2; derived from ``n_reps`` when ``None``.
    baseline_kpis : list[str]
        KPIs to include in the Run 2 confidence-interval summary.
    decay_period_days : float
        Simulation time after T* in Run 3 (policy decay window).
    policy_packages : dict[str, dict[str, Any]]
        Named sets of Experiment overrides applied at SwitchTime in Run 3.
    policy_id : str
        Default policy package to run.
    policy_seed : int
        RNG seed for the Run 3 policy arm.
    include_control_arm : bool
        When ``True``, also run the empty-override control arm in Run 3.
    output_dir : str
        Directory for all output artefacts.
    matching_period_filename : str
        Filename for the Run 1 matching-period JSON output.
    baseline_filename : str
        Filename for the Run 2 baseline JSON output.
    policy_filename : str
        Filename for the Run 3 policy JSON output.
    random_number_set : int
        Base RNG seed for the experiment.
    use_fixed_seed : bool
        Whether to use reproducible seeds.
    """
    provider_id: str = "provider"
    operational: Dict[str, Any] = field(default_factory=dict)
    provider_targets: Dict[str, float] = field(default_factory=dict)
    mape_weights: Dict[str, float] = field(default_factory=dict)
    kpi_map: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_KPI_MAP))
    step_days: float = 30.0
    min_period_days: float = 90.0
    max_period_days: float = 365.0 * 5
    rolling_window_days: float = 365.0
    calibration_seed: int = 0
    match_tolerance: float = 0.05
    n_reps: int = 20
    confidence_level: float = 0.95
    baseline_seeds: Optional[List[int]] = None
    baseline_kpis: List[str] = field(default_factory=lambda: [
        "waiting_list_size_all_in_system", "waiting_list_size",
        "rtt_incomplete_mean_days", "rtt_completed_mean_days",
        "referral_to_first_assessment_mean_days",
        "assessments_per_month", "diagnoses_per_month",
        "overall_clinician_utilisation", "workshop_utilisation",
    ])
    decay_period_days: float = 365.0 * 2
    policy_packages: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    policy_id: str = "increase_capacity"
    policy_seed: int = 0
    include_control_arm: bool = True
    output_dir: str = "run_output"
    matching_period_filename: str = "optimal_matching_period.json"
    baseline_filename: str = "stochastic_baseline.json"
    policy_filename: str = "policy_branching.json"
    random_number_set: int = 42
    use_fixed_seed: bool = True

    def baseline_seed_list(self) -> List[int]:
        """
        Return the list of RNG seeds to use for Run 2 replications.

        Returns
        -------
        list[int]
            Explicit ``baseline_seeds`` when set; otherwise
            ``list(range(n_reps))``.
        """
        if self.baseline_seeds is not None:
            return [int(s) for s in self.baseline_seeds]
        return list(range(int(self.n_reps)))

    def matching_period_path(self) -> Path:
        """
        Return the full path for the Run 1 matching-period JSON artefact.

        Returns
        -------
        pathlib.Path
        """
        return Path(self.output_dir) / self.matching_period_filename

    def baseline_path(self) -> Path:
        """
        Return the full path for the Run 2 baseline JSON artefact.

        Returns
        -------
        pathlib.Path
        """
        return Path(self.output_dir) / self.baseline_filename

    def policy_path(self) -> Path:
        """
        Return the full path for the Run 3 policy JSON artefact.

        Returns
        -------
        pathlib.Path
        """
        return Path(self.output_dir) / self.policy_filename

    def resolve_policy(self, policy_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Look up and return a copy of the named policy package overrides.

        Parameters
        ----------
        policy_id : str, optional
            Key in :attr:`policy_packages`.  Defaults to :attr:`policy_id`.

        Returns
        -------
        dict[str, Any]
            A shallow copy of the policy override dict.

        Raises
        ------
        KeyError
            If *policy_id* is not found in :attr:`policy_packages`.
        """
        pid = policy_id or self.policy_id
        if pid not in self.policy_packages:
            raise KeyError(f"Unknown policy_id={pid!r}. Available: {list(self.policy_packages)}")
        return dict(self.policy_packages[pid])

    def to_experiment_kwargs(self) -> Dict[str, Any]:
        """
        Convert :attr:`operational` parameters to :class:`~des.experiment.Experiment` keyword arguments.

        Handles aliases (e.g. ``referrals_per_day`` → ``iat``,
        ``accept_rate`` → ``pct_referral_rejected``) and auto-normalises
        appointment probabilities that do not sum to exactly 1.

        Returns
        -------
        dict[str, Any]
            Keyword arguments suitable for ``Experiment(**kwargs)``.
        """
        op = dict(self.operational)
        kw: Dict[str, Any] = {
            "random_number_set": int(op.get("random_number_set", self.random_number_set)),
            "use_fixed_seed": bool(op.get("use_fixed_seed", self.use_fixed_seed)),
        }
        if "referrals_per_day" in op:
            kw["iat"] = 1.0 / float(op["referrals_per_day"])
        if "iat" in op:
            kw["iat"] = float(op["iat"])
        if "accept_rate" in op:
            kw["pct_referral_rejected"] = 1.0 - float(op["accept_rate"])
        aliases = (
            ("pct_referral_rejected", "pct_referral_rejected", float),
            ("admin_removal", "pct_admin_removal", float),
            ("pct_admin_removal", "pct_admin_removal", float),
            ("capacity", "workforce_hours_per_day", float),
            ("workforce_hours_per_day", "workforce_hours_per_day", float),
            ("pct_diagnosis", "pct_diagnosis", None),
            ("pct_virtual_support", "pct_virtual_support", None),
            ("assessment_gap_days", "assessment_gap_days", None),
            ("workshop_group_size", "workshop_group_size", None),
            ("duration_assessment", "duration_assessment", None),
            ("assessment_appointment_counts", "assessment_appointment_counts", None),
            ("assessment_appointment_probs", "assessment_appointment_probs", None),
        )
        for src, dst, cast in aliases:
            if src in op:
                kw[dst] = cast(op[src]) if cast else op[src]
        if "assessment_appointment_probs" in kw:
            probs = [float(p) for p in kw["assessment_appointment_probs"]]
            total = sum(probs)
            if total > 0 and abs(total - 1.0) > 1e-9:
                kw["assessment_appointment_probs"] = [p / total for p in probs]
        return kw


def setup_experiment(config: ProviderRunConfig, name: str, *, seed: Optional[int] = None) -> Experiment:
    """
    Construct a ready-to-run :class:`~des.experiment.Experiment` from a config.

    Parameters
    ----------
    config : ProviderRunConfig
        Provider run configuration supplying operational parameters.
    name : str
        Scenario name assigned to the experiment.
    seed : int, optional
        RNG seed override applied via
        :meth:`~des.experiment.Experiment.set_random_no_set`.

    Returns
    -------
    Experiment
        Initialised experiment with a fresh audit.
    """
    exp = Experiment(audit=Audit(), scenario_name=name, **config.to_experiment_kwargs())
    if seed is not None and exp.use_fixed_seed:
        exp.set_random_no_set(int(seed))
    return exp


def _flat_op(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten a nested operational config dict into a single-level dict.

    Recognises optional top-level section keys (``demand_triage``,
    ``assessment_pathway``, ``clinical_outcomes``, ``rng_settings``) and
    merges them.  Also renames legacy field aliases to their canonical names.

    Parameters
    ----------
    raw : dict[str, Any]
        Raw operational block from the provider JSON config.

    Returns
    -------
    dict[str, Any]
        Flat operational dict with canonical key names.
    """
    sections = ("demand_triage", "assessment_pathway", "clinical_outcomes", "rng_settings")
    if not any(k in raw for k in sections):
        return dict(raw)
    flat: Dict[str, Any] = {}
    for s in sections:
        block = raw.get(s)
        if isinstance(block, dict):
            flat.update(block)
    for src, dst in (
        ("admin_removal_probability", "admin_removal"),
        ("appointment_counts", "assessment_appointment_counts"),
        ("appointment_probs", "assessment_appointment_probs"),
        ("random_seed", "random_number_set"),
    ):
        if src in flat and dst not in flat:
            flat[dst] = flat.pop(src)
        elif src in flat:
            flat.pop(src)
    return flat


def load_provider_run_config(path: PathLike) -> ProviderRunConfig:
    """
    Parse a provider run JSON file into a :class:`ProviderRunConfig`.

    Supports both the nested format (with ``calibration`` / ``operational``
    top-level keys) and the flat legacy format.

    Parameters
    ----------
    path : str or pathlib.Path
        Path to the JSON configuration file.

    Returns
    -------
    ProviderRunConfig
        Fully populated configuration dataclass.
    """
    raw = json.loads(Path(path).read_text())
    cal = dict(raw.get("calibration", {}))
    op = _flat_op(dict(raw.get("operational", {})))

    def pick(key: str, default: Any) -> Any:
        return raw.get(key, cal.get(key, default))

    targets = raw["provider_targets"] if "provider_targets" in raw else cal.get("provider_targets", {})
    weights = raw["mape_weights"] if "mape_weights" in raw else cal.get("mape_weights", {})
    targets = {
        k: float(v) for k, v in targets.items()
        if k not in FIXED_INPUT_KPIS and MATCHABLE_KPI_MAP.get(k, k) not in FIXED_INPUT_KPIS
    }
    weights = {k: float(v) for k, v in weights.items() if k in targets or k not in FIXED_INPUT_KPIS}

    return ProviderRunConfig(
        provider_id=str(raw.get("provider_id", "provider")),
        operational=op,
        provider_targets=targets,
        mape_weights=weights,
        kpi_map={**DEFAULT_KPI_MAP, **dict(raw.get("kpi_map", {}))},
        step_days=float(pick("step_days", 30)),
        min_period_days=float(pick("min_period_days", 90)),
        max_period_days=float(pick("max_period_days", 365 * 5)),
        rolling_window_days=float(pick("rolling_window_days", 365)),
        calibration_seed=int(pick("calibration_seed", 0)),
        match_tolerance=float(pick("match_tolerance", 0.05)),
        n_reps=int(raw.get("n_reps", 20)),
        confidence_level=float(raw.get("confidence_level", 0.95)),
        baseline_seeds=list(raw["baseline_seeds"]) if raw.get("baseline_seeds") else None,
        baseline_kpis=list(raw.get("baseline_kpis", ProviderRunConfig().baseline_kpis)),
        decay_period_days=float(raw.get("decay_period_days", 365 * 2)),
        policy_packages={k: dict(v) for k, v in raw.get("policy_packages", {}).items()},
        policy_id=str(raw.get("policy_id", "increase_capacity")),
        policy_seed=int(raw.get("policy_seed", 0)),
        include_control_arm=bool(raw.get("include_control_arm", True)),
        output_dir=str(raw.get("output_dir", "run_output")),
        matching_period_filename=str(raw.get("matching_period_filename", "optimal_matching_period.json")),
        baseline_filename=str(raw.get("baseline_filename", "stochastic_baseline.json")),
        policy_filename=str(raw.get("policy_filename", "policy_branching.json")),
        random_number_set=int(op.get("random_number_set", raw.get("random_number_set", 42))),
        use_fixed_seed=bool(op.get("use_fixed_seed", raw.get("use_fixed_seed", True))),
    )
