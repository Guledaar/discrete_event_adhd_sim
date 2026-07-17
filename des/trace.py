"""Standalone patient-flow trace logging (independent of Experiment)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from des.config import TRACE

_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

_enabled: bool = TRACE


def enable_trace() -> None:
    """
    Enable pathway tracing for subsequent simulation events.

    Notes
    -----
    Sets the module-level trace flag used by :func:`trace_line`.
    """
    global _enabled
    _enabled = True


def disable_trace() -> None:
    """
    Disable pathway tracing.

    Notes
    -----
    Clears the module-level trace flag used by :func:`trace_line`.
    """
    global _enabled
    _enabled = False


def is_tracing() -> bool:
    """
    Return whether pathway trace messages will be printed.

    Returns
    -------
    bool
        ``True`` when tracing is currently enabled.
    """
    return _enabled


@contextmanager
def tracing(enabled: bool = True) -> Iterator[None]:
    """
    Temporarily enable or disable tracing within a ``with`` block.

    Parameters
    ----------
    enabled : bool, optional
        Tracing state inside the block. Default is ``True``.
    """
    global _enabled
    previous = _enabled
    _enabled = enabled
    try:
        yield
    finally:
        _enabled = previous


def weekday_name(time: float) -> str:
    """
    Return the weekday name for a given simulation time.

    Parameters
    ----------
    time : float
        Simulation time in days (0 = Monday, 5 = Saturday, 6 = Sunday).

    Returns
    -------
    str
        Name of the weekday (e.g. ``'Monday'``).
    """
    return _WEEKDAYS[int(time % 7)]


def trace_line(time: float, message: str) -> None:
    """
    Print a formatted trace line when tracing is enabled.

    Output format: ``[Time X.XXX | Weekday] message``.

    Parameters
    ----------
    time : float
        Current simulation time in days.
    message : str
        Event description to append after the timestamp header.
    """
    if not _enabled:
        return
    print(f"[Time {time:.3f} | {weekday_name(time)}] {message}")


def trace_referral(time: float, patient_id: int) -> None:
    """
    Log patient arrival and referral submission.

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    """
    trace_line(time, f"Patient {patient_id} entered system. Referral submitted.")


def trace_triage_accepted(time: float, patient_id: int) -> None:
    """
    Log a successful triage outcome (referral accepted).

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    """
    trace_line(time, f"Patient {patient_id} passed triage. Referral accepted.")


def trace_triage_rejected(time: float, patient_id: int) -> None:
    """
    Log a referral rejection at triage (RTT clock nullified).

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    """
    trace_line(time, f"Patient {patient_id} Exit — referral rejected at triage.")


def trace_admin_cleared(time: float, patient_id: int) -> None:
    """
    Log that a patient passed the administrative review check.

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    """
    trace_line(time, f"Patient {patient_id} cleared admin review.")


def trace_admin_removed(time: float, patient_id: int) -> None:
    """
    Log an administrative removal before assessment.

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    """
    trace_line(time, f"Patient {patient_id} Exit — removed at admin review.")


def trace_assessments_required(time: float, patient_id: int, required: int) -> None:
    """
    Log the number of assessment appointments drawn for the patient.

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    required : int
        Number of assessment appointments required.
    """
    trace_line(
        time,
        f"Patient {patient_id} requires {required} assessment appointment(s).",
    )


def trace_assessment_waiting(
    time: float,
    patient_id: int,
    appointment_num: int,
    total: int,
    queue_pos: int,
) -> None:
    """
    Log that the patient is waiting for a clinician-hour slot.

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    appointment_num : int
        1-based appointment index.
    total : int
        Total appointments required.
    queue_pos : int
        Queue position at request time.
    """
    trace_line(
        time,
        f"Patient {patient_id} waiting for assessment appointment "
        f"{appointment_num}/{total} (queue pos: {queue_pos}).",
    )


def trace_assessment_started(
    time: float,
    patient_id: int,
    appointment_num: int,
    total: int,
    duration_hours: float,
) -> None:
    """
    Log the start of an assessment appointment.

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    appointment_num : int
        1-based appointment index.
    total : int
        Total appointments required.
    duration_hours : float
        Clinician hours for this appointment.
    """
    trace_line(
        time,
        f"Patient {patient_id} started assessment appointment "
        f"{appointment_num}/{total} ({duration_hours:.1f} clinician-hours).",
    )


def trace_assessment_completed(
    time: float,
    patient_id: int,
    appointment_num: int,
    total: int,
) -> None:
    """
    Log the completion of an individual assessment appointment.

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    appointment_num : int
        1-based appointment index.
    total : int
        Total appointments required.
    """
    trace_line(
        time,
        f"Patient {patient_id} completed assessment appointment "
        f"{appointment_num}/{total}.",
    )


def trace_assessment_gap(time: float, patient_id: int, gap_days: float) -> None:
    """
    Log the inter-appointment gap between two assessment appointments.

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    gap_days : float
        Gap length in days.
    """
    trace_line(
        time,
        f"Patient {patient_id} inter-appointment gap ({gap_days:g} days).",
    )


def trace_assessments_finished(time: float, patient_id: int, total: int) -> None:
    """
    Log completion of all assessment appointments for the patient.

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    total : int
        Total appointments completed.
    """
    trace_line(
        time,
        f"Patient {patient_id} finished all assessments ({total}/{total}).",
    )


def trace_diagnosis(time: float, patient_id: int, diagnosed: bool) -> None:
    """
    Log the diagnosis outcome after assessment completion.

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    diagnosed : bool
        ``True`` if diagnosis was confirmed.
    """
    if diagnosed:
        trace_line(time, f"Patient {patient_id} diagnosis confirmed.")
    else:
        trace_line(time, f"Patient {patient_id} Exit — no diagnosis after assessment.")


def trace_virtual_support(time: float, patient_id: int) -> None:
    """
    Log routing of a diagnosed patient to virtual post-diagnosis support.

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    """
    trace_line(time, f"Patient {patient_id} routed to virtual post-diagnosis support.")


def trace_workshop_waiting(time: float, patient_id: int, queue_pos: int) -> None:
    """
    Log that a diagnosed patient joined the clinical workshop waiting list.

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    queue_pos : int
        Position on the workshop waiting list.
    """
    trace_line(
        time,
        f"Patient {patient_id} waiting for clinical workshop group (queue pos: {queue_pos}).",
    )


def trace_workshop_started(time: float, patient_id: int, group_id: int, group_size: int) -> None:
    """
    Log that a workshop group has been formed and started.

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    group_id : int
        Workshop group identifier.
    group_size : int
        Number of patients in the group.
    """
    trace_line(
        time,
        f"Patient {patient_id} joined workshop group {group_id} ({group_size} patients).",
    )


def trace_workshop_session_started(
    time: float,
    patient_id: int,
    session_num: int,
    total_sessions: int,
    group_id: int,
) -> None:
    """
    Log the start of one workshop session.

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    session_num : int
        1-based session index.
    total_sessions : int
        Total sessions in the programme.
    group_id : int
        Workshop group identifier.
    """
    trace_line(
        time,
        f"Patient {patient_id} workshop session {session_num}/{total_sessions} "
        f"started (group {group_id}).",
    )


def trace_workshop_session_completed(
    time: float,
    patient_id: int,
    session_num: int,
    total_sessions: int,
) -> None:
    """
    Log the completion of one workshop session.

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    session_num : int
        1-based session index.
    total_sessions : int
        Total sessions in the programme.
    """
    trace_line(
        time,
        f"Patient {patient_id} completed workshop session {session_num}/{total_sessions}.",
    )


def trace_pathway_complete(time: float, patient_id: int, route: str) -> None:
    """
    Log final pathway completion with the exit route.

    Parameters
    ----------
    time : float
        Simulation time in days.
    patient_id : int
        Patient identifier.
    route : str
        Exit route label (e.g. ``workshop_complete``).
    """
    trace_line(time, f"Patient {patient_id} pathway complete — {route}.")


def trace_summary(cohort_arrivals: int, collection_days: float) -> None:
    """
    Print a summary line at the end of a traced simulation run.

    Parameters
    ----------
    cohort_arrivals : int
        Number of arrivals in the collection cohort.
    collection_days : float
        Collection window length in days.
    """
    if not _enabled:
        return
    days_label = f"{collection_days:g}-day"
    print(
        f"Trace complete: {cohort_arrivals} cohort arrivals in a "
        f"{days_label} collection window (see pathway messages above)"
    )
