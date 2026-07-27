"""NumPy-backed random variate wrappers for the simulation engine.

Each distribution holds its own :class:`~numpy.random.Generator` instance,
seeded from :meth:`~des.experiment.Experiment.init_sampling` so replications
are independent and reproducible.

See Also
--------
des.experiment.Experiment
    Constructs one instance of each distribution class per scenario.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any, List, Optional

import numpy as np


class Distribution(ABC):
    """
    Abstract base for distribution wrappers used by :class:`~des.experiment.Experiment`.

    Subclasses implement :meth:`sample` to draw from a fixed distribution
    with an optional per-stream seed.
    """

    @abstractmethod
    def sample(self, size: Optional[int] = None) -> Any:
        """
        Draw one or more random variates.

        Parameters
        ----------
        size : int, optional
            Number of draws. When ``None``, returns a scalar (or single discrete
            outcome).

        Returns
        -------
        array-like or scalar
            Sample(s) from the distribution.
        """
        raise NotImplementedError


class Bernoulli(Distribution):
    """
    Bernoulli(p) trial wrapper.

    Parameters
    ----------
    p : float
        Success probability in ``[0, 1]``.
    random_seed : int, optional
        Seed for :class:`~numpy.random.Generator`.
    """

    def __init__(self, p: float, random_seed: Optional[int] = None) -> None:
        """See class docstring for parameter descriptions."""
        self.rand = np.random.default_rng(seed=random_seed)
        self.p = p

    def sample(self, size: Optional[int] = None) -> np.ndarray:
        """
        Draw Bernoulli trial(s).

        Parameters
        ----------
        size : int, optional
            Number of trials.

        Returns
        -------
        numpy.ndarray
            Array of 0/1 outcomes.
        """
        return self.rand.binomial(n=1, p=self.p, size=size)


class Exponential(Distribution):
    """
    Exponential(mean) inter-arrival or duration wrapper.

    Parameters
    ----------
    mean : float
        Mean of the distribution (SimPy time units are days in this model).
    random_seed : int, optional
        Seed for :class:`~numpy.random.Generator`.
    """

    def __init__(self, mean: float, random_seed: Optional[int] = None) -> None:
        """See class docstring for parameter descriptions."""
        self.rand = np.random.default_rng(seed=random_seed)
        self.mean = mean

    def sample(self, size: Optional[int] = None) -> np.ndarray:
        """
        Draw exponential variate(s).

        Parameters
        ----------
        size : int, optional
            Number of draws.

        Returns
        -------
        numpy.ndarray
            Non-negative samples with mean ``self.mean``.
        """
        return self.rand.exponential(self.mean, size=size)


class Triangular(Distribution):
    """
    Triangular(low, mode, high) duration wrapper.

    Parameters
    ----------
    low : float
        Minimum value.
    mode : float
        Mode (peak) of the distribution.
    high : float
        Maximum value.
    random_seed : int, optional
        Seed for :class:`~numpy.random.Generator`.
    """

    def __init__(self, low: float, mode: float, high: float, random_seed: Optional[int] = None) -> None:
        """See class docstring for parameter descriptions."""
        self.rand = np.random.default_rng(seed=random_seed)
        self.low = low
        self.high = high
        self.mode = mode

    def sample(self, size: Optional[int] = None) -> np.ndarray:
        """
        Draw triangular variate(s).

        Parameters
        ----------
        size : int, optional
            Number of draws.

        Returns
        -------
        numpy.ndarray
            Samples in ``[low, high]``.
        """
        return self.rand.triangular(self.low, self.mode, self.high, size=size)


class Discrete(Distribution):
    """
    Finite discrete distribution over ``elements`` with probabilities ``probabilities``.

    Parameters
    ----------
    elements : list
        Support of the distribution (e.g. appointment counts ``[2, 3, 4, 5]``).
    probabilities : list of float
        Probabilities summing to 1.
    random_seed : int, optional
        Seed for :class:`~numpy.random.Generator`.

    Raises
    ------
    ValueError
        If ``elements`` and ``probabilities`` differ in length or probabilities
        do not sum to 1.
    """

    def __init__(self, elements: List[Any], probabilities: List[float], random_seed: Optional[int] = None) -> None:
        """See class docstring for parameter descriptions."""
        self.elements = elements
        self.probabilities = probabilities
        if len(elements) != len(probabilities):
            raise ValueError("Elements and probabilities arguments must be of the same length")
        if not math.isclose(sum(probabilities), 1.0):
            raise ValueError("Probabilities must sum to 1")
        self.cum_probs = np.add.accumulate(probabilities)
        self.rng = np.random.default_rng(random_seed)

    def sample(self, size: Optional[int] = None) -> Any:
        """
        Draw element(s) according to ``probabilities``.

        Parameters
        ----------
        size : int, optional
            Number of draws. When ``None``, returns a single element from
            ``elements``.

        Returns
        -------
        Any or numpy.ndarray
            Selected element(s).
        """
        return self.elements[np.digitize(self.rng.random(size), self.cum_probs)]
