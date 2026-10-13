from app.models.asset import AssetStatus as S

# Moves made through the status endpoint. Assigning and unassigning go through the assignment
# endpoint, which is the only way into or out of ASSIGNED, so an assignee is never left dangling.
TRANSITIONS: dict[S, set[S]] = {
    S.IN_STOCK: {S.IN_REPAIR, S.RETIRED},
    S.ASSIGNED: {S.IN_REPAIR, S.RETIRED},  # taking it back is implied; the assignee is cleared
    S.IN_REPAIR: {S.IN_STOCK, S.RETIRED},
    S.RETIRED: set(),
}


def can_transition(current: S, target: S) -> bool:
    return target in TRANSITIONS[current]
