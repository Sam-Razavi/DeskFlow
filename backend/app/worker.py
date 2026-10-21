"""Background worker. Run with: arq app.worker.WorkerSettings"""

import logging
from typing import Any

from arq import cron
from arq.connections import RedisSettings
from arq.cron import CronJob

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.seed import DemoResetRefused, reset_demo
from app.services.sla_monitor import check_sla

logger = logging.getLogger("deskflow.worker")

# Early morning in Europe (UTC), so visitors during the working day see a freshly reset demo.
DEMO_RESET_HOUR = 3
DEMO_RESET_MINUTE = 30


async def sla_check(ctx: dict[str, Any]) -> dict[str, int]:
    async with SessionLocal() as session:
        newly = await check_sla(session)
    if any(newly.values()):
        logger.info("SLA check flagged tickets: %s", newly)
    return newly


async def demo_reset(ctx: dict[str, Any]) -> str:
    """Recreate the public demo relative to now. reset_demo checks again that it may run."""
    try:
        async with SessionLocal() as session:
            result = await reset_demo(session)
    except DemoResetRefused as refused:
        logger.warning("Demo reset skipped: %s", refused)
        return f"skipped: {refused}"
    logger.info("Demo data reset: %s", result)
    return "reset"


def scheduled_jobs(settings: Settings) -> list[CronJob]:
    # The SLA check runs once at startup (so a restart catches up straight away) and then every
    # minute. The demo reset is only scheduled at all when SEED_DEMO_DATA=true.
    jobs = [cron(sla_check, second=0, run_at_startup=True)]
    if settings.demo_reset_enabled:
        jobs.append(cron(demo_reset, hour=DEMO_RESET_HOUR, minute=DEMO_RESET_MINUTE, second=0))
    return jobs


class WorkerSettings:
    cron_jobs = scheduled_jobs(get_settings())
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
