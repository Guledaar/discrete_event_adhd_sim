"""
Shim for Run 3 (policy switch at T* with optional decay).

Prefer::

    from des.runs import run3, execute_run3
"""
from des.runs.run import execute_run3, run3

__all__ = ["run3", "execute_run3"]
