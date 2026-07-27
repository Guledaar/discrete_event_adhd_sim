# Glossary — model parameters and KPIs

This document defines **canonical names** used in `des.experiment.Experiment`, `des.run_report`, and `des.runners`. Code keys are `snake_case`.

**Display labels** in the Streamlit app (Glossary page, Run 1–3 tables and charts) use:

- `des.run_report.kpi_label()` — base names from `KPI_LABELS`
- `streamlit_app.kpi_display.streamlit_kpi_label()` — same labels; **wait durations** append **(yr)** (values are shown in years in the UI)
- Run 1 calibration targets: `calibration_target_label()` — prefixes **`[Stock]`** or **`[Flow]`**

---

## Naming conventions

| Term | Meaning |
|------|---------|
| **Stock** | Snapshot at the simulation **horizon** (`sim_end`) — who is where and how long they have waited so far. |
| **Flow** | Activity in a rolling window ending at the horizon (`flow_window_days`) — throughput and waits for recent completions. |
| **Backlog / PTL** | Patients on an **incomplete** RTT pathway at the horizon (accepted, not exited, clock still running). Same count as `backlog_patients_at_horizon`. |
| **RTT** | Referral-to-treatment clock: days from **referral arrival** to **exit** (or to horizon if still incomplete). Rejected referrals **nullify** the RTT clock. |
| **T\*** | **Matching period** from Run 1 — simulation day when calibrated headline KPIs match provider targets; policy switch time in Run 3. |
| **Warm-up** | Initial days where the model runs but KPI collection may be excluded (`warm_up` in runners). |
| **Replication** | Independent stochastic repeat with a different RNG seed (`rep`); Run 2/3 summarise mean, SD, and 95% CI. |

**Units:** Simulation time is in **days** (7-day calendar). Capacity is **clinician-hours** on **weekdays**. Probabilities are **0–1** unless labelled as **%**. Utilisation headline KPI `capacity_used_pct` is **0–100**. **Wait durations** are computed in days in the model; the **Streamlit app displays waits in years** (÷ 365.25) unless noted otherwise.

---

## Model parameters

Parameters below are attributes on `Experiment` and keys in `Experiment.to_kwargs()`. Defaults live in `des.config`.

### Demand and triage

| Parameter | Type / units | Definition |
|-----------|----------------|------------|
| `iat` | days | Mean **inter-arrival time** between referrals (exponential arrivals). Related UI input: **monthly referrals** → `iat = 1 / (monthly_referrals / working_days_per_month)`. |
| `pct_referral_rejected` | 0–1 | Probability a referral is **rejected at triage** (RTT nullified). |
| `pct_admin_removal` | 0–1 | Probability an **accepted** referral is removed in **admin review** before assessment. |

### Assessment

| Parameter | Type / units | Definition |
|-----------|----------------|------------|
| `assessment_appointment_counts` | list of int | Allowed numbers of **assessment appointments** per patient (e.g. 2, 3, 4). |
| `assessment_appointment_probs` | list of 0–1 | Probability of each appointment count (sums to 1). |
| `assessment_gap_days` | days | Minimum **calendar gap** between consecutive assessment appointments. |
| `duration_assessment` | hours (3 values) | **Triangular** distribution for one assessment appointment duration: min, mode, max clinician-hours. |

### Diagnosis and post-diagnosis route

| Parameter | Type / units | Definition |
|-----------|----------------|------------|
| `pct_diagnosis` | 0–1 | Probability of a **positive diagnosis** after assessment completes. |
| `pct_virtual_support` | 0–1 | Among diagnosed patients, probability of **virtual support** exit route (vs clinical workshops). |

### Workshops (clinical pathway)

| Parameter | Type / units | Definition |
|-----------|----------------|------------|
| `workshop_group_size` | patients | Target **group size** when forming a workshop cohort from the queue. |
| `workshop_num_sessions` | count | **Sessions per programme** for each workshop group. |
| `workshop_session_interval_weeks` | weeks | **Gap between sessions** within a programme (converted to days in the model). |
| `workshop_max_wait_days` | days | Maximum wait in the workshop queue before a **partial group** can start. |
| `duration_workshop_session` | hours (3 values) | **Triangular** distribution for one workshop session’s clinician-hours per patient. |

### Workforce (shared bottleneck)

| Parameter | Type / units | Definition |
|-----------|----------------|------------|
| `workforce_hours_per_day` | hours / weekday | **Clinician hours released each weekday** for the shared pool (assessment + workshop activity). |
| `workforce_hours_workshop_session` | hours | Clinician-hours **reserved per patient per workshop session** when scheduling groups. |

### Reproducibility (not pathway physics)

| Parameter | Definition |
|-----------|------------|
| `random_number_set` | Base RNG seed. |
| `use_fixed_seed` | If true, replication `rep` uses `base_seed + rep`. |
| `scenario_name` | Label for outputs and Run 3 arms. |

### UI-only (Streamlit)

| UI label | Maps to |
|----------|---------|
| `monthly_referrals` | `iat` (see above) |

### Run 3 policy overrides

Any `Experiment` parameter above can appear in `policy_overrides` at time **T\*** (e.g. `workforce_hours_per_day`, `pct_admin_removal`, `iat`).

---

## Run framework outputs (not model params)

| Key | Definition |
|-----|------------|
| `optimal_matching_period_days` / `matching_period_days` | Calibrated **T\*** (days). |
| `flow_window_days` | Rolling window for **flow** KPIs (default often 365 days). |
| `decay_period_days` | Run 3 post-switch observation window (days). |
| `warm_up` | Days discarded before collection in Run 2. |

---

## KPI report sections (`RunReport`)

Each replication produces tables; together they form the structured report from `build_run_report()`.

| Section key | Contents |
|-------------|----------|
| `pathway_funnel` | **Stock** counts at horizon by pathway stage (referrals, assessment, diagnosis, workshops, still on pathway). |
| `pathway_exits` | Counts by **exit route** (all-time and within flow window). |
| `waits_stock_by_stage` | **Stock** waits at horizon by stage (completed vs still waiting, breach counts). Mean/median/**p25/p95** wait columns shown in **years** in Streamlit. |
| `waits_flow_by_stage` | **Flow** waits for milestones **completed in the window**. |
| `rtt_waits_stock` | RTT wait stats by **cohort** at horizon (`backlog`, `completed_all`, `completed_clinical`). |
| `backlog_waiting_time_report` | Single-row **backlog / PTL** waiting-time summary (`n`, mean, median) from `run_report_summary()`. |
| `rtt_breaches_stock` | **18- and 52-week** breach counts and **%** by RTT cohort. |
| `capacity_utilisation` | Weekday **hours released / used / unused**, assessment vs workshop split, **%** of released hours. |
| `assessment_adherence` | Share of patients completing required assessment appointments. |
| `workshop_group_stats` | Per-group size and timing (join → start → complete). |
| `activity_flow` | **Flow** event counts and per-month rates in the window. |

---

## Headline KPIs (calibration and dashboards)

Flat scalars from `headline_kpis()` / `kpi_snapshot()`. Use these names in Run 1 **targets**.

| KPI key | Streamlit label | Units | Definition |
|---------|-----------------|--------|------------|
| `backlog_patients_at_horizon` | Backlog / PTL — count at horizon | count | **PTL / backlog** — incomplete RTT pathways at horizon (accepted, active cohort). |
| `backlog_mean_wait_days` | Backlog / PTL — mean RTT wait (yr) | days (UI: years) | Mean **RTT wait** among backlog cohort at horizon. |
| `backlog_median_wait_days` | Backlog / PTL — median RTT wait (yr) | days (UI: years) | Median **RTT wait** among backlog cohort at horizon. |
| `completed_mean_rtt_days` | Completed pathway — mean RTT wait (yr) | days (UI: years) | Mean RTT for **completed clinical** exits (excludes admin removal). |
| `backlog_over_18_weeks_pct` | Backlog / PTL — over 18 weeks (%) | % | Share of backlog patients waiting **> 18 weeks** (126 days). |
| `backlog_over_52_weeks_pct` | Backlog / PTL — over 52 weeks (%) | % | Share of backlog patients waiting **> 52 weeks** (364 days). |
| `backlog_over_18_weeks` | Backlog / PTL — over 18 weeks (count) | count | Count of backlog patients over 18 weeks. |
| `backlog_over_52_weeks` | Backlog / PTL — over 52 weeks (count) | count | Count of backlog patients over 52 weeks. |
| `capacity_used_pct` | Clinician utilisation (%) | % | **Used ÷ released** clinician-hours over the run (×100). |
| `workshop_hours_share_pct` | Workshop hours share (%) | % | Workshop hours as **% of released** clinician-hours. |
| `assessments_per_month` | Flow — rate: assessments finished (/ month) | rate | Assessments **finished** in flow window ÷ window length in months. |
| `diagnoses_per_month` | Flow — rate: diagnoses (/ month) | rate | Positive **diagnoses** in flow window ÷ months. |
| `referral_to_first_assessment_mean_days` | Referral → first assessment (yr) | days (UI: years) | Mean wait among patients **still waiting** for first assessment at horizon. |
| `referrals_total` | Referrals received (total) | count | All referrals received by horizon. |
| `referrals_accepted_pct` | Referrals accepted (%) | % | Accepted ÷ all referrals × 100. |
| `assessment_completion_pct` | Assessment appointment adherence (%) | % | Assessment appointment adherence (fully completed required visits). |
| `horizon_days` | Simulation horizon (days) | days | Simulation end (`sim_end`). |
| `flow_window_days` | Flow window length (days) | days | Flow window length used for rates. |

### Flow-window headline KPIs (Run 1 calibration & Run 2–3)

| KPI key | Streamlit label |
|---------|-----------------|
| `flow_count_referrals` | Flow — count: Referrals received |
| `flow_count_assessments_started` | Flow — count: Assessments started |
| `flow_count_assessments_finished` | Flow — count: Assessments finished |
| `flow_count_diagnoses` | Flow — count: Diagnoses (positive) |
| `flow_wait_mean_days_assessments_started` | Flow — mean wait: Referral → first assessment (yr) |
| `flow_wait_median_days_assessments_started` | Flow — median wait: Referral → first assessment (yr) |
| `flow_wait_mean_days_assessments_finished` | Flow — mean wait: Referral → diagnosis decision (yr) |
| `flow_wait_median_days_assessments_finished` | Flow — median wait: Referral → diagnosis decision (yr) |

### RTT cohorts (in `rtt_waits_stock` / `rtt_breaches_stock`)

| Cohort key | Definition |
|------------|------------|
| `backlog` | Incomplete RTT at horizon (PTL). |
| `completed_all` | RTT clock stopped — any exit. |
| `completed_clinical` | Completed excluding **admin removal**. |

### Activity flow metrics (in `activity_flow`)

| Metric key | Definition |
|------------|------------|
| `referrals_in_window` | Referrals arriving in the flow window. |
| `referrals_accepted_in_window` | Accepted referrals in the window. |
| `assessments_started_in_window` | Assessments started in the window. |
| `assessments_finished_in_window` | Assessments completed in the window. |
| `diagnoses_in_window` | Positive diagnoses in the window. |
| `workshops_joined_in_window` | Patients joining workshop queue in the window. |
| `workshops_started_in_window` | Workshop programmes started in the window. |
| `workshops_finished_in_window` | Workshop programmes completed in the window. |
| `virtual_completed_in_window` | Virtual support exits in the window. |
| `all_exits_in_window` | All pathway exits in the window. |

Each flow row also has `count_in_window` and `per_month` in the table.

---

## Run 3 — policy and decay KPIs

| KPI key | Streamlit label | Units | Definition |
|---------|-----------------|--------|------------|
| `backlog_at_switch` | Backlog / PTL — count at T* (policy switch) | count | Backlog / PTL at **T\*** immediately before policy applies. |
| `backlog_at_end` | Backlog / PTL — count at end of decay | count | Backlog at end of **decay window** (T\* + decay period). |
| `backlog_decay` | Backlog / PTL — reduction (T* → end) | count | `backlog_at_switch − backlog_at_end` (positive = shrinkage). |
| `backlog_decay_per_month` | Backlog / PTL — reduction per month | count / month | `backlog_decay` normalised by decay length in months. |
| `delta_backlog_at_end` | Policy − baseline: backlog at end of decay | count | **Policy − baseline** backlog at end (paired replications). |
| `delta_backlog_decay` | Policy − baseline: backlog reduction | count | Policy − baseline **backlog_decay**. |
| `delta_backlog_decay_per_month` | Policy − baseline: reduction per month | count / month | Policy − baseline decay rate. |

Policy KPI **time series** (checkpoints after T\*) track the same headline keys as Run 1 where listed in `POLICY_KPI_TIME_SERIES_KEYS`.

---

## Legacy aliases (deprecated)

Older notebooks and targets may use these; they map to canonical keys via `normalize_kpi_key()` / `kpi_snapshot()`.

| Legacy key | Canonical key | Notes |
|------------|---------------|--------|
| `waiting_list_size` | `backlog_patients_at_horizon` | Same count. |
| `rtt_incomplete_mean_days` | `backlog_mean_wait_days` | Same mean wait. |
| `overall_clinician_utilisation` | `capacity_used_pct` | Legacy is **0–1**; canonical is **%** (targets auto-scale if ≤ 1). |
| `workshop_utilisation` | `workshop_hours_share_pct` | Legacy is **0–1**; canonical is **%**. |
| `ptl_over_*_weeks_pct` | `backlog_over_*_weeks_pct` | Same breach percentages. |
| `waiting_list_at_switch` / `_end` | `backlog_at_switch` / `backlog_at_end` | Run 3 arms. |
| `delta_waiting_list_end` | `delta_backlog_at_end` | Run 3 comparison. |

Programmatic labels: `from des.run_report import kpi_label, KPI_LABELS` and `from streamlit_app.kpi_display import streamlit_kpi_label`.
