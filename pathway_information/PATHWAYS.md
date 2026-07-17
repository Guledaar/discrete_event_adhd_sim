# NHS Neurodevelopmental Assessment Pathway

## Overview

This document describes the pathway implemented in the current discrete-event simulation
(DES) model — package [`des/`](../des/), primary demo [`demo.ipynb`](../demo.ipynb).

The model simulates an **NHS neurodevelopmental (autism/ADHD) assessment service**:
referrals arrive over time, pass triage and administrative review, compete for a **shared
weekday clinician-hour pool**, complete a variable number of assessment appointments, receive
a diagnostic outcome, and exit via **virtual support** or a **clinical workshop group**.

Earlier multi-stage models (screening, pre-assessment, further assessment, review loop) are
documented in [`notebooks/`](../notebooks/) iterations 1–4. The **active production pathway**
is the simplified bottleneck model below.

## Reference structure

The pathway follows NHS neurodevelopmental assessment logic:

- Detection and triage
- Administrative Patient Tracking List (PTL) management
- Diagnostic assessment (capacity-constrained)
- Diagnostic outcome
- Post-diagnosis support (low-intensity virtual or group clinical workshop)
- Exit with RTT clock stop

Pathway diagram: [`figures/nhs-neurodevelopmental-pathway.png`](../figures/nhs-neurodevelopmental-pathway.png)

## Implemented pathway

```
Referral arrival (weekday inter-arrivals)
    │
    ▼
Triage ── rejected ──► exit (referral_rejected)     [RTT nullified]
    │ accepted
    ▼
Administrative review ── removed ──► exit (admin_removal)   [RTT stops]
    │ cleared
    ▼
Assessment queue ──► appointment 1 … N  (shared workforce hours)
    │                  (gap between appointments: ASSESSMENT_GAP_DAYS)
    ▼
Diagnostic outcome ── no diagnosis ──► exit (no_diagnosis)   [RTT stops at assessment_completion]
    │ diagnosis
    ├── virtual support (30%) ──► exit (virtual_support)   [RTT stops at exit_time]
    │
    └── clinical workshop (70%) ──► workshop waiting list
                                      │
                                      ▼
                                 group forms (WORKSHOP_GROUP_SIZE)
                                      │
                                      ▼
                                 N workshop sessions (shared capacity)
                                      │
                                      ▼
                                 exit (workshop_complete)   [RTT stops at workshop_start_time]
```

### Stage summary

| Stage | Capacity? | Notes |
|-------|-----------|--------|
| Triage | No | Bernoulli reject (`PCT_REFERRAL_REJECTED`) |
| Admin review | No | Bernoulli admin removal (`PCT_ADMIN_REMOVAL`) |
| Assessment | **Yes** — shared weekday hours | 2–6 appointments sampled per patient; triangular duration |
| Diagnosis | No | Bernoulli positive diagnosis (`PCT_DIAGNOSIS`) |
| Virtual support | No | Immediate exit (`PCT_VIRTUAL_SUPPORT` of diagnosed) |
| Clinical workshop | **Yes** — same shared pool | Group sessions; max wait to form group |

## Pathway components

### Events

- Referral arrival (`arrival_time`)
- Triage accept / reject
- Admin clearance / removal
- Assessment wait, start, complete (per appointment)
- Inter-appointment gap
- Diagnosis positive / negative
- Virtual support exit
- Workshop join, group start, session series, completion

### States (operational)

- **Waiting** — in assessment queue or workshop waiting list
- **In service** — assessment appointment or workshop session in progress
- **Incomplete pathway** — on PTL (RTT clock running)
- **Completed / exited** — RTT clock stopped

### Transitions

Driven by:

- SimPy timed events (`yield timeout`)
- Bernoulli / discrete distributions (`des/distributions.py`)
- Shared `WorkforceHoursResource` queue (priority new vs returning assessment patients)
- `WorkshopManager` group formation rules

## Resource modelling

**Current (demo / `des/` package):**

- One **shared weekday clinician-hour budget** (`WORKFORCE_HOURS_PER_DAY`) for:
  - All assessment appointments
  - All workshop sessions
- Weekday-only capacity release (Mon–Fri); weekends = 0
- Priority queue: returning assessment patients before new referrals
- Daily capacity ledger in `Audit.capacity_days` → utilisation KPIs

**Historical iterations** (see `notebooks/`):

| Iteration | Resource model |
|-----------|----------------|
| 1–2 | SimPy `Resource` per stage, 24/7 |
| 3 | Calendar-aware appointment slots per stage |
| 4 | Multi-stage workforce-hours resources |
| **Demo** | Single shared pool + workshop groups |

## NHS RTT clock

The **Referral-to-Treatment (RTT)** / PTL clock behaviour:

| Exit route | RTT clock stops at |
|------------|-------------------|
| `referral_rejected` | Nullified (no clock) |
| `admin_removal` | `exit_time` |
| `no_diagnosis` | `assessment_completion` |
| `virtual_support` | `exit_time` |
| `workshop_complete` | `workshop_start_time` (first definitive treatment) |

Patients with an incomplete pathway at the reporting horizon are counted on the
**Patient Tracking List (PTL)** — KPI `overall_waiting_list_size`.

## Simulation frameworks

Two runner APIs use the same pathway:

| API | Use |
|-----|-----|
| `des.runner.single_run` | Warm-up + collection window |
| `des.runs.run1` / `run2` / `run3` | Calibration (`T*`), baseline CIs, policy decay |

Policy levers tested in `demo.ipynb`:

- Increase `workforce_hours_per_day` (capacity)
- Increase `pct_admin_removal` (administrative removal)
- Capacity × decay grid sweeps

## Default parameters

See [`des/config.py`](../des/config.py). Key values (notebook may override):

- `REFERRALS_PER_DAY = 1.89`
- `PCT_REFERRAL_REJECTED = 0.369`
- `PCT_ADMIN_REMOVAL = 0.10` (10% in demo notebook)
- `PCT_DIAGNOSIS = 0.75`
- `PCT_VIRTUAL_SUPPORT = 0.30`
- `WORKFORCE_HOURS_PER_DAY = 7`
- Assessment appointments: 2–6 (discrete distribution)
- Workshop: 8 per group, 6 sessions, 1-week interval

Parameter definitions: [`des/model_docs.py`](../des/model_docs.py).

## Customising the pathway

Override via `Experiment(**kwargs)` or `NOTEBOOK_EXPERIMENT_PARAMETERS` in `demo.ipynb`:

1. Arrival rate (`iat` / `REFERRALS_PER_DAY`)
2. Branch probabilities (triage, admin, diagnosis, virtual)
3. Assessment appointment count distribution and gap
4. Shared capacity (`workforce_hours_per_day`)
5. Workshop group size, sessions, max wait

## Implementation files

| File | Role |
|------|------|
| [`des/patient.py`](../des/patient.py) | Pathway SimPy process |
| [`des/system.py`](../des/system.py) | Referral generator, system coordination |
| [`des/workforce.py`](../des/workforce.py) | Shared capacity resource |
| [`des/workshop_manager.py`](../des/workshop_manager.py) | Workshop waiting list and groups |
| [`des/audit.py`](../des/audit.py) | Per-patient milestone records |
| [`des/kpi.py`](../des/kpi.py) | PTL, RTT, flow KPIs |
| [`demo.ipynb`](../demo.ipynb) | Run 1 / 2 / 3 demonstration |

Legacy iteration notebooks: [`notebooks/iteration1.ipynb`](../notebooks/iteration1.ipynb) …
[`iteration4.ipynb`](../notebooks/iteration4.ipynb).
