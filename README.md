# NHS Neurodevelopmental Assessment Pathway — Discrete Event Simulation

Discrete-event simulation (DES) for modelling **NHS neurodevelopmental (autism/ADHD)
assessment** pathway flow, waiting lists (Patient Tracking List / PTL), workforce
capacity, referral-to-treatment (RTT) clocks, and policy interventions.

**Status:** active development.

**Primary entry point:** [`demo.ipynb`](demo.ipynb) — calibration, stochastic baseline,
and policy analysis using the importable [`des/`](des/) package.

> The repository name refers to ADHD; the active model is an NHS assessment pathway.
> Earlier modelling iterations live in [`notebooks/`](notebooks/).

## What the model does

Referrals arrive over time, pass triage and administrative review, compete for a
**shared weekday clinician-hour pool**, complete multi-appointment assessments, receive
a diagnostic outcome, and exit via virtual support or a **clinical workshop group** pathway.

The simulation answers:

- How large will the waiting list grow, and how long do patients wait?
- What capacity level matches an observed PTL target (calibration)?
- Which levers — **more capacity** or **higher administrative removal** — reduce backlog
  and improve 18-week / 52-week waiting-time standards?

## Three-run framework

`demo.ipynb` runs three independent analyses on the same engine:

| Run | Purpose | API | Output |
|-----|---------|-----|--------|
| **Run 1** | Calibration | `des.runs.run1` | Find **Matching Period `T*`** where simulated PTL matches provider target |
| **Run 2** | Stochastic baseline | `des.runs.run2` | Repeat As-Is scenario over many seeds → KPI means with **95% CIs** |
| **Run 3** | Policy analysis | `des.runs.run3` | Run to `T*`, apply a policy change, measure **backlog decay** over a decay horizon |

Policy examples in `demo.ipynb`:

- **Double capacity** (7 → 14 h/weekday)
- **Double administrative removal** (10% → 20%)
- Capacity × decay grid sweeps and comparison plots

## Pathway (current model)

1. Referral arrival (weekday inter-arrivals)
2. Triage (referral rejected or accepted)
3. Administrative review (admin removal)
4. Multi-appointment assessment (shared capacity bottleneck)
5. Diagnostic outcome (diagnosis / no diagnosis)
6. Post-diagnosis support — **virtual** (quick exit) or **clinical workshop** (group sessions)
7. Exit — RTT clock stops; incomplete pathways count on the **PTL**

Pathway diagram: [`figures/nhs-neurodevelopmental-pathway.png`](figures/nhs-neurodevelopmental-pathway.png)

## Architecture

Model logic lives in the flat `des/` package:

| Module | Role |
|--------|------|
| `config.py` | Global defaults — demand, branching, capacity, workshop settings |
| `experiment.py` | Scenario configuration, RNG streams, parameter overrides |
| `patient.py` | Individual referral SimPy processes |
| `workforce.py` | `WorkforceHoursResource` — shared weekday clinician-hour pool |
| `workshop_manager.py` / `workshop_group.py` | Group workshop waiting list and sessions |
| `system.py` | `AutismPathwaySystem` — referral generation and coordination |
| `audit.py` | Patient record store during simulation |
| `kpi.py` | `compute_kpis()` — PTL, RTT, utilisation, validation |
| `runner.py` | Warm-up + collection `single_run()` / `multiple_replications()` |
| `runs/run.py` | **Run 1 / 2 / 3** framework (`run1`, `run2`, `run3`) |
| `steady_state.py` | Waiting-list census at a simulation time |
| `verification.py` | Automated V&V suites |
| `distributions.py` | Seeded stochastic distributions |

### Simulation horizons

**Warm-up + collection** (via `des.runner`):

```
WARM-UP     system runs, KPI cohort OFF
COLLECTION  KPI cohort ON (referrals in reporting window)
```

**Three-run framework** (via `des.runs`):

```
Run to T* (Matching Period)  →  optional policy switch  →  decay horizon
```

Defaults in `des/config.py`: 3-year warm-up, 5-year collection window;
Run 1 finds `T*` by matching `waiting_list_size_all_in_system` to a provider target.

### Resource modelling

- One **shared weekday clinician-hour budget** for assessment and workshop activity
- Multi-appointment assessment sequences with gaps between appointments
- Workshop groups (fixed size, session series, max wait to form a group)
- Daily capacity ledger for utilisation KPIs

## Key performance indicators

Computed by `compute_kpis()` from audit patient records.

### Waiting list / PTL

- `waiting_list_size_all_in_system` / `overall_waiting_list_size` — full PTL (all incomplete pathways)
- `first_assessment_waiting_list_size` — awaiting first assessment
- `first_workshop_waiting_list_size` — diagnosed, clinical pathway, awaiting workshop start

### RTT and access standards

- NHS RTT clock: starts at accepted referral, stops at definitive outcome
- `ptl_under_18_weeks_pct`, `ptl_over_52_weeks_pct` — PTL compliance snapshots
- `rtt_completed_mean_days`, `rtt_incomplete_mean_days`

### Flow and capacity

- Referrals, acceptances, admin removals, diagnoses, workshop completions
- `overall_clinician_utilisation`, `assessment_utilisation`
- `assessments_per_month`, `diagnoses_per_month`

### Policy / calibration (Run 3)

- `waiting_list_at_switch`, `waiting_list_at_end`
- `backlog_decay_total`, `backlog_decay_per_month`

KPI definitions: `des/kpi_docs.py` (`KPI_GLOSSARY`, `display_kpi_results_reference()`).

## Notebooks

| Notebook | Focus |
|----------|-------|
| **`demo.ipynb`** | **Primary demo — Run 1/2/3, PTL calibration, policy tests** |
| `notebooks/iteration1.ipynb` | Early baseline pathway |
| `notebooks/iteration2.ipynb` | Clinical branching and review loop |
| `notebooks/iteration3.ipynb` | Calendar-aware appointment slots |
| `notebooks/iteration4.ipynb` | Multi-stage workforce-hours model (earlier iteration) |

Legacy pathway diagrams: `figures/01_patient_pathway.png`, `02_clinical_stage.png`,
`03_workforce_hours.png`.

## Current progress

**Implemented**

- Full neurodevelopmental pathway with admin removal and workshop groups
- Modular `des/` package with three-run calibration / baseline / policy framework
- PTL and NHS RTT KPI engine with validation report
- Run 1 matching-period search with yearly progress checkpoints
- Run 2 replications with confidence intervals
- Run 3 policy branching (capacity increase, admin removal, capacity × decay grids)
- Section 13 policy comparison: double capacity vs double admin removal
- Automated verification suites in `des/verification.py`

**In progress / planned**

- External validation against published ICB statistics
- Multi-provider configuration files (`ProviderRunConfig`)
- Decision-support dashboards and optimisation

## Modelling history (iteration phases)

1. **Foundation** — baseline end-to-end flow (`notebooks/iteration1.ipynb`)
2. **Branching** — diagnosis branches, post-diagnostic support, review (`iteration2`)
3. **Calendar slots** — weekday appointment-slot resources (`iteration3`)
4. **Workforce hours** — multi-stage clinician-hour DES (`iteration4`)
5. **Provider calibration & policy** — three-run framework, PTL matching, policy decay (`demo.ipynb`)

## Repository layout

```
discrete_event_adhd_sim/
├── README.md
├── LICENSE
├── environment.yaml
├── demo.ipynb                    # primary demo (Run 1 / 2 / 3)
├── des/                          # Python DES package
│   ├── audit.py, kpi.py, experiment.py, patient.py, system.py
│   ├── workforce.py, workshop_manager.py, workshop_group.py
│   ├── runner.py, verification.py, config.py
│   └── runs/                     # run1, run2, run3 framework
├── notebooks/                    # iteration1–4 development notebooks
├── figures/                      # pathway diagrams
├── pathway_information/
│   ├── PATHWAYS.md
│   └── STATE_MAPPING.md
├── tests/                        # pytest wrappers
└── run_output/                   # example simulation exports
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

Run notebooks from the **repository root** so `des` imports resolve. The setup cell in
`demo.ipynb` locates the project root automatically.

## Run

```bash
jupyter lab demo.ipynb
```

Execute cells in order from the top. Run 1 (calibration) must complete before Run 2/3
(which use `T*` from Run 1).

### Verification

```python
from des import run_all_verifications
run_all_verifications()
```

Or via pytest (see `tests/`):

```bash
pytest tests/ -v
```

## Related documentation

- [`pathway_information/PATHWAYS.md`](pathway_information/PATHWAYS.md)
- [`pathway_information/STATE_MAPPING.md`](pathway_information/STATE_MAPPING.md)
- [`des/kpi_docs.py`](des/kpi_docs.py) — KPI glossary and calculation notes
- [`des/model_docs.py`](des/model_docs.py) — parameter definitions

## License

See [LICENSE](LICENSE).
