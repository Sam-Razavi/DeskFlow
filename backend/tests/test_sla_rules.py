from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.ticket import Priority, TicketStatus
from app.services import sla
from app.services.sla import SlaState

T0 = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
H = timedelta(hours=1)


def make(priority=Priority.P2, status=TicketStatus.NEW, **overrides):
    response_due, resolution_due = sla.due_dates(T0, priority)
    fields = {
        "priority": priority,
        "status": status,
        "created_at": T0,
        "resolved_at": None,
        "first_response_at": None,
        "response_due_at": response_due,
        "resolution_due_at": resolution_due,
        "sla_paused_at": None,
        "sla_paused_seconds": 0,
    }
    return SimpleNamespace(**{**fields, **overrides})


@pytest.mark.parametrize(
    ("priority", "response", "resolution"),
    [
        (Priority.P1, 1, 4),
        (Priority.P2, 4, 8),
        (Priority.P3, 8, 24),
        (Priority.P4, 24, 72),
    ],
)
def test_targets_per_priority(priority, response, resolution):
    response_due, resolution_due = sla.due_dates(T0, priority)
    assert response_due - T0 == response * H
    assert resolution_due - T0 == resolution * H


def test_due_dates_include_time_already_paused():
    _, resolution_due = sla.due_dates(T0, Priority.P1, paused_seconds=1800)
    assert resolution_due - T0 == timedelta(hours=4, minutes=30)


def test_resolution_state_moves_from_ok_to_at_risk_to_breached():
    ticket = make(Priority.P2)  # 8h window, at risk from 6h
    assert sla.resolution_state(ticket, T0 + 5 * H) == SlaState.OK
    assert sla.resolution_state(ticket, T0 + 6 * H) == SlaState.AT_RISK
    assert sla.resolution_state(ticket, T0 + 8 * H) == SlaState.AT_RISK  # due exactly now
    assert sla.resolution_state(ticket, T0 + 8 * H + timedelta(seconds=1)) == SlaState.BREACHED


def test_response_state_without_a_reply_follows_the_clock():
    ticket = make(Priority.P1)  # 1h window
    assert sla.response_state(ticket, T0 + timedelta(minutes=10)) == SlaState.OK
    assert sla.response_state(ticket, T0 + timedelta(minutes=50)) == SlaState.AT_RISK
    assert sla.response_state(ticket, T0 + 2 * H) == SlaState.BREACHED


def test_a_reply_settles_the_response_sla_for_good():
    on_time = make(first_response_at=T0 + H)
    late = make(first_response_at=T0 + 5 * H)
    assert sla.response_state(on_time, T0 + 100 * H) == SlaState.MET
    assert sla.response_state(late, T0 + 100 * H) == SlaState.BREACHED


def test_resolved_tickets_are_judged_on_when_they_were_resolved():
    done_in_time = make(status=TicketStatus.RESOLVED, resolved_at=T0 + 7 * H)
    done_late = make(status=TicketStatus.CLOSED, resolved_at=T0 + 9 * H)
    assert sla.resolution_state(done_in_time, T0 + 500 * H) == SlaState.MET
    assert sla.resolution_state(done_late, T0 + 500 * H) == SlaState.BREACHED


def test_response_not_applicable_when_closed_without_a_reply():
    ticket = make(status=TicketStatus.CLOSED, resolved_at=T0 + H)
    assert sla.response_state(ticket, T0 + 50 * H) == SlaState.NOT_APPLICABLE


def test_paused_ticket_never_breaches():
    ticket = make(status=TicketStatus.PENDING, sla_paused_at=T0 + H)
    assert sla.resolution_state(ticket, T0 + 1000 * H) == SlaState.PAUSED
    assert sla.response_state(ticket, T0 + 1000 * H) == SlaState.PAUSED


def test_overall_state_reports_the_worst_of_the_two():
    # Responded in time but resolution is overdue.
    ticket = make(first_response_at=T0 + H)
    assert sla.overall_state(ticket, T0 + 9 * H) == SlaState.BREACHED
    # Everything delivered on time.
    done = make(status=TicketStatus.RESOLVED, resolved_at=T0 + 3 * H, first_response_at=T0 + H)
    assert sla.overall_state(done, T0 + 50 * H) == SlaState.MET


def test_pausing_and_resuming_pushes_deadlines_back_by_the_wait():
    ticket = make(Priority.P2)
    original_resolution, original_response = ticket.resolution_due_at, ticket.response_due_at

    sla.on_status_change(ticket, TicketStatus.IN_PROGRESS, TicketStatus.PENDING, T0 + H)
    assert ticket.sla_paused_at == T0 + H

    sla.on_status_change(ticket, TicketStatus.PENDING, TicketStatus.IN_PROGRESS, T0 + 3 * H)
    assert ticket.sla_paused_at is None
    assert ticket.sla_paused_seconds == 2 * 3600
    assert ticket.resolution_due_at == original_resolution + 2 * H
    assert ticket.response_due_at == original_response + 2 * H


def test_resuming_does_not_move_a_response_deadline_that_was_already_answered():
    ticket = make(first_response_at=T0 + 5 * H)  # answered late: response breached
    original_response = ticket.response_due_at
    sla.on_status_change(ticket, TicketStatus.IN_PROGRESS, TicketStatus.PENDING, T0 + 6 * H)
    sla.on_status_change(ticket, TicketStatus.PENDING, TicketStatus.RESOLVED, T0 + 20 * H)
    assert ticket.response_due_at == original_response
    assert sla.response_state(ticket, T0 + 30 * H) == SlaState.BREACHED


def test_repeated_pause_cycles_accumulate():
    ticket = make(Priority.P3)
    original = ticket.resolution_due_at
    for start in (1, 10):
        sla.on_status_change(ticket, TicketStatus.IN_PROGRESS, TicketStatus.PENDING, T0 + start * H)
        sla.on_status_change(
            ticket, TicketStatus.PENDING, TicketStatus.IN_PROGRESS, T0 + (start + 2) * H
        )
    assert ticket.sla_paused_seconds == 4 * 3600
    assert ticket.resolution_due_at == original + 4 * H


def test_pausing_twice_keeps_the_original_pause_start():
    ticket = make()
    sla.on_status_change(ticket, TicketStatus.NEW, TicketStatus.PENDING, T0 + H)
    sla.on_status_change(ticket, TicketStatus.PENDING, TicketStatus.PENDING, T0 + 2 * H)
    assert ticket.sla_paused_at == T0 + H


def test_changing_priority_recalculates_the_deadlines():
    ticket = make(Priority.P4)
    ticket.priority = Priority.P1
    sla.recompute(ticket)
    assert ticket.resolution_due_at - T0 == 4 * H
    assert ticket.response_due_at - T0 == 1 * H


def test_recompute_keeps_time_already_paused_and_a_settled_response():
    ticket = make(Priority.P4, first_response_at=T0 + 2 * H, sla_paused_seconds=3600)
    original_response = ticket.response_due_at
    ticket.priority = Priority.P1
    sla.recompute(ticket)
    assert ticket.resolution_due_at - T0 == 5 * H  # 4h target + 1h already paused
    assert ticket.response_due_at == original_response
