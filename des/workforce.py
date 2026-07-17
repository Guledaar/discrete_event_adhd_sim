"""Shared weekday clinician-hour scheduler with priority queues."""

from __future__ import annotations

import itertools
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Generator, List, Optional

import simpy

from des.audit import Audit


@dataclass
class _HourRequest:
    """
    Pending clinician-hour request sitting in a priority queue.

    Attributes
    ----------
    hours : float
        Number of clinician hours requested.
    priority : int
        Scheduling priority (lower value = higher priority).
    event : simpy.Event
        SimPy event that is triggered when the request is granted.
    arrival_order : int
        Monotonically increasing counter used as a tie-breaker within
        the same priority level.
    """

    hours: float
    priority: int
    event: simpy.Event
    arrival_order: int


class WorkforceHoursResource:
    """
    Shared weekday clinician-hour scheduler with priority queues.

    Each simulated weekday a fixed number of clinician hours is released.
    Pending requests are served in priority order (workshops first, then
    returning assessment patients, then new assessment patients).  Unused
    hours expire at end-of-day and are recorded in the audit.

    Priority constants
    ------------------
    PRIORITY_WORKSHOP : int
        Highest priority (0) — workshop sessions.
    PRIORITY_RETURNING : int
        Middle priority (1) — follow-up assessment appointments.
    PRIORITY_NEW : int
        Lowest priority (2) — first assessment appointments.

    Parameters
    ----------
    env : simpy.Environment
        Owning SimPy environment.
    experiment : Experiment
        Scenario configuration supplying ``workforce_hours_per_day``.
    audit : Audit
        Patient-state recorder that receives per-day capacity records.
    name : str, optional
        Label used for identification.  Default ``'workforce'``.
    """

    PRIORITY_WORKSHOP = 0
    PRIORITY_RETURNING = 1
    PRIORITY_NEW = 2
    NUM_PRIORITY_LEVELS = 3

    def __init__(
        self,
        env: simpy.Environment,
        experiment: Any,
        audit: Audit,
        name: str = "workforce",
    ) -> None:
        """
        Initialise queues, counters, and start the weekday scheduler process.

        Parameters
        ----------
        env : simpy.Environment
            SimPy environment.
        experiment : Experiment
            Scenario configuration providing ``workforce_hours_per_day``.
        audit : Audit
            Audit object that receives per-day capacity balance records.
        name : str, optional
            Resource name for logging.  Default ``'workforce'``.
        """
        self.env = env
        self.experiment = experiment
        self.name = name
        self.audit = audit
        self.workforce_hours_per_day = float(experiment.workforce_hours_per_day)

        self.available_hours = 0.0
        self._request_seq = itertools.count()
        self._queues: List[Deque[_HourRequest]] = [
            deque() for _ in range(self.NUM_PRIORITY_LEVELS)
        ]
        self._day_released = 0.0
        self._day_used = 0.0
        self._day_assessment_used = 0.0
        self._day_workshop_used = 0.0

        self.env.process(self._weekday_scheduler())

    def refresh_capacity_from_experiment(self) -> None:
        """
        Re-read ``workforce_hours_per_day`` from the experiment without interrupting service.

        Called by the intervention hook in Run 3 when policy overrides are
        applied mid-simulation so that the new capacity takes effect from the
        next weekday release.
        """
        self.workforce_hours_per_day = float(self.experiment.workforce_hours_per_day)

    @property
    def waiting_count(self) -> int:
        """
        Total number of requests currently waiting across all priority queues.

        Returns
        -------
        int
            Sum of queue lengths for all priority levels.
        """
        return sum(len(queue) for queue in self._queues)

    def queue_position_for(self, priority: int) -> int:
        """
        Estimate the waiting position for a new request at *priority*.

        Counts all requests in queues at *priority* and above (i.e. those
        that would be served before a new arrival at *priority*).

        Parameters
        ----------
        priority : int
            Priority level of the hypothetical new request.

        Returns
        -------
        int
            Number of requests ahead of a new request at *priority*.
        """
        return sum(len(queue) for queue in self._queues[: priority + 1])

    def request_hours(
        self,
        hours: float,
        priority: int,
    ) -> Generator[simpy.Event, None, None]:
        """
        Request *hours* of clinician time at the given *priority*.

        This is a SimPy generator: the calling process yields from it and
        resumes only when the request has been granted (i.e. the hours are
        available and the request reaches the head of its priority queue).

        Parameters
        ----------
        hours : float
            Number of clinician hours required.
        priority : int
            Scheduling priority (use the class-level ``PRIORITY_*`` constants).

        Yields
        ------
        simpy.Event
            The internal event that is triggered when hours are granted.
        """
        request = _HourRequest(
            hours=float(hours),
            priority=priority,
            event=self.env.event(),
            arrival_order=next(self._request_seq),
        )
        self._enqueue(request)
        yield request.event

    def _enqueue(self, request: _HourRequest) -> None:
        """
        Add *request* to its priority queue and immediately attempt to grant it.

        Parameters
        ----------
        request : _HourRequest
            The pending request to enqueue.
        """
        self._queues[request.priority].append(request)
        self._try_grant()

    def _next_waiting_request(self) -> Optional[_HourRequest]:
        """
        Peek at the highest-priority waiting request without removing it.

        Returns
        -------
        _HourRequest or None
            The head of the non-empty queue with the lowest priority index,
            or ``None`` if all queues are empty.
        """
        for priority in range(self.NUM_PRIORITY_LEVELS):
            if self._queues[priority]:
                return self._queues[priority][0]
        return None

    def _pop_highest_priority(self) -> Optional[_HourRequest]:
        """
        Remove and return the highest-priority waiting request.

        Returns
        -------
        _HourRequest or None
            The removed request, or ``None`` if all queues are empty.
        """
        for priority in range(self.NUM_PRIORITY_LEVELS):
            if self._queues[priority]:
                return self._queues[priority].popleft()
        return None

    def _try_grant(self) -> None:
        """
        Grant as many queued requests as the current available-hour balance permits.

        Iterates from the highest-priority queue downward, granting each
        head-of-queue request whose ``hours`` fit within ``available_hours``.
        Stops as soon as the next request cannot be fully satisfied.
        """
        while self.available_hours > 0:
            request = self._next_waiting_request()
            if request is None or request.hours > self.available_hours:
                break
            self._pop_highest_priority()
            self.available_hours -= request.hours
            self._day_used += request.hours
            if request.priority == self.PRIORITY_WORKSHOP:
                self._day_workshop_used += request.hours
            else:
                self._day_assessment_used += request.hours
            if not request.event.triggered:
                request.event.succeed()

    def _expire_day(self) -> None:
        """
        Close out the current weekday: record the capacity balance and reset counters.

        Unused hours are written to the audit and then zeroed; they are not
        carried forward to the next day.
        """
        day_unused = self.available_hours
        if self._day_released > 0:
            self.audit.record_capacity_day(
                self.env.now,
                hours_released=self._day_released,
                hours_used=self._day_used,
                hours_unused=day_unused,
                assessment_hours_used=self._day_assessment_used,
                workshop_hours_used=self._day_workshop_used,
            )
        self.available_hours = 0.0
        self._day_released = 0.0
        self._day_used = 0.0
        self._day_assessment_used = 0.0
        self._day_workshop_used = 0.0

    def _release_day(self) -> None:
        """
        Open a new weekday by re-reading capacity and granting waiting requests.

        Re-reads ``workforce_hours_per_day`` from the experiment (so that
        mid-simulation intervention overrides are respected) and immediately
        attempts to serve any pending requests.
        """
        self.workforce_hours_per_day = float(self.experiment.workforce_hours_per_day)
        self.available_hours = self.workforce_hours_per_day
        self._day_released = self.workforce_hours_per_day
        self._try_grant()

    def _weekday_scheduler(self) -> Generator[simpy.Timeout, None, None]:
        """
        SimPy generator that drives the daily release-expire cycle.

        On each iteration the scheduler skips weekend days, expires the
        previous day's unused hours, releases a fresh allocation, waits
        one simulation day (= 1.0 time unit), then expires again.

        Yields
        ------
        simpy.Timeout
            One-day (or weekend-skip) timeout events.
        """
        while True:
            current_week_time = self.env.now % 7
            if current_week_time >= 5.0:
                yield self.env.timeout(7.0 - current_week_time)
                continue
            self._expire_day()
            self._release_day()
            yield self.env.timeout(1.0)
            self._expire_day()
