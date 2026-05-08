# ADHD Discrete Event Simulation

Discrete-event simulation project for modeling ADHD care pathway flow, queue dynamics, and throughput over time.

Status: active development.

## Current Scope

The current notebook implementation models a Phase 1 partial pathway:

1. Arrivals
2. Screening
3. Triage
4. Assessment
5. Exit

Current outputs include:

- Total arrivals
- Completed patients
- Patients still in system at run end
- Per-stage started/completed counts
- Per-stage queue and in-service statistics (max and end-of-run)
- Completed-patient time in system (average and max)

## Iteration Phases

### Phase 1: Foundation and Operational Flow (Implemented)

Objective:

- Build an executable SimPy pathway model with configurable capacities and service-time distributions.

Implemented in this phase:

- End-to-end flow: Arrival -> Screening -> Triage -> Assessment -> Exit
- External resource definition (capacities controlled in scenario cell)
- Stage-level KPI tracking and run-end snapshots
- Diagram assets generated and stored in figures

Primary artifacts:

- iteration1.ipynb
- figures/pathway_modeled_so_far.png
- figures/pathway_kpi_map.png

### Phase 2: Clinical Decision Branching (Planned)

Objective:

- Add post-assessment decision logic and branching outcomes.

Planned scope:

- Diagnosed vs not diagnosed branch
- Path-specific counters and transition probabilities
- Branch-level waiting-time and throughput metrics

### Phase 3: Treatment and Follow-Up Loops (Planned)

Objective:

- Extend pathway beyond diagnosis into treatment dynamics.

Planned scope:

- Treatment planning and treatment-start delays
- Follow-up review cycles
- No-show, dropout, and re-entry events

### Phase 4: Outcomes and Scenario Analysis (Planned)

Objective:

- Support policy experiments and capacity planning analysis.

Planned scope:

- Multi-scenario runs
- Sensitivity analysis on capacity and demand
- Visualization and summary dashboards

## Repository Layout

Current key files and folders:

- README.md
- environment.yaml
- iteration1.ipynb
- figures/
- pathway_information/
    - PATHWAYS.md
    - STATE_MAPPING.md
- adhd_simpy/
    - Model/
        - ADHD_PATHWAY.PY
        - distributions.py

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

- iteration1.ipynb

## Related Documentation

- pathway_information/PATHWAYS.md
- pathway_information/STATE_MAPPING.md
- figures/adhd_pathway.drawio

## License

See LICENSE.