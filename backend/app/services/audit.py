import enum
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.user import User


def _jsonable(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, list[Any]]:
    """Return {field: [old, new]} for every field whose value differs."""
    return {
        field: [_jsonable(before[field]), _jsonable(after[field])]
        for field in after
        if before.get(field) != after[field]
    }


def record(
    session: AsyncSession,
    actor: User | None,
    entity_type: str,
    entity_id: int,
    action: str,
    changes: Mapping[str, Any],
) -> None:
    """Stage an audit row in the caller's transaction (commits or rolls back with it)."""
    session.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            changes={k: _jsonable(v) for k, v in changes.items()},
        )
    )
