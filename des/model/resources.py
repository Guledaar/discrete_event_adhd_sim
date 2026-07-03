"""Workforce-hours capacity resource."""

import warnings
from collections import deque

from des.model.utils import trace

class WorkforceHoursAccountingError(Exception):
    """Released, used, and unused hours do not balance."""


class WorkforceHoursQueueConservationError(Exception):
    """Enqueue/grant/queue counts do not balance."""


class WorkforceHoursResource:
    """Weekday hour budget; priority + standard queues, best-fit grant, strict end validation."""

    uses_workforce_hours = True
    _TOL = 1e-9

    def __init__(
        self,
        env,
        workforce_hours_per_day,
        name="resource",
        collection_start=0.0,
        collection_end=float("inf"),
        derived_slots_per_day=0,
        on_validation_error=None,
    ):
        self.env = env
        self.name = name
        self.workforce_hours_per_day = float(workforce_hours_per_day)
        self.derived_slots_per_day = int(derived_slots_per_day)
        self.collection_start = float(collection_start)
        self.collection_end = float(collection_end)
        self._warn = on_validation_error or (
            lambda m: warnings.warn(m, UserWarning, stacklevel=3)
        )
        self.priority_queue = deque()
        self.standard_queue = deque()
        self.released = self.used = self.unused = 0.0
        self.coll_released = self.coll_used = self.coll_unused = 0.0
        self.hours_left = 0.0
        self.max_queue_length = self.priority_served = self.standard_served = 0
        self.enqueue_count = self.grant_count = 0
        self.in_service_count = self.service_complete_count = 0
        self._pool_in_coll = False
        env.process(self._day_loop())

    @staticmethod
    def _hrs(days):
        return float(days) * 24.0

    def _in_coll(self):
        return self.collection_start <= self.env.now < self.collection_end

    def _track(self, total, coll, hrs, in_coll=None):
        setattr(self, total, getattr(self, total) + hrs)
        if in_coll if in_coll is not None else self._in_coll():
            setattr(self, coll, getattr(self, coll) + hrs)

    def request(self, priority=False, service_duration_days=None):
        if service_duration_days is None:
            raise ValueError(f"{self.name}: service_duration_days required")
        evt = self.env.event()
        (self.priority_queue if priority else self.standard_queue).append(
            (evt, float(service_duration_days))
        )
        self.enqueue_count += 1
        self.max_queue_length = max(self.max_queue_length, self.count_queue())
        self._allocate()
        return evt

    def notify_service_complete(self):
        self.in_service_count = max(0, self.in_service_count - 1)
        self.service_complete_count += 1

    @staticmethod
    def _dequeue_at(q, i):
        q.rotate(-i)
        item = q.popleft()
        q.rotate(i)
        return item

    def _pop_fit(self, hours_left, queue, served_attr):
        if not queue:
            return None
        fits = [
            (i, self._hrs(d))
            for i, (_, d) in enumerate(queue)
            if self._hrs(d) <= hours_left + self._TOL
        ]
        if not fits:
            return None
        idx, need = fits[0] if fits[0][0] == 0 else max(fits, key=lambda x: x[1])
        evt, _ = queue.popleft() if idx == 0 else self._dequeue_at(queue, idx)
        setattr(self, served_attr, getattr(self, served_attr) + 1)
        return evt, need

    def _allocate(self):
        while self.hours_left > self._TOL:
            job = (
                self._pop_fit(self.hours_left, self.priority_queue, "priority_served")
                or self._pop_fit(self.hours_left, self.standard_queue, "standard_served")
            )
            if not job:
                break
            evt, need = job
            self.hours_left -= need
            if not evt.triggered:
                evt.succeed()
                self.grant_count += 1
                self.in_service_count += 1
                self._track("used", "coll_used", need)

    def _day_loop(self):
        while True:
            hours = self.workforce_hours_per_day if int(self.env.now) % 7 < 5 else 0.0
            in_coll = self._in_coll()
            self._track("released", "coll_released", hours, in_coll)
            self.hours_left = hours
            self._pool_in_coll = in_coll
            self._allocate()
            yield self.env.timeout(1.0)
            self._track("unused", "coll_unused", self.hours_left, self._pool_in_coll)
            self.hours_left = 0.0
            self._validate_accounting(strict=False)

    def count_queue(self):
        return len(self.priority_queue) + len(self.standard_queue)

    @property
    def utilisation(self):
        return min(self.coll_used / self.coll_released, 1.0) if self.coll_released else 0.0

    @property
    def full_run_utilisation(self):
        return min(self.used / self.released, 1.0) if self.released else 0.0

    def _validate_accounting(self, strict=False):
        tol, issues = 1e-6, []
        if abs(self.released - self.used - self.unused) > tol:
            issues.append(f"{self.name}: released != used+unused")
        if abs(self.coll_released - self.coll_used - self.coll_unused) > tol:
            issues.append(f"{self.name}: collection imbalance")
        if self.used > self.released + tol:
            issues.append(f"{self.name}: used exceeds released")
        u = self.full_run_utilisation
        if u < -tol or u > 1.0 + tol:
            issues.append(f"{self.name}: utilisation {u:.6f} outside [0,1]")
        for msg in issues:
            if strict:
                raise WorkforceHoursAccountingError(msg)
            self._warn(msg)

    def validate_queue_conservation(self, strict=False):
        waiting = self.count_queue()
        accounted = self.grant_count + waiting
        payload = {
            "enqueue_count": self.enqueue_count,
            "grant_count": self.grant_count,
            "waiting_count": waiting,
            "in_service_count": self.in_service_count,
            "service_complete_count": self.service_complete_count,
            "accounted_for": accounted,
            "balanced": self.enqueue_count == accounted,
        }
        if not payload["balanced"]:
            msg = f"{self.name}: enqueue={self.enqueue_count}, grant+waiting={accounted}"
            if strict:
                raise WorkforceHoursQueueConservationError(msg)
            self._warn(msg)
        return payload

    def get_summary(self):
        q = self.count_queue()
        return {
            "resource_name": self.name,
            "queue_length": q,
            "queue_backlog": q,
            "max_queue_length": self.max_queue_length,
            "released_slots": self.released,
            "used_slots": self.used,
            "unused_slots": self.unused,
            "collection_released_slots": self.coll_released,
            "collection_used_slots": self.coll_used,
            "collection_unused_slots": self.coll_unused,
            "utilisation_pct": round(self.utilisation * 100, 2),
            "full_run_utilisation_pct": round(self.full_run_utilisation * 100, 2),
            "workforce_hours_per_day": self.workforce_hours_per_day,
            "derived_slots_per_day": self.derived_slots_per_day,
            "priority_served": self.priority_served,
            "standard_served": self.standard_served,
            "enqueue_count": self.enqueue_count,
            "grant_count": self.grant_count,
            "in_service_count": self.in_service_count,
            "capacity_model": "workforce_hours",
        }

    def flush_end_of_horizon(self):
        if self.hours_left > self._TOL:
            self._track("unused", "coll_unused", self.hours_left, self._pool_in_coll)
            self.hours_left = 0.0

    def final_validate(self, strict=True):
        self.flush_end_of_horizon()
        self._validate_accounting(strict=strict)
        state = self.validate_queue_conservation(strict=strict)
        return {
            "accounting_ok": abs(self.released - self.used - self.unused) < 1e-6,
            "utilisation": self.full_run_utilisation,
            **state,
        }
