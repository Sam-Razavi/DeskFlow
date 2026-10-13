from pydantic import BaseModel

from app.models.ticket import Priority


class DashboardSummary(BaseModel):
    open_total: int
    open_by_priority: dict[Priority, int]
    sla_breached: int
    sla_at_risk: int
    unassigned: int
    assigned_to_me: int
    awaiting_confirmation: int
