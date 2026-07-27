# NHS Neurodevelopmental Assessment Pathway — Discrete Event Simulation

Discrete-event simulation (DES) for modelling **NHS neurodevelopmental (autism/ADHD)
assessment** pathway flow, waiting lists (Patient Tracking List / PTL), workforce
capacity, referral-to-treatment (RTT) clocks, and policy interventions.

**Primary entry point:** Streamlit app in [`streamlit_app/`](streamlit_app/) (`streamlit run streamlit_app/app.py`)

**Parameter and KPI definitions:** [`GLOSSARY.md`](GLOSSARY.md) (also **Glossary** in the Streamlit app sidebar).

## What the model does

Referrals arrive over time, pass triage and administrative review, compete for a
**shared weekday clinician-hour pool**, complete multi-appointment assessments, receive
a diagnostic outcome, and exit via virtual support or a **clinical workshop group** pathway.

The simulation answers:

- How large will the waiting list grow, and how long do patients wait?
- What simulation horizon matches an observed PTL target (calibration)?
- Which levers — **more capacity** or **higher administrative removal** — reduce backlog
  and improve 18-week / 52-week waiting-time standards?

## How results are produced

All KPIs come from the audit tables written during simulation. The pipeline is:

```
Experiment → AutismPathwaySystem → Audit → build_run_report → RunReport
```

| Step | Module | What you get |
|------|--------|--------------|
| Run simulation | `des/runners.py` → `single_run` | `patients`, `capacity`, `model_params`, `report` |
| Build KPIs | `des/run_report.py` → `build_run_report` | `RunReport` with 8 DataFrame sections |
| Many seeds | `des/runners.py` → `multiple_replication` | list of single-run tuples |
| Summarise reps | `des/runners.py` → `summarise_replications` | mean / SD / 95% CI per KPI |
| PTL count at time *t* | `des/steady_state.py` → `count_backlog_in_system` | backlog census (Run 3) |

### Single run (`demo1.ipynb`)

```python
from des.audit import Audit
from des.experiment import Experiment
from des.runners import single_run

experiment_0 = Experiment(audit=Audit(), ..., **NOTEBOOK_EXPERIMENT_PARAMETERS)

patients, capacity, model_params, report = single_run(
    experiment_0,
    rep=0,
    run_length=365 * 18,
    warm_up=0,
    flow_window_days=365.0,
)
```

`report` is a `RunReport` object. Display sections directly:

- `report.pathway_funnel` — cohort counts at horizon
- `report.pathway_exits` — exits (all time and flow window)
- `report.capacity_utilisation` — workforce hours used / unused
- `report.waits_stock_by_stage` — waits for patients still in system at horizon
- `report.rtt_waits_stock`, `report.rtt_breaches_stock` — RTT performance and 18/52-week breaches
- `report.waits_flow_by_stage` — waits for milestones in the rolling flow window
- `report.activity_flow` — event counts (referrals, assessments, diagnoses, etc.)
- `report.model_params` — scenario parameters

### Multiple replications (`demo1.ipynb`)

```python
from des.runners import multiple_replication, summarise_replications

results = multiple_replication(
    experiment_0,
    n_reps=5,
    run_length=RUN_LENGTH,
    warm_up=0,
    flow_window_days=365.0,
)

replication_report = summarise_replications(results)
```

Each element of `results` is the same 4-tuple as `single_run`.  
`summarise_replications` returns a `ReplicationReport` — one DataFrame per KPI section
with columns `stat`, `n`, `mean`, `sd`, `ci_lower`, `ci_upper`.

## Three-run framework

The notebook runs three analyses in sequence. All three use `des/runners.py`; Run 2 and
Run 3 reuse the matching period **T\*** from Run 1.

| Run | Purpose | Function | Main outputs |
|-----|---------|----------|--------------|
| **Run 1** | Calibration | `run1` | **T\*** — horizon where simulated KPIs match provider targets |
| **Run 2** | Stochastic baseline | `run2` | `summary` (CI across reps) + `kpi_snapshots` at T\* |
| **Run 3** | Policy analysis | `run3` | Backlog decay after a policy switch at T\* |

### Run 1 — find matching period T\*

Run 1 repeatedly calls `single_run` at increasing horizons until key KPIs are within
a tolerance (MAPE) of provider targets — typically PTL size and mean incomplete RTT.

```python
from des.runners import run1, kpi_snapshot

run1_result = run1(
    experiment_0,
    targets={"backlog_patients_at_horizon": 2800},
    max_period_days=365 * 20,
    step_days=365,
    min_period_days=365,
    match_tolerance=0.05,
    flow_window_days=365.0,
)

T_STAR = run1_result["optimal_matching_period_days"]
run1_result["history"]          # checkpoint table per horizon tried
run1_result["best_checkpoint"]  # lowest-MAPE row if no exact match
```

### Run 2 — stochastic baseline at T\*

Run 2 wraps `multiple_replication` + `summarise_replications` at horizon T\*.

```python
from des.runners import run2

run2_result = run2(
    experiment_0,
    matching_period_days=T_STAR,
    n_reps=5,
    flow_window_days=365.0,
)

run2_result["summary"]         # ReplicationReport — same sections as above
run2_result["kpi_snapshots"]   # one flat KPI row per replication
```

### Run 3 — policy switch and backlog decay

Run 3 runs one continuous simulation to T\*, applies parameter overrides (e.g. double
capacity), continues for a **decay horizon**, and compares waiting-list change against
a control arm with no policy change. Pass `n_reps=5` to replicate the **policy arm**
only; the baseline control always runs **once**.

```python
from des.runners import run3

run3_result = run3(
    experiment_0,
    matching_period_days=T_STAR,
    decay_period_days=365,
    policy_overrides={"workforce_hours_per_day": 14},
    n_reps=5,
    include_control=True,
)

run3_result["policy_summary"]["metrics_summary"]  # policy mean / 95% CI
run3_result["policy_arm"]["backlog_decay"]
run3_result["policy_arm"]["backlog_at_end"]
run3_result["comparison_summary"]                 # policy reps vs one baseline
```

Policy examples: increase `workforce_hours_per_day`, raise `pct_admin_removal`, or
combine capacity with different decay horizons.

## Pathway (current model)

1. Referral arrival (weekday inter-arrivals)
2. Triage (referral rejected or accepted)
3. Administrative review (admin removal)
4. Multi-appointment assessment (shared capacity bottleneck)
5. Diagnostic outcome (diagnosis / no diagnosis)
6. Post-diagnosis support — **virtual** (quick exit) or **clinical workshop** (group sessions)
7. Exit — RTT clock stops; incomplete pathways count on the **PTL**

## Architecture

| Module | Role |
|--------|------|
| `config.py` | Global defaults — demand, branching, capacity, workshop settings |
| `experiment.py` | Scenario configuration, RNG streams, intervention overrides |
| `patient.py` | Individual referral SimPy processes |
| `workforce.py` | `WorkforceHoursResource` — shared weekday clinician-hour pool |
| `workshop_manager.py` / `workshop_group.py` | Group workshop waiting list and sessions |
| `system.py` | `AutismPathwaySystem` — referral generation and coordination |
| `audit.py` | Patient record store during simulation |
| `run_report.py` | `build_run_report()` — KPI sections from audit tables |
| `runners.py` | `single_run`, `multiple_replication`, `summarise_replications`, `run1`/`run2`/`run3` |
| `steady_state.py` | Waiting-list census at a simulation time |
| `verification.py` | Model V&V suites (`python -m des.verification`) |
| `distributions.py` | Seeded stochastic distributions |

### Stock vs flow vs throughput

- **Stock waits** — snapshot at simulation end (who is still waiting, and for how long)
- **Flow waits** — patients whose milestone fell in the last `flow_window_days`
- **Throughput** — count of events (all time and in the flow window)

These can differ: a long horizon produces a large incomplete stock RTT mean, while flow
RTT reflects only recent completions.

## Repository layout

```
autsim_des/
├── README.md
├── LICENSE
├── environment.yaml
├── GLOSSARY.md
├── streamlit_app/           # Run 1–3 UI (primary)
├── des/
│   ├── audit.py, experiment.py, patient.py, system.py
│   ├── workforce.py, workshop_manager.py, workshop_group.py
│   ├── run_report.py, runners.py, steady_state.py
│   ├── verification.py, config.py, distributions.py
│   └── collection_window.py
└── tests/
```

## Setup

### Prerequisites

- Python 3.10+
- Conda recommended

### Create environment

```bash
conda env create -f environment.yaml
conda activate sim_env
```

Run notebooks from the **repository root** so `des` imports resolve.

### Streamlit app

All Streamlit files live in `streamlit_app/`:

```
streamlit_app/
  app.py              # Introduction (home page)
  helpers.py          # Shared UI helpers
  pages/
    2_Run_1_Calibration.py
    3_Run_2_Baseline.py
    4_Run_3_Policy.py
```

```bash
streamlit run streamlit_app/app.py
```

Pages: **Introduction** → **Run 1 (calibration + parameters)** → **Run 2 (baseline)** → **Run 3 (policy)**.

## Run

Use the Streamlit command above. Session state carries **T\***, calibrated parameters, and Run 3 scenarios across pages.

### Tests and model V&V

```bash
pytest tests/ -v
python -m des.verification   # full structural + behavioural suite
```

## License

See [LICENSE](LICENSE).
