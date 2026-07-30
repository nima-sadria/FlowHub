"""Dedicated exchange-rate scheduler process.

Run separately from the API:

    python -m app.flowhub.exchange_rates.runner

The API never owns the loop. Atomic database leases in ExchangeRateService
prevent overlap between runner instances and manual refreshes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import uuid
from contextlib import suppress
from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from app.flowhub.database import _get_engine

from .models import ExchangeRateProviderConfig
from .service import ExchangeRateService

LOGGER = logging.getLogger("flowhub.exchange_rates.runner")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return max(5, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


class ExchangeRateRunner:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        enabled: bool | None = None,
        poll_seconds: int | None = None,
        runner_id: str | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.enabled = (
            _env_bool("FLOWHUB_EXCHANGE_RATE_RUNNER_ENABLED", True)
            if enabled is None
            else enabled
        )
        self.poll_seconds = (
            _env_int("FLOWHUB_EXCHANGE_RATE_RUNNER_POLL_SECONDS", 60)
            if poll_seconds is None
            else max(5, poll_seconds)
        )
        self.runner_id = runner_id or (
            f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:12]}"
        )
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    def _heartbeat(self, state: str) -> None:
        with self.session_factory() as db:
            service = ExchangeRateService(db)
            provider = service.ensure_provider()
            provider.runner_id = self.runner_id
            provider.runner_state = state
            provider.runner_heartbeat_at = _utcnow()
            db.commit()

    def run_once(self) -> dict:
        with self.session_factory() as db:
            service = ExchangeRateService(db)
            provider = service.ensure_provider()
            provider.runner_id = self.runner_id
            provider.runner_state = "running"
            provider.runner_heartbeat_at = _utcnow()
            db.commit()
            result = service.scheduler_tick()
            provider = db.get(ExchangeRateProviderConfig, service.provider_id)
            if provider is not None:
                provider.runner_state = "idle"
                provider.runner_heartbeat_at = _utcnow()
                db.commit()
            return result

    async def serve_forever(self) -> None:
        LOGGER.info(
            "exchange_rate_runner_started",
            extra={"runner_id": self.runner_id, "enabled": self.enabled},
        )
        while not self._stop.is_set():
            try:
                if self.enabled:
                    result = await asyncio.to_thread(self.run_once)
                    LOGGER.info(
                        "exchange_rate_runner_tick",
                        extra={
                            "runner_id": self.runner_id,
                            "status": result.get("status"),
                        },
                    )
                else:
                    await asyncio.to_thread(self._heartbeat, "disabled")
            except Exception as exc:
                # Log only the exception class; provider URLs, query strings,
                # and credentials never enter runner logs.
                LOGGER.error(
                    "exchange_rate_runner_tick_failed",
                    extra={
                        "runner_id": self.runner_id,
                        "category": exc.__class__.__name__,
                    },
                )
                await asyncio.to_thread(self._heartbeat, "error")
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self.poll_seconds
                )
            except TimeoutError:
                continue
        await asyncio.to_thread(self._heartbeat, "stopped")
        LOGGER.info(
            "exchange_rate_runner_stopped", extra={"runner_id": self.runner_id}
        )


def make_session_factory() -> sessionmaker:
    db_url = os.environ.get("FLOWHUB_DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("FLOWHUB_DATABASE_URL is not configured")
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=_get_engine(db_url),
        expire_on_commit=False,
    )


async def main_async() -> None:
    logging.basicConfig(level=os.environ.get("FLOWHUB_LOG_LEVEL", "INFO"))
    runner = ExchangeRateRunner(make_session_factory())
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, runner.stop)
    await runner.serve_forever()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
