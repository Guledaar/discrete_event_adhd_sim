"""NumPy-backed random variate wrappers for the simulation engine."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any, List, Optional

import numpy as np


def generate_seed_vector(one_seed_to_rule_them_all: int = 42, size: int = 20) -> np.ndarray:
    """
    Generate a reproducible array of independent integer seeds.

    Parameters
    ----------
    one_seed_to_rule_them_all : int, optional
        Master seed used to initialise the NumPy RNG.  Default ``42``.
    size : int, optional
        Number of seeds to generate.  Default ``20``.

    Returns
    -------
    numpy.ndarray
        1-D integer array of *size* seeds drawn uniformly from
        ``[1 000, 10^10)``.
    """
    rng = np.random.default_rng(seed=one_seed_to_rule_them_all)
    return rng.integers(low=1000, high=10 ** 10, size=size)


class Distribution(ABC):
    """
    Abstract base class for all distribution wrappers.

    Every concrete subclass encapsulates a NumPy RNG and exposes a single
    :meth:`sample` method so that simulation code is decoupled from the
    underlying random-variate generator.
    """

    @abstractmethod
    def sample(self, size: Optional[int] = None) -> Any:
        """
        Draw one or more random variates.

        Parameters
        ----------
        size : int, optional
            Number of samples to return.  ``None`` returns a scalar.

        Returns
        -------
        Any
            A scalar or array of sampled values.
        """
        raise NotImplementedError()


class Bernoulli(Distribution):
    """
    Bernoulli distribution wrapper.

    Parameters
    ----------
    p : float
        Probability of success (returning ``1``).
    random_seed : int, optional
        Seed for the NumPy RNG.  ``None`` produces non-reproducible samples.
    """

    def __init__(self, p: float, random_seed: Optional[int] = None) -> None:
        self.rand = np.random.default_rng(seed=random_seed)
        self.p = p

    def sample(self, size: Optional[int] = None) -> np.ndarray:
        """
        Draw Bernoulli variates.

        Parameters
        ----------
        size : int, optional
            Number of draws. When ``None``, return a scalar.

        Returns
        -------
        scalar or numpy.ndarray
            Sampled value(s).
        """
        return self.rand.binomial(n=1, p=self.p, size=size)


class Uniform(Distribution):
    """
    Uniform distribution wrapper.

    Parameters
    ----------
    low : float
        Lower bound of the distribution.
    high : float
        Upper bound of the distribution.
    random_seed : int, optional
        Seed for the NumPy RNG.
    """

    def __init__(self, low: float, high: float, random_seed: Optional[int] = None) -> None:
        self.rand = np.random.default_rng(seed=random_seed)
        self.low = low
        self.high = high

    def sample(self, size: Optional[int] = None) -> np.ndarray:
        """
        Draw uniform variates.

        Parameters
        ----------
        size : int, optional
            Number of draws. When ``None``, return a scalar.

        Returns
        -------
        scalar or numpy.ndarray
            Sampled value(s).
        """
        return self.rand.uniform(low=self.low, high=self.high, size=size)


class Exponential(Distribution):
    """
    Exponential distribution wrapper.

    Commonly used to model inter-arrival times in DES models with a
    Poisson arrival process.

    Parameters
    ----------
    mean : float
        Mean of the exponential distribution (scale parameter).
    random_seed : int, optional
        Seed for the NumPy RNG.
    """

    def __init__(self, mean: float, random_seed: Optional[int] = None) -> None:
        self.rand = np.random.default_rng(seed=random_seed)
        self.mean = mean

    def sample(self, size: Optional[int] = None) -> np.ndarray:
        """
        Draw exponential variates.

        Parameters
        ----------
        size : int, optional
            Number of draws. When ``None``, return a scalar.

        Returns
        -------
        scalar or numpy.ndarray
            Sampled value(s).
        """
        return self.rand.exponential(self.mean, size=size)


class Poisson(Distribution):
    """
    Poisson distribution wrapper.

    Parameters
    ----------
    mean : float
        Mean (lambda) of the Poisson distribution.
    random_seed : int, optional
        Seed for the NumPy RNG.
    """

    def __init__(self, mean: float, random_seed: Optional[int] = None) -> None:
        self.rand = np.random.default_rng(seed=random_seed)
        self.mean = mean

    def sample(self, size: Optional[int] = None) -> np.ndarray:
        """
        Draw Poisson variates.

        Parameters
        ----------
        size : int, optional
            Number of draws. When ``None``, return a scalar.

        Returns
        -------
        scalar or numpy.ndarray
            Sampled value(s).
        """
        return self.rand.poisson(self.mean, size=size)


class Triangular(Distribution):
    """
    Triangular distribution wrapper.

    Parameters
    ----------
    low : float
        Minimum value of the distribution.
    mode : float
        Most likely (modal) value.
    high : float
        Maximum value of the distribution.
    random_seed : int, optional
        Seed for the NumPy RNG.
    """

    def __init__(self, low: float, mode: float, high: float, random_seed: Optional[int] = None) -> None:
        self.rand = np.random.default_rng(seed=random_seed)
        self.low = low
        self.high = high
        self.mode = mode

    def sample(self, size: Optional[int] = None) -> np.ndarray:
        """
        Draw triangular variates.

        Parameters
        ----------
        size : int, optional
            Number of draws. When ``None``, return a scalar.

        Returns
        -------
        scalar or numpy.ndarray
            Sampled value(s).
        """
        return self.rand.triangular(self.low, self.mode, self.high, size=size)


class Discrete(Distribution):
    """
    Discrete distribution over a finite set of elements.

    Parameters
    ----------
    elements : list[Any]
        Ordered list of possible outcome values.
    probabilities : list[float]
        Probability mass for each element.  Must sum to 1.
    random_seed : int, optional
        Seed for the NumPy RNG.

    Raises
    ------
    ValueError
        If *elements* and *probabilities* differ in length, or if
        *probabilities* do not sum to 1.
    """

    def __init__(self, elements: List[Any], probabilities: List[float], random_seed: Optional[int] = None) -> None:
        self.elements = elements
        self.probabilities = probabilities
        self.validate_lengths(elements, probabilities)
        self.validate_probs(probabilities)
        self.cum_probs = np.add.accumulate(probabilities)
        self.rng = np.random.default_rng(random_seed)

    def validate_lengths(self, elements: List[Any], probs: List[float]) -> None:
        """
        Raise ``ValueError`` when *elements* and *probs* have different lengths.

        Parameters
        ----------
        elements : list[Any]
            Candidate elements list.
        probs : list[float]
            Candidate probabilities list.

        Raises
        ------
        ValueError
            When ``len(elements) != len(probs)``.
        """
        if len(elements) != len(probs):
            raise ValueError("Elements and probabilities arguments must be of the same length")

    def validate_probs(self, probs: List[float]) -> None:
        """
        Raise ``ValueError`` when *probs* do not sum to 1.

        Parameters
        ----------
        probs : list[float]
            Probability values to validate.

        Raises
        ------
        ValueError
            When ``sum(probs)`` is not close to 1.0.
        """
        if not math.isclose(sum(probs), 1.0):
            raise ValueError("Probabilities must sum to 1")

    def sample(self, size: Optional[int] = None) -> Any:
        """
        Draw variates from the discrete mass function.

        Parameters
        ----------
        size : int, optional
            Number of draws. When ``None``, return a scalar.

        Returns
        -------
        scalar or numpy.ndarray
            Sampled value(s).
        """
        return self.elements[np.digitize(self.rng.random(size), self.cum_probs)]


class LogNormal(Distribution):
    """
    Log-normal distribution wrapper.

    Commonly used for service and assessment times in healthcare DES models
    where durations are right-skewed and strictly positive.

    Parameters
    ----------
    mean : float
        Mean of the underlying normal distribution (log-space).
    sigma : float
        Standard deviation of the underlying normal distribution (log-space).
    random_seed : int, optional
        Seed for the NumPy RNG.
    """

    def __init__(self, mean: float, sigma: float, random_seed: Optional[int] = None) -> None:
        self.rand = np.random.default_rng(seed=random_seed)
        self.mean = mean
        self.sigma = sigma

    def sample(self, size: Optional[int] = None) -> np.ndarray:
        """
        Draw log-normal variates.

        Parameters
        ----------
        size : int, optional
            Number of draws. When ``None``, return a scalar.

        Returns
        -------
        scalar or numpy.ndarray
            Sampled value(s).
        """
        return self.rand.lognormal(mean=self.mean, sigma=self.sigma, size=size)


class Normal(Distribution):
    """
    Normal (Gaussian) distribution wrapper.

    Parameters
    ----------
    mean : float
        Mean of the normal distribution.
    std : float
        Standard deviation of the normal distribution.
    random_seed : int, optional
        Seed for the NumPy RNG.
    """

    def __init__(self, mean: float, std: float, random_seed: Optional[int] = None) -> None:
        self.rand = np.random.default_rng(seed=random_seed)
        self.mean = mean
        self.std = std

    def sample(self, size: Optional[int] = None) -> np.ndarray:
        """
        Draw normal variates.

        Parameters
        ----------
        size : int, optional
            Number of draws. When ``None``, return a scalar.

        Returns
        -------
        scalar or numpy.ndarray
            Sampled value(s).
        """
        return self.rand.normal(loc=self.mean, scale=self.std, size=size)


class Choice(Distribution):
    """
    Weighted random sampler over a finite collection of choices.

    Parameters
    ----------
    choices : list[Any]
        Ordered list of possible values to sample from.
    probabilities : list[float]
        Probability weight for each choice.  Must sum to 1 within 1e-6.
    random_seed : int, optional
        Seed for the NumPy RNG.

    Raises
    ------
    ValueError
        When *probabilities* do not sum to 1 (tolerance 1e-6).
    """

    def __init__(self, choices: List[Any], probabilities: List[float], random_seed: Optional[int] = None) -> None:
        if abs(sum(probabilities) - 1.0) > 1e-6:
            raise ValueError("Probabilities must sum to 1.")
        self.rand = np.random.default_rng(seed=random_seed)
        self.choices = list(choices)
        self.probabilities = list(probabilities)

    def sample(self, size: Optional[int] = None) -> Any:
        """
        Draw weighted random choices.

        Parameters
        ----------
        size : int, optional
            Number of draws. When ``None``, return a scalar.

        Returns
        -------
        scalar or numpy.ndarray
            Sampled value(s).
        """
        return self.rand.choice(self.choices, size=size, p=self.probabilities)
