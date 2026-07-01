# adhd-simpy — NHS Adult Autism Assessment DES

Discrete-event simulation (DES) of the NHS adult autism assessment pathway, built with [SimPy](https://simpy.readthedocs.io/).

Extracted from `iteration4.ipynb` into an installable Python package for unit testing, CI, and reuse.

## Install

```bash
pip install -e .
```

Or with conda:

```bash
conda env create -f environment.yaml
conda activate adhd-sim
pip install -e .
```

## Quick start

```python
from adhd_simpy.Model import single_run
from adhd_simpy.Model.devon_parameters import devon_experiment, devon_run_kwargs

# Devon (DAANA) data-driven scenario
experiment = devon_experiment()
results = single_run(experiment, rep=0, **devon_run_kwargs())
print(results["ACCESS_REFERRAL_TO_DIAGNOSIS_RTT_DAYS"])
```

Or with default parameters:

```python
from adhd_simpy.Model import Audit, Experiment, single_run, multiple_runs

auditor = Audit()
experiment = Experiment(auditor=auditor)

# One replication (365-day collection, no warm-up)
results = single_run(experiment, rep=0, warmup_days=0, run_length=365)
print(results["ACCESS_REFERRAL_TO_DIAGNOSIS_RTT_DAYS"])

# Multiple replications
df = multiple_runs(experiment, n_reps=5, warmup_days=0, run_length=365)
```

## Package layout

```
adhd_simpy/
  Model/
    parameters.py      # Scenario defaults (edit here for scenarios)
    distributions.py   # RNG distribution wrappers
    audit.py           # KPI collection
    experiment.py      # Scenario config + flow counters
    patient.py         # SimPy patient process
    resources.py       # WorkforceHoursResource
    system.py          # AutismPathwaySystem
    simulation.py      # single_run(), multiple_runs()
    verification.py    # Automated V&V tests
```

## Tests

```bash
pytest tests/ -v
```

## Notebook

- **`demo.ipynb`** — full model documentation (sections 1–9): background, DES architecture, execution, applications, V&V, future work
- **`iteration4.ipynb`** — full model documentation and extended analysis

Import from the package instead of redefining classes:

```python
from adhd_simpy.Model import Audit, Experiment, single_run, multiple_runs
from adhd_simpy.Model.parameters import WARMUP_DAYS, RUN_LENGTH, REFERRALS_PER_DAY
```
