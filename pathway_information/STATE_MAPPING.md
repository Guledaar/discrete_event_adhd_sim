# Pathway State Mapping — Current Model (`des/`)

## Status

**Current:** mapping reflects the NHS neurodevelopmental assessment pathway in
[`des/`](../des/) and [`demo.ipynb`](../demo.ipynb).

**Superseded:** Iteration 2 multi-stage mapping (screening, pre-assessment, further
assessment, review loop) — retained only in [`notebooks/`](../notebooks/) for history.

## Purpose

Maps conceptual pathway states to:

- `PatientRecord` fields in [`des/audit.py`](../des/audit.py)
- `exit_route` terminal labels
- KPI counters from [`des/kpi.py`](../des/kpi.py) / [`des/kpi_docs.py`](../des/kpi_docs.py)

## Patient record fields

| Field | Meaning |
|-------|---------|
| `patient_id` | Unique identifier |
| `arrival_time` | Referral arrival (simulation days) |
| `triage_outcome` | `'accepted'` or `'rejected'` |
| `admin_removal` | `True` if removed at admin review |
| `appointments_required` | Sampled count (2–6) |
| `appointments_completed` | Appointments finished so far |
| `assessment_start` | First assessment appointment start |
| `assessment_completion` | Final assessment appointment end |
| `diagnosis` | `True` / `False` / unset |
| `support_type` | `'virtual'` or `'clinical'` (if diagnosed) |
| `workshop_join_time` | Joined workshop waiting list |
| `workshop_start_time` | First group session (RTT stop for clinical path) |
| `workshop_completion` | Final session end |
| `workshop_group_id` | Assigned group |
| `exit_time` | Pathway exit time |
| `exit_route` | Terminal reason (see below) |
| `clinician_hours_consumed` | Total hours (assessment + workshop) |
| `assessment_hours_consumed` | Assessment hours only |
| `workshop_hours_consumed` | Workshop session hours |

## State-to-stage mapping

### 1. Referral arrived

- **Trigger:** `Patient.process()` starts
- **Audit update:** `arrival_time`
- **KPI:** `referrals` (cohort arrivals in window)

### 2. Triage decision

- **Branch:** `referral_reject_dis`
- **Accepted:** `triage_outcome='accepted'` → RTT clock starts at `arrival_time`
- **Rejected:** `exit_route='referral_rejected'`, RTT **nullified**
- **KPI:** `referrals_accepted`, `referrals_rejected`

### 3. Administrative review

- **Branch:** `admin_removal_dis`
- **Removed:** `admin_removal=True`, `exit_route='admin_removal'`, RTT stops at `exit_time`
- **Cleared:** `admin_removal=False` → proceeds to assessment
- **KPI:** `admin_removals`

### 4. Assessment (multi-appointment)

- **Setup:** `appointments_required` sampled; queue via `WorkforceHoursResource`
- **Milestones:** `assessment_start` (first appt), per-appointment `appointments_completed`,
  `assessment_completion` (last appt)
- **Waiting list subset:** `first_assessment_waiting_list_size` — accepted, not yet started
- **KPI:** `assessments_completed_in_window`, `assessment_appointments_completed`,
  `assessments_per_month`

### 5. Diagnostic outcome

- **Branch:** `diagnosis_dis`
- **No diagnosis:** `diagnosis=False`, `exit_route='no_diagnosis'`, RTT stops at `assessment_completion`
- **Diagnosis:** `diagnosis=True` → support routing
- **KPI:** `diagnoses_completed_in_window`, `no_diagnosis`, `diagnoses_per_month`

### 6. Virtual support (post-diagnosis)

- **Branch:** `virtual_support_dis` (among diagnosed)
- **Exit:** `support_type='virtual'`, `exit_route='virtual_support'`, RTT stops at `exit_time`
- **KPI:** `virtual_supports`

### 7. Clinical workshop (post-diagnosis)

- **Enrol:** `support_type='clinical'`, `workshop_join_time` via `WorkshopManager.join`
- **Waiting list subset:** `first_workshop_waiting_list_size` — clinical, joined, not yet started
- **Group start:** `workshop_start_time`, `workshop_group_id` — RTT stops here
- **Sessions:** `workshop_hours_consumed` accumulates
- **Complete:** `workshop_completion`, `exit_route='workshop_complete'`
- **KPI:** `clinical_supports_enrolled`, `clinical_supports_completed`, `workshop_groups`,
  `workshop_sessions`

### 8. Incomplete pathway (on PTL)

- **Condition:** `rtt_pathway_status='incomplete'` at reporting horizon
- **KPI:** `waiting_list_size_all_in_system` / `overall_waiting_list_size`
- **Cohort subset:** `waiting_list_size` (arrivals in collection window only)

## Exit routes

| `exit_route` | RTT status | Clock stop |
|--------------|------------|------------|
| `referral_rejected` | nullified | — |
| `admin_removal` | completed | `exit_time` |
| `no_diagnosis` | completed | `assessment_completion` |
| `virtual_support` | completed | `exit_time` |
| `workshop_complete` | completed | `workshop_start_time` |
| *(none — still in pathway)* | incomplete | clock running to horizon |

## Resource mapping

### Current — shared workforce pool

| Activity | Resource | Module |
|----------|----------|--------|
| Assessment appointments | `WorkforceHoursResource` (shared) | `des/workforce.py` |
| Workshop sessions | Same shared pool | `des/workshop_group.py` |

- Capacity: `WORKFORCE_HOURS_PER_DAY` per weekday
- Queue: priority (returning assessment patients before new)
- Accounting: `Audit.capacity_days` — `hours_released`, `hours_used`, `assessment_hours_used`,
  `workshop_hours_used`

### Workshop manager

| State | Counter / field |
|-------|----------------|
| Waiting for group | `WorkshopManager.waiting_list` |
| Active in group | `WorkshopManager.active_patient_ids` |
| Live stock check | V&V `live_workshop_stock` rule in `des/kpi.py` |

## KPI summary mapping

| Concept | Primary KPI key |
|---------|-----------------|
| All referrals in window | `referrals` |
| PTL (full system) | `overall_waiting_list_size` |
| PTL ≤ 18 weeks | `ptl_under_18_weeks_pct` |
| PTL ≤ 52 weeks | `ptl_under_52_weeks_pct` |
| Mean incomplete wait | `ptl_mean_wait_days` |
| Capacity use | `overall_clinician_utilisation`, `assessment_utilisation` |
| Policy switch backlog | `waiting_list_at_switch` |
| Post-policy backlog | `waiting_list_at_end`, `backlog_decay_total` |

Full glossary: [`des/kpi_docs.py`](../des/kpi_docs.py) — `KPI_GLOSSARY`, `KPI_CALCULATIONS`.

## Audit class

**Role:** accumulate per-patient milestone timestamps during simulation; KPI computation
is deferred to `compute_kpis()` / `Audit.finalize()`.

**Tracks:**

- All fields in `PatientRecord` (above)
- Daily capacity ledger (`capacity_days`)
- Collection window / tri-phase policy timeline (`CollectionWindow`, `SimulationPhases`)

**Does not compute KPIs inline** — `des/kpi.py` enriches patient tables with RTT columns
(`rtt_pathway_status`, `rtt_wait_days`, `rtt_clock_stop`) and runs validation rules.

## Historical resource models

For state mapping of earlier iterations:

| Iteration | Stages | Resource |
|-----------|--------|----------|
| 2 | 7 stage queues + review | One SimPy `Resource` per stage, 24/7 |
| 3 | Same | Calendar-aware appointment slots |
| 4 | 7 workforce stages + review | Per-stage `WorkforceHoursResource` |

See [`notebooks/iteration2.ipynb`](../notebooks/iteration2.ipynb) and
[`PATHWAYS.md`](PATHWAYS.md) modelling history section.

## Related files

- [`PATHWAYS.md`](PATHWAYS.md) — pathway flow and policy context
- [`figures/nhs-neurodevelopmental-pathway.png`](../figures/nhs-neurodevelopmental-pathway.png)
- [`README.md`](../README.md) — project overview and three-run framework
