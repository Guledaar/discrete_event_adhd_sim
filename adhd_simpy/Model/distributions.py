"""
Module: distributions

Provides some distribution objects the encapsulate a 
numpy random number generator

"""
import numpy as np
from abc import ABC, abstractmethod
import math

def generate_seed_vector(one_seed_to_rule_them_all=42, size=20):
    '''
    Return a controllable numpy array
    of integer seeds to use in simulation model.
    
    Values are between 1000 and 10^10
    
    Params:
    ------
    one_seed_to_rule_them_all: int, optional (default=42)
        seed to produce the seed vector
        
    size: int, optional (default=20)
        length of seed vector
    '''
    rng = np.random.default_rng(seed=one_seed_to_rule_them_all)
    return rng.integers(low=1000, high=10**10, size=size)


class Distribution(ABC):
    '''
    Distribution interface
    '''
    @abstractmethod
    def sample(self, size=None):
        pass
        

class Bernoulli(Distribution):
    '''
    Convenience class for the Bernoulli distribution.
    packages up distribution parameters, seed and random generator.
    '''
    def __init__(self, p, random_seed=None):
        '''
        Constructor
        
        Params:
        ------
        p: float
            probability of drawing a 1
        
        random_seed: int, optional (default=None)
            A random seed to reproduce samples.  If set to none then a unique
            sample is created.
        '''
        self.rand = np.random.default_rng(seed=random_seed)
        self.p = p
        
    def sample(self, size=None):
        '''
        Generate a sample from the exponential distribution
        
        Params:
        -------
        size: int, optional (default=None)
            the number of samples to return.  If size=None then a single
            sample is returned.
        '''
        return self.rand.binomial(n=1, p=self.p, size=size)
    

class Uniform(Distribution):
    '''
    Convenience class for the Bernoulli distribution.
    packages up distribution parameters, seed and random generator.
    '''
    def __init__(self, low, high, random_seed=None):
        '''
        Constructor
        
        Params:
        ------
        low: float
            lower range of the uniform
            
        high: float
            upper range of the uniform
        
        random_seed: int, optional (default=None)
            A random seed to reproduce samples.  If set to none then a unique
            sample is created.
        '''
        self.rand = np.random.default_rng(seed=random_seed)
        self.low = low
        self.high = high
        
    def sample(self, size=None):
        '''
        Generate a sample from the exponential distribution
        
        Params:
        -------
        size: int, optional (default=None)
            the number of samples to return.  If size=None then a single
            sample is returned.
        '''
        return self.rand.uniform(low=self.low, high=self.high, size=size)
    
    
class Exponential(Distribution):
    '''
    Convenience class for the exponential distribution.
    packages up distribution parameters, seed and random generator.
    '''
    def __init__(self, mean, random_seed=None):
        '''
        Constructor
        
        Params:
        ------
        mean: float
            The mean of the exponential distribution
        
        random_seed: int, optional (default=None)
            A random seed to reproduce samples.  If set to none then a unique
            sample is created.
        '''
        self.rand = np.random.default_rng(seed=random_seed)
        self.mean = mean
        
    def sample(self, size=None):
        '''
        Generate a sample from the exponential distribution
        
        Params:
        -------
        size: int, optional (default=None)
            the number of samples to return.  If size=None then a single
            sample is returned.
        '''
        return self.rand.exponential(self.mean, size=size)
    

class Poisson(Distribution):
    '''
    Convenience class for the poisson distribution.
    packages up distribution parameters, seed and random generator.
    '''
    def __init__(self, mean, random_seed=None):
        '''
        Constructor
        
        Params:
        ------
        mean: float
            The mean of the poisson distribution
        
        random_seed: int, optional (default=None)
            A random seed to reproduce samples.  If set to none then a unique
            sample is created.
        '''
        self.rand = np.random.default_rng(seed=random_seed)
        self.mean = mean
        
    def sample(self, size=None):
        '''
        Generate a sample from the poisson distribution
        
        Params:
        -------
        size: int, optional (default=None)
            the number of samples to return.  If size=None then a single
            sample is returned.
        '''
        return self.rand.poisson(self.mean, size=size)
    

class Triangular(Distribution):
    '''
    Convenience class for the triangular distribution.
    packages up distribution parameters, seed and random generator.
    '''
    def __init__(self, low, mode, high, random_seed=None):
        self.rand = np.random.default_rng(seed=random_seed)
        self.low = low
        self.high = high
        self.mode = mode
        
    def sample(self, size=None):
        return self.rand.triangular(self.low, self.mode, self.high, size=size)
    
    
class Discrete(Distribution):
    """
    Encapsulates a discrete distribution
    """
    def __init__(self, elements, probabilities, random_seed=None):
        self.elements = elements
        self.probabilities = probabilities
        
        self.validate_lengths(elements, probabilities)
        self.validate_probs(probabilities)
        
        self.cum_probs = np.add.accumulate(probabilities)
        
        self.rng = np.random.default_rng(random_seed)
        
        
    def validate_lengths(self, elements, probs):
        if (len(elements) != len(probs)):
            raise ValueError('Elements and probilities arguments must be of the same length')
            
    def validate_probs(self, probs):
        if not math.isclose(sum(probs), 1.0):
            raise ValueError('Probabilities must sum to 1')
        
    def sample(self, size=None):
        return self.elements[np.digitize(self.rng.random(size), self.cum_probs)]


class LogNormal(Distribution):
    '''
    Convenience class for the log-normal distribution.

    Commonly used for service/assessment times in healthcare DES models
    where durations are right-skewed and strictly positive (e.g. ADHD
    full diagnostic assessment duration).

    Params are specified as the *mean* and *standard deviation* of the
    underlying normal (log-space) distribution.
    '''
    def __init__(self, mean, sigma, random_seed=None):
        '''
        Constructor

        Params:
        ------
        mean: float
            Mean of the underlying normal distribution (log-space).

        sigma: float
            Standard deviation of the underlying normal distribution (log-space).

        random_seed: int, optional (default=None)
            A random seed to reproduce samples.
        '''
        self.rand = np.random.default_rng(seed=random_seed)
        self.mean = mean
        self.sigma = sigma

    def sample(self, size=None):
        return self.rand.lognormal(mean=self.mean, sigma=self.sigma, size=size)


class Normal(Distribution):
    '''
    Convenience class for the normal (Gaussian) distribution.

    Useful for symmetric continuous outcomes such as age at referral or
    standardised rating-scale scores in an ADHD pathway model.
    Samples below zero are possible; consider LogNormal for durations.
    '''
    def __init__(self, mean, std, random_seed=None):
        '''
        Constructor

        Params:
        ------
        mean: float
            Mean of the normal distribution.

        std: float
            Standard deviation of the normal distribution.

        random_seed: int, optional (default=None)
            A random seed to reproduce samples.
        '''
        self.rand = np.random.default_rng(seed=random_seed)
        self.mean = mean
        self.std = std

    def sample(self, size=None):
        return self.rand.normal(loc=self.mean, scale=self.std, size=size)


class Gamma(Distribution):
    '''
    Convenience class for the gamma distribution.

    A flexible, strictly-positive distribution commonly used in healthcare
    DES for service times (e.g. medication titration duration, wait for
    follow-up appointment).  When shape=1 it reduces to the exponential.

    Parameterised by *shape* (k) and *scale* (θ); mean = k * θ.
    '''
    def __init__(self, shape, scale, random_seed=None):
        '''
        Constructor

        Params:
        ------
        shape: float
            Shape parameter (k > 0).

        scale: float
            Scale parameter (θ > 0).

        random_seed: int, optional (default=None)
            A random seed to reproduce samples.
        '''
        self.rand = np.random.default_rng(seed=random_seed)
        self.shape = shape
        self.scale = scale

    def sample(self, size=None):
        return self.rand.gamma(shape=self.shape, scale=self.scale, size=size)


class Erlang(Distribution):
    '''
    Convenience class for the Erlang distribution (Gamma with integer shape).

    Used in queueing theory to model the sum of k i.i.d. exponential stages,
    e.g. a multi-step ADHD assessment that has k sequential phases each with
    mean duration 1/μ days.

    Parameterised by *shape* k (positive integer) and *scale* θ; mean = k * θ.
    '''
    def __init__(self, shape, scale, random_seed=None):
        '''
        Constructor

        Params:
        ------
        shape: int
            Number of exponential phases (k ≥ 1).

        scale: float
            Scale (mean of each exponential phase, θ > 0).

        random_seed: int, optional (default=None)
            A random seed to reproduce samples.
        '''
        if not isinstance(shape, int) or shape < 1:
            raise ValueError('Erlang shape must be a positive integer.')
        self.rand = np.random.default_rng(seed=random_seed)
        self.shape = shape
        self.scale = scale

    def sample(self, size=None):
        return self.rand.gamma(shape=self.shape, scale=self.scale, size=size)


class Weibull(Distribution):
    '''
    Convenience class for the Weibull distribution.

    Suitable for modelling time-to-event outcomes in the ADHD pathway such
    as time-to-dropout, time-to-medication-review, or patient survival in
    the system.  Shape < 1 → decreasing hazard; shape > 1 → increasing.

    Parameterised by *shape* (a) and *scale* (λ); mean = λ * Γ(1 + 1/a).
    '''
    def __init__(self, shape, scale, random_seed=None):
        '''
        Constructor

        Params:
        ------
        shape: float
            Shape parameter (a > 0).  Controls hazard behaviour.

        scale: float
            Scale parameter (λ > 0).

        random_seed: int, optional (default=None)
            A random seed to reproduce samples.
        '''
        self.rand = np.random.default_rng(seed=random_seed)
        self.shape = shape
        self.scale = scale

    def sample(self, size=None):
        return self.scale * self.rand.weibull(self.shape, size=size)


class Beta(Distribution):
    '''
    Convenience class for the Beta distribution.

    Bounded on [0, 1]; ideal for modelling probabilities or proportions
    that vary across patients in an ADHD pathway, e.g. probability of
    accepting a referral, medication adherence rate, or comorbidity prevalence.
    '''
    def __init__(self, alpha, beta, random_seed=None):
        '''
        Constructor

        Params:
        ------
        alpha: float
            Shape parameter α > 0.

        beta: float
            Shape parameter β > 0.

        random_seed: int, optional (default=None)
            A random seed to reproduce samples.
        '''
        self.rand = np.random.default_rng(seed=random_seed)
        self.alpha = alpha
        self.beta = beta

    def sample(self, size=None):
        return self.rand.beta(self.alpha, self.beta, size=size)


class NegativeBinomial(Distribution):
    '''
    Convenience class for the negative binomial distribution.

    Models over-dispersed count data — a better fit than Poisson when the
    variance exceeds the mean.  Useful for the number of ADHD referrals per
    week/month when referral counts are bursty (e.g. school-term spikes).

    Parameterised by *n* (number of successes) and *p* (success probability);
    mean = n*(1-p)/p.
    '''
    def __init__(self, n, p, random_seed=None):
        '''
        Constructor

        Params:
        ------
        n: int
            Number of successes (target).

        p: float
            Probability of success on each trial (0 < p ≤ 1).

        random_seed: int, optional (default=None)
            A random seed to reproduce samples.
        '''
        self.rand = np.random.default_rng(seed=random_seed)
        self.n = n
        self.p = p

    def sample(self, size=None):
        return self.rand.negative_binomial(self.n, self.p, size=size)

