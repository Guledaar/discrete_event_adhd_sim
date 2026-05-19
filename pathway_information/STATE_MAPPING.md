# Autism State Mapping (Iteration 2)

## Status

State and event mapping is almost completed.

- Implemented mapping: core diagnostic and post-diagnostic pathway flow.
- Remaining mapping work: finalize resource-calendar related state behavior.

## Purpose

This file maps conceptual pathway states to implemented model stages and counters in `iteration2.ipynb`.

## State-to-Stage Mapping

1. Referral Arrived
- Stage: referral entry
- Related counters: `N_REFERRALS_ARRIVED`

2. Triage Decision
- Stage: referral triage gate
- Related counters: `N_REF_ACCEPTED`, `N_REF_REJECTED`

3. Screening
- Stage: screening service
- Related counters: `N_SCREENING_ACCEPTED`, `N_SCREENING_COMPLETED`, `N_SCREENING_DISCHARGED`

4. Pre-Assessment
- Stage: pre-assessment service
- Related counters: `N_PRE_ASSESS_ACCEPTED`, `N_PRE_ASSESS_COMPLETED`, `N_PRE_ASSESS_REJECTED`

5. Assessment
- Stage: assessment service
- Related counters: `N_ASSESSMENT_ACCEPTED`, `N_ASSESSMENT_COMPLETED`, `N_NON_DIAGNOSIS_ASSESSMENT`

6. Further Assessment
- Stage: further assessment service
- Related counters: `N_FURTHER_ASSESS_ACCEPTED`, `N_FURTHER_ASSESS_COMPLETED`, `N_NON_DIAGNOSIS_FURTHER_ASSESSMENT`

7. Diagnosis Confirmed
- Stage: post-assessment diagnostic outcome
- Related counters: `N_DIAGNOSIS_TOTAL`

8. Post-Diagnostic Clinical Support
- Stage: clinical support branch
- Related counters: `N_POST_DIAG_CLINICAL_ACCEPTED`, `N_POST_DIAG_CLINICAL_COMPLETED`

9. Post-Diagnostic Other Support
- Stage: other/community support branch
- Related counters: `N_POST_DIAG_OTHER_ACCEPTED`, `N_POST_DIAG_OTHER_COMPLETED`

10. Review / Removal / Discharge
- Stage: review service and terminal branch
- Related counters: `N_REMOVAL_DISCHARGE`, `N_SELF_REMOVED`, `N_COMPLETED`

11. Exit / End-of-Run Inventory
- Stage: pathway exit tracking
- Related counters: `N_EXITED_TOTAL`, `N_IN_SYSTEM_END`

## Resource Mapping (Current)

Current Iteration 2 design uses one SimPy resource per operational stage:

- screening
- pre-assessment
- assessment
- further assessment
- post-diagnostic clinical
- post-diagnostic other
- review/discharge

Current assumption:

- Resources are modeled as available 24/7.
- No explicit working-day calendars are applied yet.

## Resource Mapping (Next)

Planned next step is resource modelling realism:

1. Working-day and working-hours constraints
2. Calendar-aware capacity logic
3. Optional shift and availability variation
