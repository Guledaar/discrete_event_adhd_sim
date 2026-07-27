# NHS Neurodevelopmental Assessment Pathway — Discrete Event Simulation

Discrete-event simulation (DES) for NHS neurodevelopmental (autism/ADHD) assessment pathways: PTL/backlog, RTT, workforce capacity, and policy what-if analysis.

**Status:** complete.

## Entry points

| Tool | Use |
|------|-----|
| [`demo.ipynb`](demo.ipynb) | Notebook tutorial — `single_run` through Run 1 / 2 / 3 |
| [`streamlit_app/`](streamlit_app/) | Interactive Run 1–3 UI (local or **Streamlit Cloud**) |
| [`GLOSSARY.md`](GLOSSARY.md) | Parameter and KPI definitions |

## Quick start

**Pip / Streamlit Cloud:**

```bash
pip install -r requirements.txt
jupyter lab demo.ipynb          # notebook
./run_streamlit.sh              # local app
```

**Optional Conda (local only):**

```bash
conda env create -f conda/environment.yml
conda activate sim_env
```

Run commands from the **repository root** so `import des` works.

## Deploy on Streamlit Cloud

1. Push to GitHub: `requirements.txt`, `streamlit_app/`, `des/`, `figures/`, `GLOSSARY.md`, `demo.ipynb`.
2. [share.streamlit.io](https://share.streamlit.io/) → **Create app** → main file **`streamlit_app/app.py`**, Python **3.10**.
3. Cloud installs **`requirements.txt`** only — keep **`conda/environment.yml`** under `conda/` (not `environment.yml` at repo root).

Full steps: **[DEPLOY_STREAMLIT.md](DEPLOY_STREAMLIT.md)**.

## Three-run framework

| Run | API | Output |
|-----|-----|--------|
| Run 1 | `run1()` | **T\***, calibration `history` |
| Run 2 | `run2()` | Replications at T\* + CI summaries |
| Run 3 | `run3()` | Policy vs control backlog decay |

Building blocks: `single_run`, `multiple_replication`, `summarise_replications` in [`des/runners.py`](des/runners.py). KPIs via [`des/run_report.py`](des/run_report.py).

## Repository layout

```
discrete_event_adhd_sim/
├── README.md
├── GLOSSARY.md
├── DEPLOY_STREAMLIT.md
├── demo.ipynb                 # runner tutorial
├── requirements.txt           # Streamlit Cloud + pip
├── run_streamlit.sh
├── conda/environment.yml      # local Conda (sim_env)
├── des/                       # simulation core
├── streamlit_app/             # multipage app
├── figures/
├── notebooks/
└── tests/
```

## Tests

```bash
pytest tests/ -v
python -m des.verification
```

## License

See [LICENSE](LICENSE).
