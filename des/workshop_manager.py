"""Forms workshop groups from the clinical-support waiting list."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Deque, Generator, Tuple

import simpy

from des.trace import trace_workshop_started, trace_workshop_waiting
from des.workshop_group import WorkshopGroup

if TYPE_CHECKING:
    from des.patient import Patient
    from des.system import AutismPathwaySystem


class WorkshopManager:
    """
    Form workshop groups from the clinical-support waiting list.

    Patients who require clinical post-diagnosis support call :meth:`join`
    to join the waiting list.  The manager checks after every joining event
    and every simulated day whether enough patients are waiting (or the
    oldest has waited long enough) to form a new group.

    Parameters
    ----------
    env : simpy.Environment
        Owning SimPy environment.
    system : AutismPathwaySystem
        Parent system providing experiment configuration and the audit.

    Attributes
    ----------
    waiting_list : deque[tuple[float, Patient]]
        Queue of ``(join_time, patient)`` pairs in arrival order.
    active_patient_ids : set[int]
        IDs of patients currently inside an active workshop group.
    """

    def __init__(self, env: simpy.Environment, system: AutismPathwaySystem) -> None:
        """
        Initialise the waiting list and start the daily monitoring process.

        Parameters
        ----------
        env : simpy.Environment
            SimPy environment.
        system : AutismPathwaySystem
            Parent simulation system.
        """
        self.env = env
        self.system = system
        self.audit = system.experiment.audit
        self.waiting_list: Deque[Tuple[float, Patient]] = deque()
        self.active_patient_ids: set[int] = set()
        self.env.process(self._monitor())

    @property
    def waiting_count(self) -> int:
        """
        Number of patients currently waiting to form a workshop group.

        Returns
        -------
        int
            Length of the workshop waiting list.
        """
        return len(self.waiting_list)

    def join(self, patient: Patient) -> None:
        """
        Add *patient* to the clinical-support waiting list.

        Records the join time in the audit, logs a trace event, then
        immediately attempts to form a new group.

        Parameters
        ----------
        patient : Patient
            The patient joining the workshop waiting list.
        """
        arrival_time = self.env.now
        queue_pos = len(self.waiting_list)
        trace_workshop_waiting(arrival_time, patient.patient_id, queue_pos)
        self.waiting_list.append((arrival_time, patient))
        self.audit.update_patient(patient.patient_id, workshop_join_time=arrival_time)
        self._try_form_groups()

    def _should_start_workshop(self) -> bool:
        """
        Return ``True`` when conditions are met to form a new workshop group.

        A group is formed when either the waiting list has reached the target
        group size, or the oldest patient has exceeded the maximum wait.

        Returns
        -------
        bool
            ``True`` if a group can or must be started now.
        """
        if not self.waiting_list:
            return False
        group_size = self.system.experiment.workshop_group_size
        max_wait_days = self.system.experiment.workshop_max_wait_days
        if len(self.waiting_list) >= group_size:
            return True
        oldest_arrival_time, _ = self.waiting_list[0]
        return (self.env.now - oldest_arrival_time) >= max_wait_days

    def _try_form_groups(self) -> None:
        """
        Repeatedly form groups while :meth:`_should_start_workshop` is ``True``.
        """
        while self._should_start_workshop():
            self._form_group()

    def _form_group(self) -> None:
        """
        Dequeue the next cohort of patients and launch a :class:`WorkshopGroup`.

        Takes up to ``workshop_group_size`` patients from the front of the
        waiting list, assigns them a new group ID, records ``workshop_start_time``
        in the audit, and spawns a :meth:`WorkshopGroup.process` coroutine.
        """
        group_size = self.system.experiment.workshop_group_size
        member_count = min(group_size, len(self.waiting_list))
        members = [self.waiting_list.popleft()[1] for _ in range(member_count)]
        group_id = self.system.next_workshop_group_id
        for patient in members:
            self.active_patient_ids.add(patient.patient_id)
            self.audit.update_patient(
                patient.patient_id,
                workshop_start_time=self.env.now,
                workshop_group_id=group_id,
            )
            trace_workshop_started(
                self.env.now,
                patient.patient_id,
                group_id,
                member_count,
            )
        group = WorkshopGroup(group_id, members, self.system)
        self.system.next_workshop_group_id += 1
        self.env.process(group.process())

    def _monitor(self) -> Generator[simpy.Timeout, None, None]:
        """
        SimPy generator that checks for formable groups every simulated day.

        Yields
        ------
        simpy.Timeout
            One-day timeout events.
        """
        while True:
            yield self.env.timeout(1.0)
            self._try_form_groups()
