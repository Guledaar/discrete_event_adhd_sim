"""NumPy-backed random variate wrappers for the simulation engine."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any, List, Optional

import numpy as np


class Distribution(ABC):
    """Abstract base for distribution wrappers used by :class:`~des.experiment.Experiment`."""

    @abstractmethod
    def sample(self, size: Optional[int] = None) -> Any:
        raise NotImplementedError()


class Bernoulli(Distribution):
    def __init__(self, p: float, random_seed: Optional[int] = None) -> None:
        self.rand = np.random.default_rng(seed=random_seed)
        self.p = p

    def sample(self, size: Optional[int] = None) -> np.ndarray:
        return self.rand.binomial(n=1, p=self.p, size=size)


class Exponential(Distribution):
    def __init__(self, mean: float, random_seed: Optional[int] = None) -> None:
        self.rand = np.random.default_rng(seed=random_seed)
        self.mean = mean

    def sample(self, size: Optional[int] = None) -> np.ndarray:
        return self.rand.exponential(self.mean, size=size)


class Triangular(Distribution):
    def __init__(self, low: float, mode: float, high: float, random_seed: Optional[int] = None) -> None:
        self.rand = np.random.default_rng(seed=random_seed)
        self.low = low
        self.high = high
        self.mode = mode

    def sample(self, size: Optional[int] = None) -> np.ndarray:
        return self.rand.triangular(self.low, self.mode, self.high, size=size)


class Discrete(Distribution):
    def __init__(self, elements: List[Any], probabilities: List[float], random_seed: Optional[int] = None) -> None:
        self.elements = elements
        self.probabilities = probabilities
        if len(elements) != len(probabilities):
            raise ValueError("Elements and probabilities arguments must be of the same length")
        if not math.isclose(sum(probabilities), 1.0):
            raise ValueError("Probabilities must sum to 1")
        self.cum_probs = np.add.accumulate(probabilities)
        self.rng = np.random.default_rng(random_seed)

    def sample(self, size: Optional[int] = None) -> Any:
        return self.elements[np.digitize(self.rng.random(size), self.cum_probs)]
