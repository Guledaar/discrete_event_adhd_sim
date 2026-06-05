# ADHD Discrete Event Simulation

Discrete-event simulation project for modelling neurodevelopmental care pathway
flow, queue dynamics, appointment capacity, and throughput over time.

Status: active development. The current primary model is Iteration 3 in
`iterarion3.ipynb`.

Note: the repository name refers to ADHD, while the current Iteration 3
notebook is documented as a full autism assessment pathway model. The README
therefore describes the current notebook accurately.

## Current Scope

`iterarion3.ipynb` models a patient-level autism assessment pathway using
SimPy. Referrals arrive on weekdays, move through clinical decision points,
wait for appointment slots, and exit through rejection, discharge, diagnosis,
formal discharge, or self-removal.

The current pathway stages are:

1. Referral arrival
2. Referral triage
3. Screening
4. Pre-assessment
5. Assessment
6. Further assessment
7. Post-diagnostic support split: clinical vs other support
8. Review and discharge
9. Final exit: formally discharged or self-removed

## Current Resource Modelling

Iteration 3 moves beyond continuously available SimPy resources. It uses a
custom `CalendarAwareQueueResource` to model appointment-slot capacity.

The resource model includes:

1. Weekday-only referral arrivals.
2. Weekday-only appointment capacity.
3. Separate slot capacities for screening, pre-assessment, assessment, further
   assessment, post-diagnostic clinical support, post-diagnostic other support,
   and review.
4. First-in, first-out queues for each pathway stage.
5. Released, used, and unused appointment-slot counts.
6. Queue backlog, maximum queue length, and utilisation reporting.

This design is intended to represent booked clinical capacity more realistically
than always-on 24/7 resources.

## Key Performance Indicators

The model tracks KPIs aligned with access, flow, backlog, and capacity planning.

### Access KPIs

1. **Referral-to-screening RTT**: mean time from referral to screening.
2. **Referral-to-pre-assessment RTT**: mean time from referral to
   pre-assessment.
3. **Referral-to-assessment RTT**: mean time from referral to assessment.
4. **Referral-to-further-assessment RTT**: mean time from referral to further
   assessment.
5. **Referral-to-diagnosis RTT**: mean time from referral to diagnosis.

### Flow KPIs

6. **Total arrivals**: number of referrals entering the system.
7. **Total exits**: number of patients leaving the system.
8. **Patients in system at end**: remaining unfinished pathway backlog.
9. **Clinical completions**: patients completing the full clinical pathway.
10. **Diagnosis rate**: proportion of arrivals with confirmed diagnosis.

### Exit KPIs

11. **Referral rejections**: referrals rejected at triage.
12. **Screening discharges**: patients discharged after screening.
13. **Pre-assessment rejections**: patients rejected at pre-assessment.
14. **Non-diagnosis at assessment**: patients exiting after assessment.
15. **Non-diagnosis at further assessment**: patients exiting after further
    assessment.
16. **Formal discharges**: patients formally discharged after review.
17. **Self-removals**: patients leaving through the self-removal route.

### Queue and Capacity KPIs

18. **Mean queue length by stage**: average observed queue size at each stage.
19. **Total backlog**: patients still waiting across resources at run end.
20. **Slot usage**: total appointment slots used.
21. **Utilisation by stage**: proportion of released slots used by each stage.
22. **Overall capacity utilisation**: used slots divided by released slots.

## Verification and Validation

Iteration 3 includes dedicated testing and V&V sections inside
`iterarion3.ipynb`.

Current tests include:

1. **Trace test**: runs a short three-day simulation with event-level logging to
   inspect patient movement.
2. **100% triage rejection test**: forces all referrals to exit at triage and
   checks that no patient reaches downstream stages.
3. **Stage boundary tests**: checks 100% exit and 0% exit behaviour at triage,
   screening, pre-assessment, assessment, and further assessment.
4. **Seed control and reproducibility**: confirms fixed seeds reproduce key
   outputs.
5. **Stochastic independence**: confirms unseeded runs can vary.
6. **Patient flow mass conservation**: checks that arrivals equal exits plus
   patients still in the system.
7. **Calendar-aware mathematical convergence**: compares high-capacity
   simulated RTT values with simplified theoretical expectations.

These checks provide evidence that the model logic, counters, random stream
handling, and calendar-aware capacity mechanism are behaving as intended. They
do not replace expert validation of the clinical assumptions.

## Current Progress Snapshot

- Pathway mapping: implemented for the Iteration 3 autism assessment pathway.
- Branching logic: implemented across triage, screening, pre-assessment,
  assessment, further assessment, post-diagnostic support, and final exit.
- Resource realism: implemented using weekday calendar-aware appointment slots.
- Replications: implemented with seeded and unseeded multi-run comparison.
- V&V: implemented with boundary tests, flow conservation, seed checks, and
  mathematical convergence checks.
- Documentation: notebook markdown has been expanded with model summary,
  resource modelling explanation, code explanations, and V&V interpretation.

## Iteration Phases

### Phase 1: Foundation and Operational Flow

Objective:

- Build an executable SimPy pathway model with configurable capacities and
  service-time distributions.

Implemented:

- End-to-end baseline flow.
- External resource definition.
- Stage-level KPI tracking and run-end snapshots.
- Diagram assets stored in `figures/`.

Primary artifacts:

- `iteration1.ipynb`
- `figures/pathway_modeled_so_far.png`
- `figures/pathway_kpi_map.png`

### Phase 2: Clinical Decision Branching and Extended Pathway

Objective:

- Add post-assessment decision logic and branching outcomes.

Implemented:

- Diagnosed vs non-diagnosed branch.
- Further-assessment pathway.
- Post-diagnostic clinical vs other support split.
- Final review, discharge, and self-removal branch.

Primary artifact:

- `iteration2.ipynb`

### Phase 3: Calendar-Aware Resource Realism

Objective:

- Move from continuously available resources to appointment-slot capacity.

Implemented in `iterarion3.ipynb`:

- Weekday-only arrival logic.
- Stage-specific weekday appointment-slot release.
- Calendar-aware FIFO queues.
- Used, unused, and released slot tracking.
- Stage-level and system-level utilisation metrics.

### Resource Modelling Status

The current resource model is a calendar-aware capacity abstraction that has passed internal V&V testing. Resource assumptions are still awaiting NHS stakeholder feedback and may be refined in future iterations. As such, the model should be viewed as a proof-of-concept rather than a final representation of NHS service operations.

### Phase 4: Verification, Validation, and Replications

Objective:

- Build confidence in model behaviour and support repeated simulation runs.

Implemented in `iterarion3.ipynb`:

- Short trace run.
- Boundary-condition testing.
- Seeded and unseeded replications.
- Flow conservation verification.
- Mathematical convergence checks.
- Final V&V automation cell.

### Phase 5: Outcomes and Scenario Analysis

Objective:

- Extend the model for policy experiments and capacity planning.

Planned scope:

- Multi-scenario comparison tables.
- Sensitivity analysis on demand, capacity, and branching assumptions.
- Visualisation and summary dashboards.
- Optional treatment and follow-up loops beyond diagnosis.

## Repository Layout

Current key files and folders:

urrent key files and folders:

- `README.md`
- `environment.yaml`
- `iteration1.ipynb`
- `iteration2.ipynb`
- `iterarion3.ipynb`
- `figures/`
- `pathway_information/`
  - `PATHWAYS.md`
  - `STATE_MAPPING.md`
- `adhd_simpy/`
  - `Model/`
    - `ADHD_PATHWAY.PY`
    - `distributions.py`

## Setup

### Prerequisites

- Python 3.10+
- Conda recommended

### Create Environment

```bash
conda env create -f environment.yaml
conda activate adhd-sim
```

## Run

Open and execute notebook cells in order:

- `iterarion3.ipynb`: current primary Iteration 3 model
- `iteration2.ipynb`: earlier branching pathway model
- `iteration1.ipynb`: earlier baseline model

## Related Documentation

- pathway_information/PATHWAYS.md
- pathway_information/STATE_MAPPING.md
- figures/adhd_pathway.drawio

## License

See LICENSE
