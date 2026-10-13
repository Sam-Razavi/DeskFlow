"""Background worker. Run with: arq app.worker.WorkerSettings"""

import logging
from typing import Any

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.services.sla_monitor import check_sla

logger = logging.getLogger("deskflow.worker")


async def sla_check(ctx: dict[str, Any]) -> dict[str, int]:
    async with SessionLocal() as session:
        newly = await check_sla(session)
    if any(newly.values()):
        logger.info("SLA check flagged tickets: %s", newly)
    return newly


class WorkerSettings:
    # Runs once at startup (so a restart catches up straight away) and then every minute.
    cron_jobs = [cron(sla_check, second=0, run_at_startup=True)]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
