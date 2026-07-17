"""
Package entry point for ``python -m des``.

Runs a short demo ``single_run`` and a tiny ``multiple_replications`` batch.
"""

from des import Audit, Experiment, multiple_replications, single_run

if __name__ == "__main__":
    experiment = Experiment(audit=Audit())
    print(single_run(experiment, rep=0, warmup_days=0, collection_days=365))
    print(
        multiple_replications(
            experiment,
            n_reps=3,
            warmup_days=0,
            collection_days=180,
        ).mean(numeric_only=True)
    )
