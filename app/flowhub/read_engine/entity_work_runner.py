"""Fast-tick runner for the per-entity Channel Read work queue.

Runs as a sibling task to OrderSyncRunner from the same process
(orders/runner.py main_async()), on a much shorter interval than the
~30s full-channel-due check, so webhook-driven observation converges in
seconds rather than waiting for the next slow tick -- without any new
scheduler process or infrastructure. Disabled by default
(FLOWHUB_CHANNEL_ENTITY_WORK_ENABLED); this task builds and tests the
capability, enabling it live is a separate operational decision.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from app.flowhub.data_layer.models import DlChannelEntityWork
from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.read_engine.entity_work import (
    claim_entity_work,
    complete_entity_work,
    recover_expired_entity_work,
    sync_pending_woocommerce_receipts,
)
from app.flowhub.read_engine.exceptions import IncrementalReadUnsupported
from app.flowhub.read_engine.manual import ManualReadService
from app.flowhub.read_engine.service import IncrementalReadEngine
from app.flowhub.security.upstream_errors import CATEGORY_INTERNAL_ERROR, classify_failure

LOGGER = logging.getLogger("flowhub.read_engine.entity_work_runner")


@dataclass(frozen=True)
class EntityWorkRunnerSettings:
    enabled: bool
    loop_interval_seconds: int
    claim_batch_size: int
    worker_concurrency: int
    lease_seconds: int

    @classmethod
    def from_env(cls) -> EntityWorkRunnerSettings:
        return cls(
            enabled=_env_bool("FLOWHUB_CHANNEL_ENTITY_WORK_ENABLED", False),
            loop_interval_seconds=_env_int("FLOWHUB_CHANNEL_ENTITY_WORK_POLL_SECONDS", 5),
            claim_batch_size=_env_int("FLOWHUB_CHANNEL_ENTITY_WORK_BATCH_SIZE", 25),
            worker_concurrency=_env_int("FLOWHUB_CHANNEL_ENTITY_WORK_CONCURRENCY", 5),
            lease_seconds=_env_int("FLOWHUB_CHANNEL_ENTITY_WORK_LEASE_SECONDS", 120),
        )


class ChannelEntityWorkRunner:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        settings: EntityWorkRunnerSettings | None = None,
        runner_id: str | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings or EntityWorkRunnerSettings.from_env()
        self.runner_id = runner_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:12]}"
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def serve_forever(self) -> None:
        if not self.settings.enabled:
            LOGGER.info("channel_entity_work_runner_disabled", extra={"runner_id": self.runner_id})
            return
        LOGGER.info("channel_entity_work_runner_started", extra={"runner_id": self.runner_id})
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:
                LOGGER.exception("channel_entity_work_runner_tick_failed", extra={"runner_id": self.runner_id})
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.settings.loop_interval_seconds)
            except TimeoutError:
                continue
        LOGGER.info("channel_entity_work_runner_stopped", extra={"runner_id": self.runner_id})

    async def run_once(self) -> dict[str, Any]:
        with self.session_factory() as db:
            recover_expired_entity_work(db)
        for connector_id in self._active_woocommerce_connector_ids():
            with self.session_factory() as db:
                sync_pending_woocommerce_receipts(db, connector_id)

        with self.session_factory() as db:
            claimed = claim_entity_work(
                db,
                worker_id=self.runner_id,
                limit=self.settings.claim_batch_size,
                lease_seconds=self.settings.lease_seconds,
            )
            claimed_ids = [work.id for work in claimed]

        if not claimed_ids:
            return {"runnerId": self.runner_id, "claimed": 0, "processed": 0}

        semaphore = asyncio.Semaphore(max(1, self.settings.worker_concurrency))

        async def _bounded(work_id: int) -> None:
            async with semaphore:
                await self._process_one(work_id)

        await asyncio.gather(*(_bounded(work_id) for work_id in claimed_ids))
        return {"runnerId": self.runner_id, "claimed": len(claimed_ids), "processed": len(claimed_ids)}

    async def _process_one(self, work_id: int) -> None:
        # Each claimed item gets its own session: one item's rollback must
        # never poison the others claimed in the same batch.
        with self.session_factory() as db:
            work = db.get(DlChannelEntityWork, work_id)
            if work is None or work.status != "running":
                return  # already recovered/completed by a concurrent path
            try:
                adapter = ManualReadService(db).adapter_for(work.connector_id)
                await IncrementalReadEngine(db).run_entity(
                    adapter, entity_id=work.entity_id, parent_id=work.parent_entity_id
                )
            except HTTPException as exc:
                complete_entity_work(
                    db, work, outcome="failed", error_category="not_configured", error_message=str(exc.detail)
                )
                return
            except IncrementalReadUnsupported as exc:
                complete_entity_work(
                    db, work, outcome="failed", error_category="not_configured", error_message=str(exc)
                )
                return
            except Exception as exc:
                classified = classify_failure(exc, source=work.connector_id.split(":", 1)[0])
                category = str(classified.get("category") or CATEGORY_INTERNAL_ERROR)
                complete_entity_work(
                    db,
                    work,
                    outcome="failed",
                    error_category=category,
                    error_message=str(classified.get("message") or exc.__class__.__name__),
                )
                return
            complete_entity_work(db, work, outcome="completed")

    def _active_woocommerce_connector_ids(self) -> list[str]:
        with self.session_factory() as db:
            rows = (
                db.query(IntegrationConnectorInstance.id)
                .filter(
                    IntegrationConnectorInstance.connector_type == "woocommerce",
                    IntegrationConnectorInstance.enabled.is_(True),
                )
                .all()
            )
            return [row[0] for row in rows]


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
