"""FlowHub Beta — /api/v2/data-layer router.

Read-only endpoints exposing Data Layer status for the /data-layer UI page.
No write paths to WooCommerce or Nextcloud are present or possible.

Routes:
  GET /api/v2/data-layer/status              — overall Data Layer status summary
  GET /api/v2/data-layer/products/status     — product cache status
  GET /api/v2/data-layer/sources/status      — source + destination snapshot status
  GET /api/v2/data-layer/connectors/status   — connector health + telemetry
  GET /api/v2/data-layer/refresh-jobs        — recent refresh job history
  GET /api/v2/data-layer/invalidation-events — recent invalidation events
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.beta.auth.dependencies import get_current_user
from app.beta.auth.models import BetaUser
from app.beta.database import get_db
from app.beta.data_layer.health_service import ConnectorHealthService
from app.beta.data_layer.invalidation_service import InvalidationService
from app.beta.data_layer.product_service import ProductReadModelService
from app.beta.data_layer.refresh_service import RefreshJobService
from app.beta.data_layer.snapshot_service import DestinationSnapshotService, SourceSnapshotService
from app.beta.data_layer.telemetry_service import ConnectorTelemetryService

router = APIRouter(prefix="/data-layer", tags=["data-layer"])


@router.get("/status")
async def data_layer_status(
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Overall Data Layer status. Aggregates all sub-stores."""
    product_status = ProductReadModelService(db).get_status()
    health_summary = ConnectorHealthService(db).get_summary()
    telemetry_summary = ConnectorTelemetryService(db).get_summary()
    src_status = SourceSnapshotService(db).get_status()
    dst_status = DestinationSnapshotService(db).get_status()
    refresh_summary = RefreshJobService(db).get_summary()
    inv_summary = InvalidationService(db).get_summary()

    initialized = any([
        product_status["initialized"],
        health_summary["initialized"],
        src_status["initialized"],
        dst_status["initialized"],
    ])

    return {
        "data_layer_version": "1.0",
        "initialized": initialized,
        "read_only": True,
        "apply_blocked": True,
        "product_cache": product_status,
        "source_snapshots": src_status,
        "destination_snapshots": dst_status,
        "connector_health": health_summary,
        "connector_telemetry": telemetry_summary,
        "refresh_jobs": refresh_summary,
        "invalidation_events": inv_summary,
    }


@router.get("/products/status")
async def products_status(
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Product cache status."""
    return ProductReadModelService(db).get_status()


@router.get("/sources/status")
async def sources_status(
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Source and destination snapshot status."""
    src_svc = SourceSnapshotService(db)
    dst_svc = DestinationSnapshotService(db)
    return {
        "source": src_svc.get_status(),
        "destination": dst_svc.get_status(),
        "source_snapshots": src_svc.get_all(),
        "destination_snapshots": dst_svc.get_all(),
    }


@router.get("/connectors/status")
async def connectors_status(
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Connector health and telemetry."""
    return {
        "health": {
            "summary": ConnectorHealthService(db).get_summary(),
            "connectors": ConnectorHealthService(db).get_all(),
        },
        "telemetry": {
            "summary": ConnectorTelemetryService(db).get_summary(),
            "connectors": ConnectorTelemetryService(db).get_all(),
        },
    }


@router.get("/refresh-jobs")
async def refresh_jobs(
    limit: int = 20,
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Recent refresh job history."""
    svc = RefreshJobService(db)
    return {
        "summary": svc.get_summary(),
        "items": svc.list_recent(limit=min(limit, 100)),
    }


@router.get("/invalidation-events")
async def invalidation_events(
    limit: int = 50,
    entity_type: str | None = None,
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Recent invalidation events."""
    svc = InvalidationService(db)
    return {
        "summary": svc.get_summary(),
        "items": svc.list_recent(limit=min(limit, 200), entity_type=entity_type),
    }
