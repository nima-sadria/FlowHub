"""Manual read service for production API routes."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.connectors.read import NextcloudSpreadsheetReadAdapter, WooCommerceProductReadAdapter
from app.flowhub.read_engine.contracts import ReadConnectorAdapter
from app.flowhub.read_engine.exceptions import IncrementalReadUnsupported
from app.flowhub.read_engine.service import IncrementalReadEngine
from app.flowhub.setup.service import AppConfigService


class ManualReadService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.config = AppConfigService(db)

    async def run_manual(self, connector_id: str, *, triggered_by: str) -> dict:
        adapter = self.adapter_for(connector_id)
        try:
            progress = await IncrementalReadEngine(self.db).run_manual(adapter, triggered_by=triggered_by)
        except IncrementalReadUnsupported as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": exc.code, "message": str(exc)},
            ) from exc
        return {
            **asdict(progress),
            "manual_triggered": True,
            "scheduler_started": False,
            "automatic_sync": False,
        }

    def adapter_for(self, connector_id: str) -> ReadConnectorAdapter:
        if connector_id == "woocommerce:primary":
            url = self.config.get("woocommerce.url") or ""
            key = self.config.get("woocommerce.key") or ""
            secret = self.config.get("woocommerce.secret") or ""
            if not url or not key or not secret:
                raise HTTPException(status.HTTP_409_CONFLICT, "connector_not_configured")
            return WooCommerceProductReadAdapter(url=url, key=key, secret=secret)

        if connector_id == "nextcloud:primary":
            return NextcloudSpreadsheetReadAdapter(
                url=self.config.get("nextcloud.url") or "",
                username=self.config.get("nextcloud.username") or "",
                password=self.config.get("nextcloud.password") or "",
                spreadsheet_path=self.config.get("nextcloud.spreadsheet_path") or "",
            )

        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "incremental_read_unsupported", "message": "incremental_read_unsupported"},
        )
