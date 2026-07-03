# NHS Adult Autism Assessment — Discrete Event Simulation

Discrete-event simulation (DES) project for modelling neurodevelopmental care pathway
flow, queue dynamics, workforce capacity, referral-to-treatment (RTT) times, and
throughput over time.

**Status:** active development. The current primary model is **Iteration 4** in
[`iteration4.ipynb`](iteration4.ipynb), backed by the importable Python package in
[`des/`](des/).

> The repository name refers to ADHD, while the active pathway model is an **NHS adult
> autism assessment** service. Earlier notebooks (`iteration1`–`iteration3`) document
> the modelling journey; `des/` is the current implementation.

## Current Scope

The Iteration 4 model simulates a patient-level autism assessment pathway using
**SimPy**. Referrals arrive on weekdays, move through clinical decision points, wait
for capacity-constrained appointments, and exit through rejection, discharge,
diagnosis, formal discharge, or self-removal.

Pathway stages:

1. Referral arrival and triage
2. Screening
3. Pre-assessment
4. Assessment
5. Further assessment (complexity branch)
6. Diagnostic outcome
7. Post-diagnostic support (clinical vs other)
8. Review loop (continue support, formal discharge, or self-removal)
9. Final exit

## Architecture (Iteration 4)

Model logic lives in `des/model/` and is driven from the notebook:

| Module | Role |
|--------|------|
| `parameters.py` | Global defaults (demand, durations, branching, workforce hours) |
| `experiment.py` | Scenario configuration, RNG streams, parameter overrides |
| `patient.py` | Individual referral processes and pathway logic |
| `resources.py` | `WorkforceHoursResource` — weekday clinician-hour capacity |
| `system.py` | `AutismPathwaySystem` — referral generation and coordination |
| `audit.py` | KPI collection, cohort filtering, RTT samples |
| `simulation.py` | `single_run()` and `multiple_runs()` replication runners |
| `verification.py` | Automated V&V test suites |
| `distributions.py` | Seeded stochastic distributions |

### Simulation phases

Each replication runs three phases:

```
Phase 1  WARM-UP     Days [0, warmup_days)                 KPI cohort OFF
Phase 2  COLLECTION  Days [warmup_days, + run_length)       KPI cohort ON
Phase 3  DRAIN       After last referral until empty       (max MAX_DRAIN_DAYS)
```

- **Cohort KPIs** (RTT, diagnosis rate, stage utilisation) apply only to referrals
  arriving during the collection window.
- **Warm-up** fills queues before collection; warm-up patients compete for capacity
  but are excluded from cohort RTT.
- **Drain** clears patients still in the pathway after collection ends. Without drain
  (`max_drain_days=0`), slow patients remain and RTT KPIs are biased downward.

Default horizons (`des/model/parameters.py`): 730-day warm-up, 1825-day collection
(5 years), 3650-day max drain.

### Resource modelling

Iteration 4 uses **`WorkforceHoursResource`** — capacity measured in **clinician hours
per weekday** (Mon–Fri), not discrete appointment slots.

Features:

- Weekday-only referral arrivals and capacity release
- Per-stage workforce hour budgets (screening through review)
- Priority and standard queues; best-fit scheduling within daily hour budget
- Triangular appointment durations (hours)
- Released / used / unused hour accounting with end-of-run validation

Iteration 3 (`iteration3.ipynb`) used calendar-aware appointment-slot resources; that
approach is superseded by workforce-hours modelling in Iteration 4.

## Key Performance Indicators

KPIs are collected by `Audit` during the collection cohort and summarised at run end.

### Access / RTT

- Referral-to-milestone RTT (screening, pre-assessment, assessment, further
  assessment, diagnosis, review)
- Legacy wait-time metrics for comparison

### Flow

- `ARRIVED_ALL` / `ARRIVED_TOTAL` — all referrals vs cohort only
- `FLOW_DIAGNOSIS_CONFIRMED` and `FLOW_DIAGNOSIS_RATE_PCT`
- Stage exit counters (rejections, non-diagnosis, discharges)
- `IN_SYSTEM_END` — cohort patients remaining at simulation end

### Queue and capacity

- Mean and peak queue length by stage (`QUEUE_PEAK_ANY_STAGE`)
- Stage utilisation (`CAPACITY_UTILISATION_*`, 0–1 in raw output)
- `OVERALL_SYSTEM_UTILISATION` (percent)

### Run validity flags

- `COHORT_DRAIN_COMPLETE` — all cohort patients exited
- `COHORT_RTT_VALID` — safe to report cohort RTT KPIs

## Notebook Guide

| Notebook | Focus |
|----------|-------|
| `iteration1.ipynb` | Baseline end-to-end flow, external resources |
| `iteration2.ipynb` | Clinical branching, post-diagnostic support, review |
| `iteration3.ipynb` | Calendar-aware appointment-slot resources, early V&V |
| **`iteration4.ipynb`** | **Workforce-hours DES, modular `des/` package, warm-up/drain, scenarios, V&V** |

`iteration4.ipynb` sections include:

- Model overview and default parameters
- Single trace run (debugging)
- Single run: drain phase and warm-up comparison (§6.2)
- Multiple replications — fixed vs random seeds (§6.3)
- Parameter experiments and multi-run scenario analysis (§7.x)
- Warm-up / steady-state sensitivity
- Automated verification (§8)
- Planned work: provider calibration, intervention analysis (§9)

Pathway diagrams: [`figures/`](figures/) (`01_patient_pathway.png`, `02_clinical_stage.png`,
`03_workforce_hours.png`).

## Current Progress Snapshot

**Implemented**

- Full autism assessment pathway with review loop
- Modular `des/` package importable from notebooks and tests
- Workforce-hours capacity with priority queues and best-fit scheduling
- Warm-up → collection → drain simulation lifecycle with cohort KPI filtering
- `single_run()` and `multiple_runs()` with fixed and random seed modes
- Scenario comparison (demand increase, capacity increase) via `Experiment(**kwargs)`
- Diagnosis rate, RTT, queue, and utilisation KPIs with drain-validity flags
- Automated V&V: seed reproducibility, flow conservation, RTT cohort checks,
  mathematical convergence, demand-stress monotonicity
- Pytest suite in `des/tests/test_verification.py`

**In progress / planned**

- Provider calibration using NHS operational data (`devon_parameters.py` pattern)
- Dynamic calibration and freeze-state initialisation (§7.4–7.5)
- External validation against published ICB statistics
- Intervention analysis and decision-support dashboards (§9)

## Iteration Phases

### Phase 1 — Foundation and operational flow

- End-to-end baseline pathway, stage KPIs, diagram assets
- Artifacts: `iteration1.ipynb`, `figures/`

### Phase 2 — Clinical decision branching

- Diagnosis branches, further assessment, post-diagnostic support, review/discharge
- Artifact: `iteration2.ipynb`

### Phase 3 — Calendar-aware appointment slots

- Weekday slot release, FIFO queues, slot utilisation tracking
- Artifact: `iteration3.ipynb`

### Phase 4 — Workforce-hours realism and modular package

- Clinician-hour capacity, triangular durations, priority scheduling
- Extracted model code into `des/`
- Warm-up, collection cohort, and drain phases
- Artifact: `iteration4.ipynb`, `des/`

### Phase 5 — Scenarios, calibration, and decision support

- Partially implemented: single-run and multi-run scenario tables (§7.2–7.3)
- Planned: multi-ICB calibration, sensitivity dashboards, optimisation

## Repository Layout

```
discrete_event_adhd_sim/
├── README.md
├── LICENSE
├── environment.yaml
├── iteration1.ipynb … iteration4.ipynb   # modelling iterations (4 = current)
├── des/                                  # Iteration 4 Python package
│   ├── model/                            # pathway, resources, simulation, V&V
│   └── tests/                            # pytest V&V wrappers
├── adhd_simpy/                           # earlier inline model (Iteration 3 era)
├── figures/                              # pathway diagrams
├── pathway_information/
│   ├── PATHWAYS.md
│   └── STATE_MAPPING.md
└── demo/                                 # standalone demo copy of the model
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

Install the project root on `PYTHONPATH` (notebooks import `des` directly when run
from the repository root).

## Run

Open and execute notebook cells in order:

```bash
jupyter lab iteration4.ipynb
```

Recommended order for new users:

1. `iteration4.ipynb` — current model (start here)
2. `iteration3.ipynb` — prior slot-based resource model
3. `iteration2.ipynb` / `iteration1.ipynb` — earlier pathway versions

### Run automated tests

```bash
pytest des/tests/ -v
```

## Related Documentation

- [`pathway_information/PATHWAYS.md`](pathway_information/PATHWAYS.md) — pathway structure
- [`pathway_information/STATE_MAPPING.md`](pathway_information/STATE_MAPPING.md) — state definitions
- [`figures/`](figures/) — pathway visualisations
- [`demo/README.md`](demo/README.md) — standalone demo package

## License

See [LICENSE](LICENSE).
