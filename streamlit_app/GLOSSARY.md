# Glossary — using this app

Plain-language definitions for **Run 1–3**, the **Glossary** page, and tables or charts in the sidebar. **Waits are shown in years** unless a field says “days”.

---

## Core ideas

| Term | Meaning |
|------|---------|
| **Stock** | Snapshot at the **horizon** (end of the run or checkpoint): who is on the pathway and how long they have waited **so far**. |
| **Flow** | Activity in a **rolling window** ending at that horizon: recent throughput and waits for people who **just completed** a step. |
| **Backlog / PTL** | Patients still on an **incomplete** pathway at the horizon (accepted, not yet exited). |
| **RTT (referral to treatment)** | Time from **referral** to **exit** (or to the horizon if still waiting). Rejected referrals are not counted in RTT waits. |
| **T\*** | Horizon from **Run 1** where your chosen KPI matches the provider target; in **Run 3**, the time when a **policy change** applies. |
| **Flow window** | Number of **days** before the horizon used for **flow** counts and waits (often 365). |
| **Replication** | Repeat of the same scenario with random variation; Run 2/3 show **mean** and **95% confidence interval** when you run more than one. |
| **MAPE** | Run 1 match error: how far the simulated calibration target is from your target value (lower is closer). |

**Capacity:** Weekday **clinician hours** are shared between **assessment** and **clinical workshops**. That pool is the usual bottleneck when utilisation is high.

---

## Run 1 — model settings (sidebar page)

### Demand and triage

| Setting | Meaning |
|---------|---------|
| **Monthly referrals** | Average new referrals per calendar month (drives how busy the service is). |
| **Referral rejected (triage) %** | Share of referrals stopped at triage. |
| **Admin removal %** | Share of accepted referrals removed before assessment starts. |

### Capacity

| Setting | Meaning |
|---------|---------|
| **Clinician hours / weekday** | Clinician hours available each **weekday** for assessments and workshops combined. |
| **Clinician hours per workshop session** | Hours charged per patient per workshop session when a group runs. |

### Pathway probabilities

| Setting | Meaning |
|---------|---------|
| **Diagnosis rate %** | Share of patients who complete assessment and receive a diagnosis. |
| **Virtual support route %** | Among diagnosed patients, share who leave via **virtual support** (others go to **workshops**). |

### Assessment programme

| Setting | Meaning |
|---------|---------|
| **Days between assessment appointments** | Minimum gap between two assessment visits for the same patient. |
| **Min / Mode / Max hours** (assessment) | Typical length of one assessment visit (clinician hours). |
| **Assessment appointment mix** | How many visits each patient needs (e.g. 2–6) and how common each option is. |

### Workshop programme

| Setting | Meaning |
|---------|---------|
| **Workshop group size** | Target number of patients in one workshop group. |
| **Sessions per programme** | Number of sessions in a full workshop programme. |
| **Weeks between sessions** | Gap between sessions in the same programme. |
| **Max days to form workshop group** | Longest wait allowed to fill a group before a partial group may start. |
| **Min / Mode / Max hours** (workshop) | Clinician hours for one workshop session per patient. |

### Calibration

| Setting | Meaning |
|---------|---------|
| **Calibration target KPI** | One **stock** or **flow** KPI matched to your **target value** (see below). |
| **Target value** | Provider figure for that KPI (waits in **years** for wait targets). |
| **Match tolerance (MAPE)** | How close a match must be to stop searching for T\*. |
| **Max search horizon (years)** | Latest simulated year Run 1 will try. |
| **Horizon step (days)** | How much the simulated end date increases each try. |
| **Flow window (days)** | Window for **flow** KPIs at each calibration step. |

### Stock matching targets

- **Backlog / PTL — count at horizon** — how many incomplete pathways at T\*.
- **Backlog / PTL — mean RTT wait (yr)** — average wait among that backlog.
- **Backlog / PTL — median RTT wait (yr)** — middle wait among that backlog.

### Flow matching targets

- **Flow — mean/median wait: Referral → first assessment (yr)** — for patients who **started** assessment in the flow window.
- **Flow — mean/median wait: Referral → diagnosis decision (yr)** — for patients who **finished** assessment in the flow window.

---

## Run 2 — baseline at T\*

| Output | Meaning |
|--------|---------|
| **Headline KPIs** | Backlog size and waits at **T\***; flow counts and waits with uncertainty. |
| **Bottleneck panel** | Where patients are **still waiting** by stage, wait times, and **overall / assessment / workshop** utilisation. |
| **Analyst detail** | Deeper tables: RTT waits, 18/52-week breaches, waits by stage, pathway activity. |

---

## Run 3 — policy

| Term | Meaning |
|------|---------|
| **Baseline (control)** | Same T\* and decay period, **no** policy change. |
| **Policy arm** | Parameters change at **T\*** (demand, capacity, triage, assessment, workshops). |
| **Decay period** | How long the simulation continues **after** T\* to see backlog change. |
| **Backlog at T\*** | PTL count just before the policy switch. |
| **Backlog at end of decay** | PTL count at the end of the decay window. |
| **Backlog reduction (T\* → end)** | Drop in PTL count (positive = list shrank). |
| **Policy − baseline** | Difference between policy and control on the same replication seed. |

Policy levers use the same labels as **Run 1** (grouped as Demand/triage, Capacity, Pathway, Assessment, Workshops).

---

## Headline KPIs (all runs)

| Label in app | Meaning |
|--------------|---------|
| **Backlog / PTL — count at horizon** | Incomplete pathways at the horizon. |
| **Backlog / PTL — mean / median RTT wait (yr)** | Wait among backlog patients only. |
| **Backlog / PTL — over 18 weeks (%)** | Share of backlog waiting longer than 18 weeks. |
| **Backlog / PTL — over 52 weeks (%)** | Share of backlog waiting longer than 52 weeks. |
| **Clinician utilisation (%)** | Share of released weekday clinician hours that were used. |
| **Assessment hours (% of released capacity)** | Assessment share of all hours released. |
| **Workshop hours (% of released capacity)** | Workshop share of all hours released. |
| **Flow — rate: assessments finished (/ month)** | Assessment completions per month in the flow window. |
| **Flow — rate: diagnoses (/ month)** | Diagnoses per month in the flow window. |
| **Flow — count: …** | Number of events (referrals, assessments started/finished, diagnoses) in the flow window. |
| **Flow — mean/median wait: … (yr)** | Waits for recent completions (referral → assessment or diagnosis). |

---

## Bottleneck panel

| View | Meaning |
|------|---------|
| **Patients still waiting (by stage)** | Largest queues at the horizon (e.g. before first assessment). |
| **Median wait (yr)** | Typical wait among those still waiting at each stage. |
| **Pathway stock counts** | How many patients sit at major steps (in assessment, in workshops, still on pathway). |
| **Insight line** | Highlights the biggest queue and warns when clinician utilisation is very high. |

---

## Waits by pathway stage (analyst tables)

Stages describe **milestones** from referral onward, for example:

- Referral → first assessment  
- Referral → diagnosis decision  
- Referral → workshop queue / start / finish  
- Referral → virtual support exit  

**Still waiting** counts patients who have not reached that milestone yet at the horizon.

---

## Access standards

| Term | Meaning |
|------|---------|
| **18-week standard** | Wait longer than **126 days** from referral. |
| **52-week standard** | Wait longer than **364 days** from referral. |

Breaches are reported for the **backlog** and by stage where shown in analyst tables.
