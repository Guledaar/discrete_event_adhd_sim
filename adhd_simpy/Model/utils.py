"""Trace and capacity reporting helpers."""

from adhd_simpy.Model import parameters


def trace(msg: str) -> None:
    """Print a debug message when global ``parameters.TRACE`` is True."""
    if parameters.TRACE:
        print(msg)



def triangular_mean_hours(duration_triplet):
    """
    Mean of a triangular duration specification in hours.

    Parameters
    ----------
    duration_triplet : sequence of float
        ``[min, mode, max]`` duration in hours.

    Returns
    -------
    float
        Arithmetic mean of the three values.
    """
    return sum(duration_triplet) / 3.0


def derive_daily_slots(workforce_hours, duration_triplet):
    """
    Reporting-only upper bound on weekday appointment starts.

    Parameters
    ----------
    workforce_hours : float
        Clinician hours available per weekday.
    duration_triplet : sequence of float
        ``[min, mode, max]`` appointment duration in hours.

    Returns
    -------
    int
        ``max(1, workforce_hours // mean_duration)``; not used by the scheduler.

    Notes
    -----
    Simulation capacity is enforced by :class:`WorkforceHoursResource`, not this value.
    """
    mean_hours = triangular_mean_hours(duration_triplet)
    if mean_hours <= 0:
        return 0
    return max(1, int(workforce_hours / mean_hours))
