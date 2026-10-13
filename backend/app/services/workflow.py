from app.models.ticket import TicketStatus as S
from app.models.user import Role

TRANSITIONS: dict[S, set[S]] = {
    S.NEW: {S.IN_PROGRESS, S.PENDING, S.RESOLVED, S.CLOSED},
    S.IN_PROGRESS: {S.PENDING, S.RESOLVED},
    S.PENDING: {S.IN_PROGRESS, S.RESOLVED},
    S.RESOLVED: {S.IN_PROGRESS, S.CLOSED},  # reopen or confirm
    S.CLOSED: set(),
}

# What a requester may do to their own ticket: confirm a fix or reopen it.
REQUESTER_TRANSITIONS: set[tuple[S, S]] = {(S.RESOLVED, S.CLOSED), (S.RESOLVED, S.IN_PROGRESS)}


def can_transition(current: S, target: S, role: Role) -> bool:
    if target not in TRANSITIONS[current]:
        return False
    if role == Role.REQUESTER:
        return (current, target) in REQUESTER_TRANSITIONS
    return True
