# ADHD Discrete Event Simulation

Discrete-event simulation project for modeling ADHD care pathway flow, queue dynamics, and throughput over time.

Status: active development (Iteration 2 in progress).

## Current Scope

The current notebook implementation in `iteration2.ipynb` models an expanded diagnostic pathway with branching and downstream support:

1. Referral arrival
2. Referral triage
3. Screening
4. Pre-assessment
5. Assessment
6. Further assessment
7. Post-diagnostic support split (clinical vs other)
8. Review/discharge
9. Final exit (formally discharged or self-removed)

Current outputs include:

- Total arrivals
- Completed patients
- Patients still in system at run end
- Stage-level accepted/completed/rejected counters
- Branch-level non-diagnosis and diagnostic support counters
- End-of-run pathway inventory metrics

## Current Progress Snapshot

- Pathway mapping: almost completed.
- Resource modelling with realistic service calendars: next major work item.
- Current resource method in Iteration 2: stage-specific SimPy `Resource` objects.
- Current resource assumption in Iteration 2: resources are modeled as continuously available (24/7), with no weekday/weekend or shift constraints yet.

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

### Phase 2: Clinical Decision Branching and Extended Pathway (Mostly Implemented in Iteration 2)

Objective:

- Add post-assessment decision logic and branching outcomes.

Implemented in current notebook (`iteration2.ipynb`):

- Diagnosed vs not diagnosed branch
- Further-assessment and non-diagnosis pathways
- Post-diagnostic clinical vs other support split
- Final review/discharge branch with removal outcomes

Remaining in this phase:

- Complete and lock state/event mapping documentation

### Phase 3: Resource Realism (Next)

Objective:

- Move from always-available resources to service-time-aware operational constraints.

Planned scope:

- Working-day and working-hours capacity logic
- Stage calendars (weekday/weekend behavior)
- Optional shift and availability policies by stage

### Phase 4: Treatment and Follow-Up Loops (Planned)

Objective:

- Extend pathway beyond diagnosis into treatment dynamics.

Planned scope:

- Treatment planning and treatment-start delays
- Follow-up review cycles
- No-show, dropout, and re-entry events

### Phase 5: Outcomes and Scenario Analysis (Planned)

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
- iteration2.ipynb
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

- iteration2.ipynb (current primary model)
- iteration1.ipynb (earlier baseline)

## Related Documentation

- pathway_information/PATHWAYS.md
- pathway_information/STATE_MAPPING.md
- figures/adhd_pathway.drawio

## License

See LICENSE.