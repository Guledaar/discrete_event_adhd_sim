"""Neurodevelopmental(Autism) Pathway Discrete Event Simulation."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    import scipy  # noqa: F401 — des.runners
except ImportError:
    import streamlit as st

    st.set_page_config(page_title="NHS Pathway DES — setup error")
    st.error("Missing **scipy**. Streamlit Cloud: commit root **requirements.txt** and reboot.")
    st.code("pip install -r requirements.txt")
    st.stop()

import streamlit as st
from helpers import init_session_state
from kpi_reporting import render_session_status_sidebar

_FIGURES = Path(__file__).resolve().parent.parent / "figures"
_PATHWAY_FLOWCHART = _FIGURES / "nhs-neurodevelopmental-pathway.png"

st.set_page_config(
    page_title="Neurodevelopmental(Autism) Pathway Discrete Event Simulation",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_session_state()
render_session_status_sidebar()

st.title("Neurodevelopmental(Autism) Pathway Discrete Event Simulation")

st.markdown(
    """
This application models an **Neurodevelopmental(Autism) Pathway** using discrete-event
simulation. Use the pages in the sidebar to calibrate the model, run a stochastic
baseline, and test policy interventions.
"""
)

if _PATHWAY_FLOWCHART.is_file():
    st.image(
        str(_PATHWAY_FLOWCHART),
        caption="NHS neurodevelopmental pathway — referral through assessment, diagnosis, and exit routes.",
        use_container_width=True,
    )
else:
    st.warning(f"Pathway flowchart not found: `{_PATHWAY_FLOWCHART}`")

st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
### The problem

Referrals arrive continuously. Patients compete for **limited weekday clinician hours**,
pass triage and admin review, complete multi-appointment assessments, receive a diagnosis,
and exit via virtual support or a **clinical workshop programme**.

Services must track:
- **PTL (Patient Tracking List)** — incomplete pathways in the system
- **RTT (Referral-to-Treatment)** — days from referral to exit
- **18-week / 52-week standards** — waiting-time breaches
"""
    )

with col2:
    st.markdown(
        """
### How DES solves it

| Challenge | Approach |
|-----------|----------|
| Random arrivals & variation | Stochastic processes (inter-arrivals, triage, diagnosis) |
| Shared capacity bottleneck | SimPy processes compete for a **weekday clinician-hour pool** |
| Long horizons (years) | Time jumps between events |
| Policy what-if | Switch parameters mid-simulation at time **T*** |
| Uncertainty | Multiple replications → mean, SD, 95% CI |
"""
    )

st.markdown("---")

st.markdown(
    """
### How to use this app

| Step | Page | What it does |
|------|------|--------------|
| **1** | **Glossary** | Definitions of all **parameters** and **KPIs** |
| **2** | **Run 1 — Calibration** | Set model parameters; find **T\\*** where simulated PTL matches provider target |
| **3** | **Run 2 — Baseline** | Run `N` replications at T\\* → baseline KPIs with confidence intervals |
| **4** | **Run 3 — Policy** | Apply a policy at T\\*; **N baseline + N policy** replications → paired mean ± CI |

**Pipeline:** `Experiment` → `AutismPathwaySystem` → `Audit` → `build_run_report` → KPI tables

Each run produces:
- **Stock** metrics — snapshot at horizon (PTL, waits, breach %)
- **Flow** metrics — completions in the rolling window (throughput, recent waits)
- Stage counts, assessment/diagnosis rates

See **Glossary** in the sidebar for full parameter and KPI definitions.
"""
)

if st.session_state.get("t_star"):
    t = float(st.session_state["t_star"])
    r2 = st.session_state.get("run2_result")
    r3n = len([s for s in (st.session_state.get("run3_scenario_runs") or []) if not s.get("is_baseline")])
    extra = []
    if r2 is not None:
        extra.append(f"Run 2: **{r2.get('n_reps')}** baseline rep(s)")
    if r3n:
        extra.append(f"Run 3: **{r3n}** policy scenario(s) this session")
    suffix = f" · {' · '.join(extra)}" if extra else ""
    st.success(
        f"T* calibrated: **{t:.0f} days** ({t / 365.25:.1f} years). "
        f"Proceed to **Run 2** (baseline uncertainty) or **Run 3** (policy decay).{suffix}"
    )
else:
    st.info("Start with **Run 1 — Calibration** in the sidebar, or open **Glossary** for parameter and KPI definitions.")
