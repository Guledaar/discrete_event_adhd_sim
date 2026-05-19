# ADHD Pathway Models

## Overview

This document describes the pathway currently implemented in the ADHD discrete-event simulation notebooks.

The active model is implemented in `iteration2.ipynb` and focuses on pathway flow, stage-level queueing, branching, and throughput.

## Reference Model

The simulation framework is informed by structured care pathways similar to the NHS Autism Pathway model structure:
- Detection and initial triage
- Diagnostic assessment and further assessment branches
- Post-diagnostic support branches
- Monitoring/review and exit outcomes

## Implemented Iteration 2 Pathway

The current modeled flow is:

1. Referral arrival
2. Referral triage
3. Screening
4. Pre-assessment
5. Assessment
6. Further assessment
7. Post-diagnostic support split:
	- Clinical support
	- Other/community support
8. Review/discharge
9. Exit:
	- Formally discharged
	- Self-removed

Early exits occur at multiple gate points (triage rejection, screening discharge, pre-assessment rejection, and non-diagnosis outcomes).

## Pathway Components

### Events

Events represent pathway occurrences such as:

- Referral arrival
- Start of stage service
- Completion of stage service
- Branch decision at gate points
- Pathway exit or completion

### States

Operational states are represented by movement through stage queues and services:

- Waiting for stage resource
- In stage service
- Exited pathway
- Completed pathway

### Transitions

Transitions are driven by:

- SimPy event timing (`yield timeout`)
- Capacity-limited stage resources
- Bernoulli branch probabilities

## Current Progress

- Pathway mapping is almost completed.
- The next major task is resource modelling realism.

Current Iteration 2 resource method:

- Uses SimPy `Resource` objects for each stage.
- Each stage has its own dedicated resource.
- Resources are currently modeled as continuously available (24/7).
- No explicit weekday/weekend or working-hours calendars yet.

## Next Resource Modelling Step

Planned resource modelling improvements:

1. Working-day and working-hours capacity logic
2. Stage-specific calendar constraints
3. Optional shift patterns and availability variation

## Defining Custom Pathways

Pathways can be customized by defining:

1. Initial state
2. Stage sequence and branch points
3. State transitions
4. Time distributions for events
5. Probabilities and exit conditions
6. Stage resource capacities and calendars

## Implementation

Current implementation files:

- `iteration2.ipynb` (primary model)
- `adhd_simpy/Model/distributions.py` (sampling distributions)
- `figures/iteration2_model_pathway_human_readable.png` (current pathway diagram)
