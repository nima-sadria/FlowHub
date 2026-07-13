"""Application use cases for FlowHub Unified Workspace."""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.commerce.service import CommerceHubService
from app.flowhub.data_layer.models import DlProductCache
from app.flowhub.product_pricing.service import ProductPricingService
from app.flowhub.setup.service import AppConfigService
from app.flowhub.unified_workspace.authorization import has_workspace_permission
from app.flowhub.unified_workspace.connectors import WorkspaceConnectorFactory
from app.flowhub.unified_workspace.domain import (
    ApplyState,
    ChannelCapabilities,
    DraftChange,
    EntryPoint,
    MappingState,
    Money,
    ProductKind,
    ReviewState,
    WorkspaceDomainError,
    canonical_text,
    checksum,
    deterministic_revision_checksum,
    stable_json,
    utcnow,
    validate_product_editable,
    values_equal,
)
from app.flowhub.unified_workspace.events import (
    DomainEvent,
    DomainEventBus,
    PersistenceAuditSubscriber,
)
from app.flowhub.unified_workspace.listing_guard import (
    ListingGuardConflict,
    acquire_listing_guard,
)
from app.flowhub.unified_workspace.models import (
    ApplyJob,
    ApplyJobItem,
    CanonicalProduct,
    ChannelCache,
    CurrencyProfile,
    Draft,
    DraftRevision,
    DraftRevisionChange,
    Listing,
    MappingRevision,
    Review,
    ReviewCacheVersion,
    ReviewItem,
    ReviewSelection,
    SnapshotRow,
    UnifiedAuditEntry,
    UnifiedWorkspace,
    UserWorkspacePreference,
    ValidationIssue,
    WorkspaceChannel,
    WorkspaceLock,
    WorkspaceSnapshot,
)
from app.flowhub.unified_workspace.repositories import (
    ApplyRepository,
    AuditRepository,
    DraftRepository,
    PreferenceRepository,
    ReviewRepository,
    WorkspaceRepository,
)
from app.flowhub.workspace.price_workflow import WorkspacePriceWorkflowService
from app.flowhub.write_pipeline.models import (
    ProviderWriteAttempt,
    ProviderWriteAttemptEvent,
)
from app.flowhub.write_pipeline.service import WritePipelineService
from app.flowhub.write_pipeline.workspace_contracts import (
    WorkspaceWriteBatchCommand,
    WorkspaceWriteIntent,
    WorkspaceWriteResult,
    WriteOutcome,
)

SCHEMA_VERSION = "uw-snapshot-1"
NORMALIZATION_VERSION = "uw-normalization-1"
VALIDATION_VERSION = "uw-validation-1"
CURRENCY_RULESET_VERSION = "uw-currency-1"
MAX_SELECTION = 10_000
MAX_DRAFT_CHANGES = 30_000
LOCK_MINUTES = 15
STALE_APPLY_MINUTES = 5
logger = logging.getLogger("flowhub.unified_workspace")


def _id() -> str:
    return str(uuid.uuid4())


class UnifiedWorkspaceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.workspaces = WorkspaceRepository(db)
        self.drafts = DraftRepository(db)
        self.reviews = ReviewRepository(db)
        self.applies = ApplyRepository(db)
        self.audits = AuditRepository(db)
        self.preferences = PreferenceRepository(db)
        self.config = AppConfigService(db)
        self.commerce = CommerceHubService(db)
        self.pricing = ProductPricingService(db)
        self.connectors = WorkspaceConnectorFactory(self.pricing, self.commerce)
        self.events = DomainEventBus()
        self.events.subscribe(PersistenceAuditSubscriber(db, _id))

    # -- Workspace and snapshots ---------------------------------------------

    def create_manual_workspace(
        self, *, name: str, selections: list[dict[str, Any]], user: FlowHubUser, correlation_id: str
    ) -> dict[str, Any]:
        if not selections or len(selections) > MAX_SELECTION:
            raise self._unprocessable(
                "WORKSPACE_SELECTION_INVALID", f"Select between 1 and {MAX_SELECTION} products."
            )
        normalized_selection = sorted(
            {
                (canonical_text(item.get("connector_id")), canonical_text(item.get("product_id")))
                for item in selections
                if canonical_text(item.get("connector_id"))
                and canonical_text(item.get("product_id"))
            }
        )
        if len(normalized_selection) != len(selections):
            raise self._unprocessable(
                "WORKSPACE_SELECTION_INVALID",
                "Selections must be unique and include connector_id and product_id.",
            )
        self._seed_channels()
        currency_profile = self._global_currency_profile()
        cache_rows = (
            self.db.query(DlProductCache)
            .filter(
                tuple_(DlProductCache.connector_id, DlProductCache.product_id).in_(
                    normalized_selection
                ),
                DlProductCache.exists.is_(True),
            )
            .all()
        )
        found: dict[tuple[str, str], DlProductCache] = {
            (str(row.connector_id), str(row.product_id)): row for row in cache_rows
        }
        missing = [
            f"{connector}:{product}"
            for connector, product in normalized_selection
            if (connector, product) not in found
        ]
        if missing:
            raise self._unprocessable(
                "PRODUCT_SELECTION_NOT_FOUND",
                "Selected cache records were not found.",
                {"missing": missing},
            )
        listing_map = {
            (item.channel_id, item.external_primary_id): item
            for item in self.db.query(Listing)
            .filter(
                tuple_(Listing.channel_id, Listing.external_primary_id).in_(normalized_selection)
            )
            .all()
        }
        canonical_ids = {item.canonical_product_id for item in listing_map.values()}
        canonical_map = (
            {
                item.id: item
                for item in self.db.query(CanonicalProduct)
                .filter(CanonicalProduct.id.in_(canonical_ids))
                .all()
            }
            if canonical_ids
            else {}
        )
        listing_ids = {item.id for item in listing_map.values()}
        cache_map = (
            {
                item.listing_id: item
                for item in self.db.query(ChannelCache)
                .filter(ChannelCache.listing_id.in_(listing_ids))
                .all()
            }
            if listing_ids
            else {}
        )
        channel_map = {
            item.id: item
            for item in self.db.query(WorkspaceChannel)
            .filter(WorkspaceChannel.id.in_({item[0] for item in normalized_selection}))
            .all()
        }

        workspace_id = _id()
        snapshot_id = _id()
        workspace = UnifiedWorkspace(
            id=workspace_id,
            name=canonical_text(name) or "Manual Workspace",
            entry_point=EntryPoint.MANUAL,
            source_type=None,
            owner_user_id=user.id,
            status="active",
            version=1,
        )
        self.db.add(workspace)
        snapshot_payload: list[dict[str, Any]] = []
        staged_rows: list[SnapshotRow] = []
        for row_number, identity in enumerate(normalized_selection, start=1):
            cache_row = found[identity]
            canonical, listing, channel_cache = self._materialize_cache_identity(
                cache_row,
                listing_map=listing_map,
                canonical_map=canonical_map,
                cache_map=cache_map,
                channel_map=channel_map,
            )
            normalized = self._normalized_snapshot_data(canonical, listing, channel_cache)
            row_payload = {
                "row_number": row_number,
                "canonical_product_id": canonical.id,
                "listing_id": listing.id,
                "mapping_version": listing.mapping_version,
                "normalized": normalized,
            }
            snapshot_payload.append(row_payload)
            staged_rows.append(
                SnapshotRow(
                    id=_id(),
                    snapshot_id=snapshot_id,
                    row_number=row_number,
                    canonical_product_id=canonical.id,
                    listing_id=listing.id,
                    mapping_version=listing.mapping_version,
                    raw_data_json={
                        "connector_id": cache_row.connector_id,
                        "product_id": cache_row.product_id,
                    },
                    normalized_data_json=normalized,
                    row_checksum=checksum(row_payload),
                )
            )
        snapshot_checksum = checksum(
            {
                "workspace_id": workspace_id,
                "entry_point": EntryPoint.MANUAL,
                "rows": snapshot_payload,
                "currency_profile": currency_profile.id,
                "normalization": NORMALIZATION_VERSION,
                "validation": VALIDATION_VERSION,
            }
        )
        snapshot = WorkspaceSnapshot(
            id=snapshot_id,
            workspace_id=workspace_id,
            entry_point=EntryPoint.MANUAL,
            source_type=None,
            creator_user_id=user.id,
            schema_version=SCHEMA_VERSION,
            content_checksum=snapshot_checksum,
            normalization_version=NORMALIZATION_VERSION,
            validation_ruleset_version=VALIDATION_VERSION,
            mapping_version=max((item.mapping_version or 1 for item in staged_rows), default=1),
            currency_profile_id=currency_profile.id,
            source_metadata_json={},
            acquisition_metadata_json={
                "selection_count": len(staged_rows),
                "read_external_source": False,
            },
        )
        draft = Draft(
            id=_id(),
            workspace_id=workspace_id,
            snapshot_id=snapshot_id,
            owner_user_id=user.id,
            current_revision_id=None,
            version=0,
            status="draft",
        )
        self.db.add_all([snapshot, *staged_rows, draft])
        self._audit(
            "workspace_created",
            user,
            correlation_id,
            workspace_id=workspace_id,
            snapshot_id=snapshot_id,
            draft_id=draft.id,
            metadata={"entry_point": "manual", "selection_count": len(staged_rows)},
        )
        self._audit(
            "snapshot_created",
            user,
            correlation_id,
            workspace_id=workspace_id,
            snapshot_id=snapshot_id,
            metadata={"checksum": snapshot_checksum},
        )
        self._audit(
            "draft_created",
            user,
            correlation_id,
            workspace_id=workspace_id,
            snapshot_id=snapshot_id,
            draft_id=draft.id,
        )
        self.db.commit()
        return self.workspace_shape(workspace_id, user)

    async def create_source_workspace(
        self,
        *,
        name: str,
        source_currency: str | None,
        source_unit: str | None,
        user: FlowHubUser,
        correlation_id: str,
    ) -> dict[str, Any]:
        self._seed_channels()
        preview = await WorkspacePriceWorkflowService(self.db).preview_from_nextcloud(user)
        global_profile = self._global_currency_profile()
        currency_profile = (
            self._source_currency_profile("nextcloud:primary", source_currency, source_unit)
            if source_currency or source_unit
            else global_profile
        )
        workspace_id = _id()
        snapshot_id = _id()
        workspace = UnifiedWorkspace(
            id=workspace_id,
            name=canonical_text(name) or "Source Workspace",
            entry_point=EntryPoint.SOURCE,
            source_type="nextcloud_excel",
            owner_user_id=user.id,
            status="active",
            version=1,
        )
        self.db.add(workspace)
        staged_rows: list[SnapshotRow] = []
        immutable_rows: list[dict[str, Any]] = []
        preview_rows_data = [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
            for item in preview.rows
        ]
        matched_identities = {
            ("woocommerce:primary", str(matched.get("productId")))
            for row_data in preview_rows_data
            if isinstance(
                (matched := row_data.get("matchedProduct") or row_data.get("matched_product")), dict
            )
            and matched.get("productId")
        }
        source_listing_map = (
            {
                (item.channel_id, item.external_primary_id): item
                for item in self.db.query(Listing)
                .filter(
                    tuple_(Listing.channel_id, Listing.external_primary_id).in_(matched_identities)
                )
                .all()
            }
            if matched_identities
            else {}
        )
        source_canonical_ids = {item.canonical_product_id for item in source_listing_map.values()}
        source_canonical_map = (
            {
                item.id: item
                for item in self.db.query(CanonicalProduct)
                .filter(CanonicalProduct.id.in_(source_canonical_ids))
                .all()
            }
            if source_canonical_ids
            else {}
        )
        source_listing_ids = {item.id for item in source_listing_map.values()}
        source_cache_map = (
            {
                item.listing_id: item
                for item in self.db.query(ChannelCache)
                .filter(ChannelCache.listing_id.in_(source_listing_ids))
                .all()
            }
            if source_listing_ids
            else {}
        )
        source_channel_map = {
            item.id: item
            for item in self.db.query(WorkspaceChannel)
            .filter(WorkspaceChannel.id == "woocommerce:primary")
            .all()
        }
        source_products: dict[str, DlProductCache] = (
            {
                str(item.product_id): item
                for item in self.db.query(DlProductCache)
                .filter(
                    DlProductCache.connector_id == "woocommerce:primary",
                    DlProductCache.product_id.in_({identity[1] for identity in matched_identities}),
                )
                .all()
            }
            if matched_identities
            else {}
        )
        for number, row_data in enumerate(preview_rows_data, start=1):
            matched = row_data.get("matchedProduct") or row_data.get("matched_product")
            canonical_id = None
            listing_id = None
            mapping_version = None
            if isinstance(matched, dict) and matched.get("productId"):
                cache_row = source_products.get(str(matched["productId"]))
                if cache_row is not None:
                    canonical, listing, _ = self._materialize_cache_identity(
                        cache_row,
                        listing_map=source_listing_map,
                        canonical_map=source_canonical_map,
                        cache_map=source_cache_map,
                        channel_map=source_channel_map,
                    )
                    canonical_id, listing_id, mapping_version = (
                        canonical.id,
                        listing.id,
                        listing.mapping_version,
                    )
            normalized = {
                "source": row_data.get("source") or {},
                "canonical_product_id": canonical_id,
                "listing_id": listing_id,
                "proposed_price": row_data.get("proposedPrice"),
                "source_stock": row_data.get("sourceStock"),
                "errors": row_data.get("errors") or [],
                "warnings": row_data.get("warnings") or [],
            }
            immutable_rows.append(normalized)
            staged_rows.append(
                SnapshotRow(
                    id=_id(),
                    snapshot_id=snapshot_id,
                    row_number=number,
                    canonical_product_id=canonical_id,
                    listing_id=listing_id,
                    mapping_version=mapping_version,
                    raw_data_json=row_data.get("source") or {},
                    normalized_data_json=normalized,
                    row_checksum=checksum(normalized),
                )
            )
        snapshot_checksum = checksum({"legacy_preview_id": preview.id, "rows": immutable_rows})
        snapshot = WorkspaceSnapshot(
            id=snapshot_id,
            workspace_id=workspace_id,
            entry_point=EntryPoint.SOURCE,
            source_type="nextcloud_excel",
            creator_user_id=user.id,
            schema_version=SCHEMA_VERSION,
            content_checksum=snapshot_checksum,
            normalization_version=NORMALIZATION_VERSION,
            validation_ruleset_version=VALIDATION_VERSION,
            mapping_version=max((row.mapping_version or 1 for row in staged_rows), default=1),
            currency_profile_id=currency_profile.id,
            source_metadata_json={
                "source_id": preview.sourceId,
                "source_name": preview.sourceName,
                "legacy_preview_id": preview.id,
            },
            acquisition_metadata_json={
                "read_once": True,
                "acquired_at": str(preview.startedAt),
            },
        )
        draft = Draft(
            id=_id(),
            workspace_id=workspace_id,
            snapshot_id=snapshot_id,
            owner_user_id=user.id,
            version=0,
            status="draft",
        )
        self.db.add_all([snapshot, *staged_rows, draft])
        self._audit(
            "workspace_created",
            user,
            correlation_id,
            workspace_id=workspace_id,
            snapshot_id=snapshot_id,
            draft_id=draft.id,
            metadata={"entry_point": "source", "legacy_preview_id": preview.id},
        )
        self._audit(
            "snapshot_created",
            user,
            correlation_id,
            workspace_id=workspace_id,
            snapshot_id=snapshot_id,
            metadata={"checksum": snapshot_checksum, "read_once": True},
        )
        self.db.commit()
        return self.workspace_shape(workspace_id, user)

    def workspace_shape(self, workspace_id: str, user: FlowHubUser) -> dict[str, Any]:
        workspace = self._workspace_for_user(workspace_id, user)
        snapshot = self.workspaces.snapshot(workspace.id)
        draft = self.drafts.for_workspace(workspace.id)
        if snapshot is None or draft is None:
            raise self._conflict("WORKSPACE_INCOMPLETE", "Workspace persistence is incomplete.")
        return {
            "id": workspace.id,
            "name": workspace.name,
            "entryPoint": workspace.entry_point,
            "sourceType": workspace.source_type,
            "ownerUserId": workspace.owner_user_id,
            "status": workspace.status,
            "version": workspace.version,
            "snapshot": {
                "id": snapshot.id,
                "checksum": snapshot.content_checksum,
                "schemaVersion": snapshot.schema_version,
                "createdAt": snapshot.created_at,
            },
            "draft": {
                "id": draft.id,
                "version": draft.version,
                "currentRevisionId": draft.current_revision_id,
                "status": draft.status,
            },
            "createdAt": workspace.created_at,
        }

    def grid(
        self,
        workspace_id: str,
        user: FlowHubUser,
        *,
        page: int,
        page_size: int,
        search: str | None,
        product_type: str | None,
        mapping_state: str | None,
        category: str | None,
        brand: str | None,
        channel_id: str | None,
        sku: str | None,
        listing_id: str | None,
        channel_status: str | None,
        min_price: float | None,
        max_price: float | None,
        stock_quantity: float | None,
        sorts: list[tuple[str, str]],
    ) -> dict[str, Any]:
        workspace = self._workspace_for_user(workspace_id, user)
        snapshot = self.workspaces.snapshot(workspace.id)
        draft = self.drafts.for_workspace(workspace.id)
        if snapshot is None or draft is None:
            raise self._conflict("WORKSPACE_INCOMPLETE", "Workspace persistence is incomplete.")
        page_size = min(max(page_size, 1), 500)
        rows, total = self.workspaces.grid_rows(
            snapshot.id,
            page=max(page, 1),
            page_size=page_size,
            search=search,
            product_type=product_type,
            mapping_state=mapping_state,
            category=category,
            brand=brand,
            channel_id=channel_id,
            sku=sku,
            listing_id=listing_id,
            channel_status=channel_status,
            min_price=min_price,
            max_price=max_price,
            stock_quantity=stock_quantity,
            sorts=sorts,
        )
        current_changes = (
            {
                (change.listing_id, change.field): change
                for change in self.drafts.changes(draft.current_revision_id)
            }
            if draft.current_revision_id
            else {}
        )
        preference = self.preferences.for_user(user.id)
        display_source = preference.display_name_source if preference else "canonical"
        display_names: dict[str, str] = {}
        if display_source != "canonical":
            product_ids = [product.id for _, product, _, _ in rows if product is not None]
            source_listings = (
                self.db.query(Listing)
                .filter(
                    Listing.canonical_product_id.in_(product_ids),
                    Listing.channel_id == display_source,
                    Listing.enabled.is_(True),
                )
                .order_by(Listing.canonical_product_id, Listing.id)
                .all()
            )
            for source_listing in source_listings:
                display_names.setdefault(source_listing.canonical_product_id, source_listing.label)
        row_listing_ids = [listing.id for _, _, listing, _ in rows if listing is not None]
        apply_statuses: dict[tuple[str, str], str] = {}
        if row_listing_ids:
            latest_items = (
                self.db.query(ApplyJobItem)
                .join(ApplyJob, ApplyJob.id == ApplyJobItem.apply_job_id)
                .filter(
                    ApplyJob.workspace_id == workspace.id,
                    ApplyJobItem.listing_id.in_(row_listing_ids),
                )
                .order_by(ApplyJobItem.completed_at.desc(), ApplyJobItem.id.desc())
                .all()
            )
            for item in latest_items:
                apply_statuses.setdefault((item.listing_id, item.field), item.status)
        latest_review = None
        if draft.current_revision_id:
            latest_review = (
                self.db.query(Review)
                .filter_by(workspace_id=workspace.id, draft_revision_id=draft.current_revision_id)
                .order_by(Review.created_at.desc(), Review.id.desc())
                .first()
            )
        items = []
        for snapshot_row, product, listing, cache in rows:
            if product is None or listing is None:
                items.append(
                    {
                        "rowId": snapshot_row.id,
                        "unresolved": True,
                        "validation": snapshot_row.normalized_data_json,
                    }
                )
                continue
            capabilities = self._capabilities(listing.channel_id)
            fields: dict[str, dict[str, Any]] = {}
            current_values = {
                "price": cache.price_raw if cache else None,
                "stock": str(cache.stock_quantity)
                if cache and cache.stock_quantity is not None
                else None,
                "status": cache.status if cache else None,
            }
            for field, current in current_values.items():
                saved = current_changes.get((listing.id, field))
                writable = (
                    product.product_type != ProductKind.VARIABLE
                    and capabilities.can_write(field)
                    and listing.mapping_state == MappingState.RESOLVED
                )
                persisted_status = apply_statuses.get((listing.id, field))
                cell_status = (
                    "stale_review"
                    if saved and latest_review and latest_review.status == ReviewState.STALE
                    else "applied"
                    if persisted_status == "applied"
                    else "failed"
                    if persisted_status == "failed"
                    else "draft_saved"
                    if saved
                    else "unchanged"
                    if writable
                    else "read_only"
                    if current is not None
                    else "unavailable"
                )
                fields[field] = {
                    "current": current,
                    "target": saved.target_value if saved else current,
                    "status": cell_status,
                    "readOnly": not writable,
                    "currency": saved.currency
                    if saved
                    else cache.price_currency
                    if cache and field == "price"
                    else None,
                    "unit": saved.unit
                    if saved
                    else cache.price_unit
                    if cache and field == "price"
                    else None,
                }
            items.append(
                {
                    "rowId": snapshot_row.id,
                    "canonicalProductId": product.id,
                    "canonicalName": product.name,
                    "displayName": display_names.get(product.id, product.name),
                    "displayNameSource": display_source,
                    "productType": product.product_type,
                    "parentProductId": product.parent_id,
                    "listingId": listing.id,
                    "listingLabel": listing.label,
                    "channelId": listing.channel_id,
                    "externalPrimaryId": listing.external_primary_id,
                    "externalIdType": listing.external_id_type,
                    "sku": listing.sku,
                    "mappingState": listing.mapping_state,
                    "mappingVersion": listing.mapping_version,
                    "cacheVersion": cache.cache_version if cache else None,
                    "cacheFreshness": cache.freshness if cache else "missing",
                    "fields": fields,
                }
            )
        channels = [
            self._channel_shape(connector.capabilities())
            for connector in self.connectors.implemented()
        ]
        return {
            "items": items,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "channels": channels,
            "draftVersion": draft.version,
            "revisionId": draft.current_revision_id,
        }

    # -- Draft revisions ------------------------------------------------------

    def save_draft(
        self,
        workspace_id: str,
        *,
        expected_version: int,
        raw_changes: list[dict[str, Any]],
        metadata: dict[str, Any],
        user: FlowHubUser,
        correlation_id: str,
    ) -> dict[str, Any]:
        workspace = self._workspace_for_user(workspace_id, user, edit=True)
        draft = self.drafts.for_workspace(workspace.id)
        snapshot = self.workspaces.snapshot(workspace.id)
        if draft is None or snapshot is None:
            raise self._conflict("WORKSPACE_INCOMPLETE", "Workspace persistence is incomplete.")
        if draft.version != expected_version:
            raise self._conflict(
                "DRAFT_VERSION_CONFLICT",
                "Draft was saved from an obsolete version.",
                {"expected": expected_version, "actual": draft.version},
            )
        if len(raw_changes) > MAX_DRAFT_CHANGES:
            raise self._unprocessable(
                "DRAFT_BATCH_LIMIT", f"Draft changes are limited to {MAX_DRAFT_CHANGES} cells."
            )
        incoming = [DraftChange(**item) for item in raw_changes]
        unique_keys = {(item.listing_id, item.field) for item in incoming}
        if len(unique_keys) != len(incoming):
            raise self._unprocessable(
                "DUPLICATE_DRAFT_CHANGE", "A Listing field may appear only once per revision."
            )
        merged: dict[tuple[str, str], DraftChange] = {}
        if draft.current_revision_id:
            for item in self.drafts.changes(draft.current_revision_id):
                merged[(item.listing_id, item.field)] = DraftChange(
                    canonical_product_id=item.canonical_product_id,
                    listing_id=item.listing_id,
                    channel_id=item.channel_id,
                    field=item.field,
                    target_value=item.target_value,
                    currency=item.currency,
                    unit=item.unit,
                )
        incoming_listing_ids = {item.listing_id for item in incoming}
        incoming_caches = (
            {
                item.listing_id: item
                for item in self.db.query(ChannelCache)
                .filter(ChannelCache.listing_id.in_(incoming_listing_ids))
                .all()
            }
            if incoming_listing_ids
            else {}
        )
        for change in incoming:
            cache = incoming_caches.get(change.listing_id)
            current_value = self._current_value(cache, change.field) if cache else None
            if values_equal(change.field, current_value, change.target_value):
                merged.pop((change.listing_id, change.field), None)
            else:
                merged[(change.listing_id, change.field)] = change
        changes = [merged[key] for key in sorted(merged)]
        change_listing_ids = {item.listing_id for item in changes}
        change_product_ids = {item.canonical_product_id for item in changes}
        change_listings = (
            {
                item.id: item
                for item in self.db.query(Listing).filter(Listing.id.in_(change_listing_ids)).all()
            }
            if change_listing_ids
            else {}
        )
        change_products = (
            {
                item.id: item
                for item in self.db.query(CanonicalProduct)
                .filter(CanonicalProduct.id.in_(change_product_ids))
                .all()
            }
            if change_product_ids
            else {}
        )
        snapshot_listing_ids = (
            {
                item[0]
                for item in self.db.query(SnapshotRow.listing_id)
                .filter(
                    SnapshotRow.snapshot_id == snapshot.id,
                    SnapshotRow.listing_id.in_(change_listing_ids),
                )
                .all()
            }
            if change_listing_ids
            else set()
        )
        for change in changes:
            listing = change_listings.get(change.listing_id)
            product = change_products.get(change.canonical_product_id)
            if (
                listing is None
                or product is None
                or listing.canonical_product_id != product.id
                or listing.channel_id != change.channel_id
            ):
                raise self._unprocessable(
                    "DRAFT_IDENTITY_INVALID",
                    "Draft change identity does not match the persisted Listing.",
                )
            if listing.id not in snapshot_listing_ids:
                raise self._unprocessable(
                    "DRAFT_OUTSIDE_SNAPSHOT",
                    "Draft change Listing is not in the immutable Snapshot.",
                )
            validate_product_editable(product.product_type)
            if listing.mapping_state != MappingState.RESOLVED:
                raise self._unprocessable(
                    "MAPPING_UNRESOLVED", "Only resolved Listings may be edited."
                )
            capabilities = self._capabilities(listing.channel_id)
            if not capabilities.can_write(change.field):
                raise self._unprocessable(
                    "FIELD_READ_ONLY", f"{change.field} is read-only for {listing.channel_id}."
                )
            if change.field == "price" and (
                change.currency != capabilities.currency
                or str(change.unit).upper() != capabilities.unit.upper()
            ):
                raise self._unprocessable(
                    "CURRENCY_UNIT_INVALID",
                    f"Expected {capabilities.currency}/{capabilities.unit} for {listing.channel_id}.",
                )
            if (
                change.field == "status"
                and change.target_value not in capabilities.supported_statuses
            ):
                raise self._unprocessable(
                    "STATUS_UNSUPPORTED", "Target status is not supported by the Channel."
                )
        revision_checksum = deterministic_revision_checksum(changes, metadata)
        if draft.current_revision_id:
            current = self.drafts.revision(draft.current_revision_id)
            if current and current.checksum == revision_checksum:
                return {
                    **self._revision_shape(current),
                    "noOp": True,
                    "draftVersion": draft.version,
                }
        revision = DraftRevision(
            id=_id(),
            draft_id=draft.id,
            workspace_id=workspace.id,
            snapshot_id=snapshot.id,
            revision_number=draft.version + 1,
            parent_revision_id=draft.current_revision_id,
            restored_from_revision_id=None,
            creator_user_id=user.id,
            checksum=revision_checksum,
            metadata_json=dict(metadata),
        )
        self.db.add(revision)
        for change in changes:
            payload = change.as_dict()
            self.db.add(
                DraftRevisionChange(
                    id=_id(),
                    revision_id=revision.id,
                    canonical_product_id=change.canonical_product_id,
                    listing_id=change.listing_id,
                    channel_id=change.channel_id,
                    field=change.field,
                    target_value=canonical_text(change.target_value),
                    currency=change.currency,
                    unit=change.unit,
                    change_checksum=checksum(payload),
                )
            )
        draft.current_revision_id = revision.id
        draft.version += 1
        draft.updated_at = utcnow()
        self._audit(
            "draft_revision_saved",
            user,
            correlation_id,
            workspace_id=workspace.id,
            snapshot_id=snapshot.id,
            draft_id=draft.id,
            draft_revision_id=revision.id,
            metadata={
                "revision_number": revision.revision_number,
                "checksum": revision.checksum,
                "change_count": len(changes),
            },
        )
        self.db.commit()
        return {**self._revision_shape(revision), "noOp": False, "draftVersion": draft.version}

    def revisions(
        self, workspace_id: str, user: FlowHubUser, *, page: int, page_size: int
    ) -> dict[str, Any]:
        workspace = self._workspace_for_user(workspace_id, user)
        draft = self.drafts.for_workspace(workspace.id)
        if draft is None:
            raise self._not_found("DRAFT_NOT_FOUND", "Draft not found.")
        items, total = self.drafts.revisions(
            draft.id, page=max(page, 1), page_size=min(max(page_size, 1), 100)
        )
        return {
            "items": [self._revision_shape(item) for item in items],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def restore_revision(
        self,
        workspace_id: str,
        revision_id: str,
        *,
        expected_version: int,
        user: FlowHubUser,
        correlation_id: str,
    ) -> dict[str, Any]:
        workspace = self._workspace_for_user(workspace_id, user, edit=True)
        draft = self.drafts.for_workspace(workspace.id)
        source = self.drafts.revision(revision_id)
        if draft is None or source is None or source.draft_id != draft.id:
            raise self._not_found("REVISION_NOT_FOUND", "Draft revision not found.")
        if draft.version != expected_version:
            raise self._conflict(
                "DRAFT_VERSION_CONFLICT", "Draft was restored from an obsolete version."
            )
        source_changes = self.drafts.changes(source.id)
        revision = DraftRevision(
            id=_id(),
            draft_id=draft.id,
            workspace_id=workspace.id,
            snapshot_id=source.snapshot_id,
            revision_number=draft.version + 1,
            parent_revision_id=draft.current_revision_id,
            restored_from_revision_id=source.id,
            creator_user_id=user.id,
            checksum=checksum(
                {
                    "restored_from": source.id,
                    "source_checksum": source.checksum,
                    "revision": draft.version + 1,
                }
            ),
            metadata_json={"restored_from_revision_id": source.id},
        )
        self.db.add(revision)
        for item in source_changes:
            self.db.add(
                DraftRevisionChange(
                    id=_id(),
                    revision_id=revision.id,
                    canonical_product_id=item.canonical_product_id,
                    listing_id=item.listing_id,
                    channel_id=item.channel_id,
                    field=item.field,
                    target_value=item.target_value,
                    currency=item.currency,
                    unit=item.unit,
                    change_checksum=checksum(
                        {"source_change": item.id, "target": item.target_value}
                    ),
                )
            )
        draft.current_revision_id = revision.id
        draft.version += 1
        draft.updated_at = utcnow()
        self._audit(
            "draft_revision_restored",
            user,
            correlation_id,
            workspace_id=workspace.id,
            snapshot_id=source.snapshot_id,
            draft_id=draft.id,
            draft_revision_id=revision.id,
            metadata={"restored_from": source.id},
        )
        self.db.commit()
        return {**self._revision_shape(revision), "draftVersion": draft.version}

    # -- Review ---------------------------------------------------------------

    def generate_review(
        self, workspace_id: str, revision_id: str, user: FlowHubUser, correlation_id: str
    ) -> dict[str, Any]:
        workspace = self._workspace_for_user(workspace_id, user, edit=True)
        snapshot = self.workspaces.snapshot(workspace.id)
        revision = self.drafts.revision(revision_id)
        if (
            snapshot is None
            or revision is None
            or revision.workspace_id != workspace.id
            or revision.snapshot_id != snapshot.id
        ):
            raise self._unprocessable(
                "REVIEW_INPUT_INVALID",
                "Review must reference this Workspace Snapshot and Draft Revision.",
            )
        changes = self.drafts.changes(revision.id)
        if not changes:
            raise self._unprocessable(
                "REVIEW_EMPTY", "Review requires at least one saved Draft change."
            )
        review_listing_ids = {item.listing_id for item in changes}
        review_product_ids = {item.canonical_product_id for item in changes}
        review_listings = {
            item.id: item
            for item in self.db.query(Listing).filter(Listing.id.in_(review_listing_ids)).all()
        }
        review_products = {
            item.id: item
            for item in self.db.query(CanonicalProduct)
            .filter(CanonicalProduct.id.in_(review_product_ids))
            .all()
        }
        review_caches = {
            item.listing_id: item
            for item in self.db.query(ChannelCache)
            .filter(ChannelCache.listing_id.in_(review_listing_ids))
            .all()
        }
        mapping_payload: list[dict[str, Any]] = []
        capability_payload: list[dict[str, Any]] = []
        currency_payload: list[dict[str, Any]] = []
        cache_payload: list[dict[str, Any]] = []
        prepared: list[dict[str, Any]] = []
        blocking = 0
        warnings = 0
        for change in changes:
            listing = review_listings.get(change.listing_id)
            product = review_products.get(change.canonical_product_id)
            cache = review_caches.get(change.listing_id)
            capabilities = self._capabilities(change.channel_id)
            errors: list[str] = []
            item_warnings: list[str] = []
            if listing is None or product is None or cache is None:
                errors.append("listing_or_cache_unavailable")
            else:
                if listing.mapping_state != MappingState.RESOLVED:
                    errors.append("mapping_unresolved")
                if cache.freshness != "fresh" or cache.fetch_status != "success":
                    errors.append("channel_cache_not_fresh")
                try:
                    validate_product_editable(product.product_type)
                except WorkspaceDomainError:
                    errors.append("variable_parent_read_only")
                if not capabilities.can_write(change.field):
                    errors.append("field_capability_unavailable")
                if change.field == "price":
                    if (
                        change.currency != capabilities.currency
                        or str(change.unit).upper() != capabilities.unit.upper()
                    ):
                        errors.append("currency_unit_invalid")
                    else:
                        self._money(change.target_value, capabilities)
                if (
                    change.field == "stock"
                    and cache.manage_stock is False
                    and capabilities.requires_stock_management
                ):
                    errors.append("stock_management_disabled")
            current = self._current_value(cache, change.field) if cache else None
            unchanged = values_equal(change.field, current, change.target_value)
            eligible = not errors and not unchanged
            if errors:
                blocking += 1
            if item_warnings:
                warnings += 1
            normalized = self._normalized_target(change, capabilities) if not errors else {}
            prepared.append(
                {
                    "change": change,
                    "listing": listing,
                    "cache": cache,
                    "capabilities": capabilities,
                    "current": current,
                    "errors": errors,
                    "warnings": item_warnings,
                    "eligible": eligible,
                    "normalized": normalized,
                }
            )
            if listing:
                mapping_payload.append(
                    {
                        "listing": listing.id,
                        "version": listing.mapping_version,
                        "state": listing.mapping_state,
                    }
                )
            capability_payload.append(
                {"channel": capabilities.channel_id, "version": capabilities.version}
            )
            currency_payload.append(
                {
                    "channel": capabilities.channel_id,
                    "currency": capabilities.currency,
                    "unit": capabilities.unit,
                }
            )
            if cache:
                cache_payload.append(
                    {
                        "listing": cache.listing_id,
                        "version": cache.cache_version,
                        "checksum": cache.checksum,
                    }
                )
        mapping_payload = _unique_dicts(mapping_payload)
        capability_payload = _unique_dicts(capability_payload)
        currency_payload = _unique_dicts(currency_payload)
        mapping_digest = checksum(mapping_payload)
        capability_digest = checksum(capability_payload)
        currency_digest = checksum(currency_payload)
        currency_profile = self.db.get(CurrencyProfile, snapshot.currency_profile_id)
        if currency_profile is None:
            raise self._conflict(
                "CURRENCY_PROFILE_MISSING",
                "Snapshot Currency Profile is unavailable.",
            )
        channel_currency_references = sorted(
            f"{item['channel']}:{item['currency']}:{item['unit']}" for item in currency_payload
        )
        review_checksum = checksum(
            {
                "snapshot": snapshot.content_checksum,
                "revision": revision.checksum,
                "mapping": mapping_digest,
                "capability": capability_digest,
                "currency": currency_digest,
                "currency_profile": currency_profile.id,
                "currency_profile_version": currency_profile.version,
                "currency_profile_checksum": currency_profile.checksum,
                "currency_ruleset": CURRENCY_RULESET_VERSION,
                "cache": cache_payload,
                "ruleset": VALIDATION_VERSION,
            }
        )
        review = Review(
            id=_id(),
            workspace_id=workspace.id,
            snapshot_id=snapshot.id,
            draft_revision_id=revision.id,
            created_by_user_id=user.id,
            status=ReviewState.BLOCKED if blocking else ReviewState.READY,
            ruleset_version=VALIDATION_VERSION,
            capability_digest=capability_digest,
            currency_digest=currency_digest,
            currency_profile_id=currency_profile.id,
            currency_profile_version=currency_profile.version,
            currency_profile_checksum=currency_profile.checksum,
            currency_source_reference=(
                f"{currency_profile.scope}:{currency_profile.scope_reference}"
            ),
            currency_channel_references_json=channel_currency_references,
            currency_ruleset_version=CURRENCY_RULESET_VERSION,
            mapping_digest=mapping_digest,
            checksum=review_checksum,
            summary_json={
                "total": len(prepared),
                "eligible": sum(1 for item in prepared if item["eligible"]),
                "blocked": blocking,
                "warnings": warnings,
            },
        )
        self.db.add(review)
        cache_seen: set[str] = set()
        for item in prepared:
            change = item["change"]
            review_item = ReviewItem(
                id=_id(),
                review_id=review.id,
                draft_change_id=change.id,
                canonical_product_id=change.canonical_product_id,
                listing_id=change.listing_id,
                channel_id=change.channel_id,
                field=change.field,
                current_value=item["current"],
                target_value=change.target_value,
                normalized_value_json=item["normalized"],
                payload_summary_json={"field": change.field, "target": change.target_value},
                validation_state="error"
                if item["errors"]
                else "unchanged"
                if not item["eligible"]
                else "ready",
                warnings_json=item["warnings"],
                errors_json=item["errors"],
                eligible=item["eligible"],
                selected=False,
            )
            self.db.add(review_item)
            for error in item["errors"]:
                self.db.add(
                    ValidationIssue(
                        id=_id(),
                        workspace_id=workspace.id,
                        snapshot_id=snapshot.id,
                        review_id=review.id,
                        canonical_product_id=change.canonical_product_id,
                        listing_id=change.listing_id,
                        channel_id=change.channel_id,
                        code=error,
                        severity="error",
                        message=error.replace("_", " "),
                        metadata_json={"field": change.field},
                    )
                )
            cache = item["cache"]
            listing = item["listing"]
            capabilities = item["capabilities"]
            if cache and listing and listing.id not in cache_seen:
                cache_seen.add(listing.id)
                self.db.add(
                    ReviewCacheVersion(
                        id=_id(),
                        review_id=review.id,
                        listing_id=listing.id,
                        channel_id=listing.channel_id,
                        cache_version=cache.cache_version,
                        cache_checksum=cache.checksum,
                        mapping_version=listing.mapping_version,
                        capability_version=capabilities.version,
                    )
                )
        self._audit(
            "review_generated",
            user,
            correlation_id,
            workspace_id=workspace.id,
            snapshot_id=snapshot.id,
            draft_revision_id=revision.id,
            review_id=review.id,
            review_result=review.status,
            metadata={"checksum": review.checksum, **review.summary_json},
        )
        self.db.commit()
        return self.review_shape(review.id, user)

    def select_review_items(
        self,
        workspace_id: str,
        review_id: str,
        item_ids: list[str],
        user: FlowHubUser,
        correlation_id: str,
    ) -> dict[str, Any]:
        workspace = self._workspace_for_user(workspace_id, user, edit=True)
        review = self.reviews.get(review_id)
        if review is None or review.workspace_id != workspace.id:
            raise self._not_found("REVIEW_NOT_FOUND", "Review not found.")
        if review.status != ReviewState.READY:
            raise self._conflict(
                "REVIEW_NOT_READY", "Only a ready Review may receive Apply selection."
            )
        unique_ids = sorted(set(item_ids))
        if not unique_ids or len(unique_ids) != len(item_ids):
            raise self._unprocessable(
                "REVIEW_SELECTION_INVALID", "Select one or more unique Review items."
            )
        items = (
            self.db.query(ReviewItem)
            .filter(ReviewItem.review_id == review.id, ReviewItem.id.in_(unique_ids))
            .all()
        )
        if len(items) != len(unique_ids) or any(not item.eligible for item in items):
            raise self._unprocessable(
                "REVIEW_SELECTION_INELIGIBLE",
                "Selection contains missing or ineligible Review items.",
            )
        selected_channel_ids = sorted({item.channel_id for item in items})
        preference = self.preferences.for_user(user.id)
        visible_channel_ids = set(
            preference.visible_channel_ids_json
            if preference is not None
            else ["woocommerce:primary", "snappshop:main"]
        )
        if not set(selected_channel_ids).issubset(visible_channel_ids):
            raise self._conflict(
                "SELECTION_CHANGED",
                "Hidden Channels cannot participate in Apply selection.",
            )
        self.db.query(ReviewSelection).filter_by(review_id=review.id).delete(
            synchronize_session=False
        )
        for item_id in unique_ids:
            self.db.add(
                ReviewSelection(
                    id=_id(),
                    review_id=review.id,
                    review_item_id=item_id,
                    selected_by_user_id=user.id,
                )
            )
        review.selection_version += 1
        review.selected_channel_ids_json = selected_channel_ids
        selection_document = self._selection_document(review, items)
        selection_checksum = checksum(selection_document)
        review.selection_checksum = selection_checksum
        self._audit(
            "review_selection_saved",
            user,
            correlation_id,
            workspace_id=workspace.id,
            snapshot_id=review.snapshot_id,
            draft_revision_id=review.draft_revision_id,
            review_id=review.id,
            metadata={
                "selected_count": len(unique_ids),
                "selection_checksum": selection_checksum,
                "selection_version": review.selection_version,
                "canonical_selection": selection_document,
            },
        )
        self.db.commit()
        return {
            "reviewId": review.id,
            "selectedItemIds": unique_ids,
            "selectionChecksum": selection_checksum,
            "selectionVersion": review.selection_version,
        }

    def review_shape(self, review_id: str, user: FlowHubUser) -> dict[str, Any]:
        review = self.reviews.get(review_id)
        if review is None:
            raise self._not_found("REVIEW_NOT_FOUND", "Review not found.")
        self._workspace_for_user(review.workspace_id, user)
        selections = {item.review_item_id for item in self.reviews.selections(review.id)}
        return {
            "id": review.id,
            "workspaceId": review.workspace_id,
            "snapshotId": review.snapshot_id,
            "draftRevisionId": review.draft_revision_id,
            "status": review.status,
            "checksum": review.checksum,
            "summary": review.summary_json,
            "createdAt": review.created_at,
            "staleReason": review.stale_reason,
            "items": [
                {
                    "id": item.id,
                    "canonicalProductId": item.canonical_product_id,
                    "listingId": item.listing_id,
                    "channelId": item.channel_id,
                    "field": item.field,
                    "current": item.current_value,
                    "target": item.target_value,
                    "normalized": item.normalized_value_json,
                    "validationState": item.validation_state,
                    "warnings": item.warnings_json,
                    "errors": item.errors_json,
                    "eligible": item.eligible,
                    "selected": item.id in selections,
                }
                for item in self.reviews.items(review.id)
            ],
        }

    # -- Apply ----------------------------------------------------------------

    async def apply_selected(
        self,
        workspace_id: str,
        review_id: str,
        *,
        idempotency_key: str,
        expected_selection_checksum: str,
        confirmed: bool,
        user: FlowHubUser,
        correlation_id: str,
    ) -> dict[str, Any]:
        workspace = self._workspace_for_user(workspace_id, user, edit=True)
        if not has_workspace_permission(user, "apply.execute"):
            self._audit(
                "permission_denied",
                user,
                correlation_id,
                workspace_id=workspace.id,
                reason="apply.execute",
            )
            self.db.commit()
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                {"code": "WORKSPACE_PERMISSION_DENIED", "message": "Apply permission is required."},
            )
        if not confirmed:
            raise self._unprocessable(
                "APPLY_CONFIRMATION_REQUIRED", "Explicit Apply confirmation is required."
            )
        key = canonical_text(idempotency_key)
        if not key or len(key) > 255:
            raise self._unprocessable(
                "IDEMPOTENCY_KEY_INVALID", "A valid idempotency key is required."
            )
        existing = self.applies.by_idempotency(key)
        if existing:
            self._recover_job_if_stale(existing, user, correlation_id)
            return self.apply_shape(existing.id, user)
        review = self.reviews.get(review_id)
        if review is None or review.workspace_id != workspace.id:
            raise self._not_found("REVIEW_NOT_FOUND", "Review not found.")
        draft = self.drafts.for_workspace(workspace.id)
        snapshot = self.workspaces.snapshot(workspace.id)
        if (
            draft is None
            or snapshot is None
            or draft.current_revision_id != review.draft_revision_id
            or review.snapshot_id != snapshot.id
        ):
            raise self._conflict(
                "APPLY_REVISION_MISMATCH",
                "Apply Review does not match the current Draft Revision and Snapshot.",
            )
        selections = self.reviews.selections(review.id)
        selected_ids = sorted(item.review_item_id for item in selections)
        if not selected_ids:
            raise self._unprocessable(
                "APPLY_SELECTION_REQUIRED",
                "Apply selected only requires explicit Review selection.",
            )
        review_items = (
            self.db.query(ReviewItem)
            .filter(ReviewItem.review_id == review.id, ReviewItem.id.in_(selected_ids))
            .all()
        )
        if len(review_items) != len(selected_ids) or any(
            not item.eligible or item.errors_json for item in review_items
        ):
            raise self._unprocessable(
                "APPLY_SELECTION_INELIGIBLE", "Selected Review items are no longer eligible."
            )
        selected_channel_ids = sorted({item.channel_id for item in review_items})
        if selected_channel_ids != sorted(review.selected_channel_ids_json):
            raise self._conflict(
                "SELECTION_CHANGED",
                "The confirmed Channel scope changed; confirm selection again.",
            )
        selection_checksum = checksum(self._selection_document(review, review_items))
        expected_checksum = canonical_text(expected_selection_checksum)
        if (
            not expected_checksum
            or expected_checksum != selection_checksum
            or review.selection_checksum != selection_checksum
        ):
            raise self._conflict(
                "APPLY_SELECTION_CHECKSUM_MISMATCH",
                "The confirmed selection changed; confirm the current selection again.",
            )
        logical_operation_key = checksum(
            {
                "workspace": workspace.id,
                "snapshot": snapshot.id,
                "draft_revision": review.draft_revision_id,
                "review": review.id,
                "selection": selection_checksum,
                "operation_version": "workspace-apply-v2",
            }
        )
        existing = self.applies.by_logical_operation(logical_operation_key)
        if existing:
            self._recover_job_if_stale(existing, user, correlation_id)
            return self.apply_shape(existing.id, user)
        listing_rows = {
            row.id: row
            for row in self.db.query(Listing)
            .filter(Listing.id.in_({item.listing_id for item in review_items}))
            .all()
        }
        lock_scope = sorted(
            {(listing_rows[item.listing_id].channel_id, item.listing_id) for item in review_items}
        )
        job = ApplyJob(
            id=_id(),
            workspace_id=workspace.id,
            snapshot_id=snapshot.id,
            draft_revision_id=review.draft_revision_id,
            review_id=review.id,
            requested_by_user_id=user.id,
            idempotency_key=key,
            logical_operation_key=logical_operation_key,
            correlation_id=correlation_id,
            selection_checksum=selection_checksum,
            request_json={"selected_review_item_ids": selected_ids, "confirmed": True},
            status=ApplyState.PENDING,
            operation_checksum=logical_operation_key,
        )
        self.db.add(job)
        job_items: dict[str, ApplyJobItem] = {}
        for item in review_items:
            job_item = ApplyJobItem(
                id=_id(),
                apply_job_id=job.id,
                review_item_id=item.id,
                canonical_product_id=item.canonical_product_id,
                listing_id=item.listing_id,
                channel_id=item.channel_id,
                field=item.field,
                payload_hash=checksum(item.payload_summary_json),
                status="pending",
                attempt_number=0,
                retry_eligible=False,
                connector_response_json={},
            )
            job_items[item.id] = job_item
            self.db.add(job_item)
        self._audit(
            "apply_requested",
            user,
            correlation_id,
            workspace_id=workspace.id,
            snapshot_id=snapshot.id,
            draft_id=draft.id,
            draft_revision_id=review.draft_revision_id,
            review_id=review.id,
            apply_job_id=job.id,
            metadata={
                "selected_only": True,
                "selection_checksum": selection_checksum,
                "selected_count": len(selected_ids),
            },
        )
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.applies.by_idempotency(key)
            if existing:
                return self.apply_shape(existing.id, user)
            raise
        try:
            self._acquire_listing_locks(workspace.id, job.id, lock_scope)
        except Exception as exc:
            self.db.rollback()
            durable_job = self.db.get(ApplyJob, job.id)
            if durable_job is not None:
                durable_job.status = ApplyState.FAILED
                durable_job.completed_at = utcnow()
                self._audit(
                    "apply_lock_failed",
                    user,
                    correlation_id,
                    workspace_id=workspace.id,
                    snapshot_id=snapshot.id,
                    draft_revision_id=job.draft_revision_id,
                    review_id=job.review_id,
                    apply_job_id=job.id,
                    apply_result=ApplyState.FAILED,
                    reason=canonical_text(exc)[:1000],
                )
                self.db.commit()
            raise
        successful = 0
        failed = 0
        reconciliation = 0
        try:
            review = self.reviews.get(review.id)
            if review is None or review.status != ReviewState.READY:
                raise self._conflict("REVIEW_NOT_READY", "Apply requires a ready Review.")
            self._assert_review_fresh(review, user, correlation_id)
            current_selection = self.reviews.selections(review.id)
            current_ids = sorted(item.review_item_id for item in current_selection)
            if (
                current_ids != selected_ids
                or checksum(self._selection_document(review, review_items)) != expected_checksum
            ):
                raise self._conflict(
                    "APPLY_SELECTION_CHECKSUM_MISMATCH",
                    "The confirmed selection changed after lock acquisition.",
                )
            draft = self.drafts.for_workspace(workspace.id)
            if draft is None or draft.current_revision_id != review.draft_revision_id:
                raise self._conflict(
                    "APPLY_REVISION_MISMATCH", "Draft Revision changed before dispatch."
                )
            job.status = ApplyState.RUNNING
            job.started_at = utcnow()
            job.heartbeat_at = job.started_at
            job.worker_id = correlation_id
            self._audit(
                "apply_started",
                user,
                correlation_id,
                workspace_id=workspace.id,
                snapshot_id=snapshot.id,
                draft_revision_id=review.draft_revision_id,
                review_id=review.id,
                apply_job_id=job.id,
            )
            self.db.commit()
            grouped: dict[str, list[ReviewItem]] = defaultdict(list)
            for item in review_items:
                grouped[item.listing_id].append(item)
            intents = tuple(
                self._write_intent(job, listing_id, items, selection_checksum)
                for listing_id, items in sorted(grouped.items())
            )
            results = await WritePipelineService(self.db).execute_workspace(
                WorkspaceWriteBatchCommand(
                    workspace_id=workspace.id,
                    snapshot_id=snapshot.id,
                    draft_revision_id=job.draft_revision_id,
                    review_id=job.review_id,
                    selection_checksum=selection_checksum,
                    correlation_id=correlation_id,
                    requested_by=user.username,
                    intents=intents,
                ),
                user,
            )
            job.heartbeat_at = utcnow()
            for result in results:
                affected = grouped[result.listing_id]
                if result.outcome is WriteOutcome.VERIFIED_APPLIED:
                    successful += len(affected)
                    self._record_listing_success(job, result, affected, user)
                elif result.outcome is WriteOutcome.RECONCILIATION_REQUIRED:
                    reconciliation += len(affected)
                    self._record_listing_reconciliation(job, result, affected, user)
                else:
                    failed += len(affected)
                    self._record_listing_failure(job, result, affected, user)
            self.db.commit()
            job.completed_at = utcnow()
            job.status = (
                ApplyState.RECONCILIATION_REQUIRED
                if reconciliation
                else ApplyState.APPLIED
                if failed == 0
                else ApplyState.PARTIALLY_APPLIED
                if successful
                else ApplyState.FAILED
            )
            draft.status = "applied" if job.status == ApplyState.APPLIED else draft.status
            self._audit(
                "apply_completed",
                user,
                correlation_id,
                workspace_id=workspace.id,
                snapshot_id=snapshot.id,
                draft_id=draft.id,
                draft_revision_id=review.draft_revision_id,
                review_id=review.id,
                apply_job_id=job.id,
                apply_result=job.status,
                metadata={
                    "success_count": successful,
                    "failure_count": failed,
                    "reconciliation_count": reconciliation,
                },
            )
            if reconciliation == 0:
                self._release_listing_locks(job.id)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            durable_job = self.db.get(ApplyJob, job.id)
            if durable_job:
                dispatched = (
                    self.db.query(ProviderWriteAttemptEvent.id)
                    .join(
                        ProviderWriteAttempt,
                        ProviderWriteAttempt.id == ProviderWriteAttemptEvent.attempt_id,
                    )
                    .filter(
                        ProviderWriteAttempt.apply_job_id == job.id,
                        ProviderWriteAttemptEvent.outcome.in_(
                            [
                                WriteOutcome.DISPATCHED.value,
                                WriteOutcome.PROVIDER_ACCEPTED.value,
                                WriteOutcome.VERIFIED_APPLIED.value,
                                WriteOutcome.RECONCILIATION_REQUIRED.value,
                            ]
                        ),
                    )
                    .first()
                    is not None
                )
                durable_job.status = (
                    ApplyState.RECONCILIATION_REQUIRED if dispatched else ApplyState.FAILED
                )
                durable_job.completed_at = utcnow()
                if not dispatched:
                    self._release_listing_locks(job.id)
                self._audit(
                    "apply_reconciliation_required" if dispatched else "apply_pre_dispatch_failed",
                    user,
                    correlation_id,
                    workspace_id=workspace.id,
                    snapshot_id=snapshot.id,
                    draft_revision_id=job.draft_revision_id,
                    review_id=job.review_id,
                    apply_job_id=job.id,
                    apply_result=durable_job.status,
                    reason=canonical_text(exc)[:1000],
                )
                self.db.commit()
            raise
        return self.apply_shape(job.id, user)

    async def reconcile_apply(
        self,
        workspace_id: str,
        job_id: str,
        user: FlowHubUser,
        correlation_id: str,
    ) -> dict[str, Any]:
        workspace = self._workspace_for_user(workspace_id, user, edit=True)
        if not has_workspace_permission(user, "apply.execute"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Apply permission is required.")
        job = self.applies.get(job_id)
        if job is None or job.workspace_id != workspace.id:
            raise self._not_found("APPLY_NOT_FOUND", "Apply job not found.")
        self._recover_job_if_stale(job, user, correlation_id)
        if job.status not in {
            ApplyState.RECONCILIATION_REQUIRED,
        }:
            raise self._conflict(
                "APPLY_RECONCILIATION_NOT_REQUIRED",
                "Only an uncertain Apply may be reconciled.",
            )
        uncertain_job_items = (
            self.db.query(ApplyJobItem)
            .filter(
                ApplyJobItem.apply_job_id == job.id,
                ApplyJobItem.status.in_(
                    ["reconciliation_required", "dispatched", "provider_accepted", "recovering"]
                ),
            )
            .all()
        )
        uncertain_item_ids = [item.id for item in uncertain_job_items]
        if not uncertain_item_ids:
            raise self._conflict(
                "APPLY_RECONCILIATION_EMPTY",
                "No uncertain Apply items are eligible for reconciliation.",
            )
        review_items = (
            self.db.query(ReviewItem)
            .join(ApplyJobItem, ApplyJobItem.review_item_id == ReviewItem.id)
            .filter(ApplyJobItem.id.in_(uncertain_item_ids))
            .all()
        )
        grouped: dict[str, list[ReviewItem]] = defaultdict(list)
        for item in review_items:
            grouped[item.listing_id].append(item)
        intents = tuple(
            self._intent_from_immutable_attempt(job, listing_id) for listing_id in sorted(grouped)
        )
        job.heartbeat_at = utcnow()
        job.worker_id = correlation_id
        for uncertain_item in uncertain_job_items:
            uncertain_item.status = "recovering"
        self.db.commit()
        results = await WritePipelineService(self.db).execute_workspace(
            WorkspaceWriteBatchCommand(
                workspace_id=job.workspace_id,
                snapshot_id=job.snapshot_id,
                draft_revision_id=job.draft_revision_id,
                review_id=job.review_id,
                selection_checksum=job.selection_checksum,
                correlation_id=correlation_id,
                requested_by=user.username,
                intents=intents,
            ),
            user,
            reconcile_only=True,
        )
        unresolved = 0
        for result in results:
            affected = grouped[result.listing_id]
            if result.outcome is WriteOutcome.VERIFIED_APPLIED:
                self._record_listing_success(job, result, affected, user)
            else:
                unresolved += len(affected)
                self._record_listing_reconciliation(job, result, affected, user)
        job.status = self._apply_status_from_items(job.id)
        if job.status in {
            ApplyState.APPLIED,
            ApplyState.PARTIALLY_APPLIED,
            ApplyState.FAILED,
        }:
            job.completed_at = utcnow()
        if job.status == ApplyState.APPLIED:
            draft = self.drafts.for_workspace(job.workspace_id)
            if draft is not None:
                draft.status = "applied"
            self._release_listing_locks(job.id)
        self._audit(
            "apply_reconciled" if unresolved == 0 else "apply_reconciliation_pending",
            user,
            correlation_id,
            workspace_id=job.workspace_id,
            snapshot_id=job.snapshot_id,
            draft_revision_id=job.draft_revision_id,
            review_id=job.review_id,
            apply_job_id=job.id,
            apply_result=job.status,
            metadata={"unresolved_count": unresolved},
        )
        self.db.commit()
        return self.apply_shape(job.id, user)

    def recover_stale_applies(self, user: FlowHubUser, correlation_id: str) -> dict[str, Any]:
        if not has_workspace_permission(user, "apply.execute"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Apply permission is required.")
        cutoff = utcnow() - timedelta(minutes=STALE_APPLY_MINUTES)
        candidates = (
            self.db.query(ApplyJob)
            .filter(
                ApplyJob.status == ApplyState.RUNNING,
                ApplyJob.heartbeat_at.isnot(None),
                ApplyJob.heartbeat_at < cutoff,
            )
            .order_by(ApplyJob.id.asc())
            .with_for_update(skip_locked=True)
            .all()
        )
        recovered: list[str] = []
        for job in candidates:
            if self._recover_job_if_stale(job, user, correlation_id):
                recovered.append(job.id)
        self.db.commit()
        return {"recoveredJobIds": recovered, "count": len(recovered)}

    def apply_shape(self, job_id: str, user: FlowHubUser) -> dict[str, Any]:
        job = self.applies.get(job_id)
        if job is None:
            raise self._not_found("APPLY_NOT_FOUND", "Apply job not found.")
        self._workspace_for_user(job.workspace_id, user)
        return {
            "id": job.id,
            "workspaceId": job.workspace_id,
            "snapshotId": job.snapshot_id,
            "draftRevisionId": job.draft_revision_id,
            "reviewId": job.review_id,
            "status": job.status,
            "correlationId": job.correlation_id,
            "selectionChecksum": job.selection_checksum,
            "createdAt": job.created_at,
            "startedAt": job.started_at,
            "completedAt": job.completed_at,
            "items": [
                {
                    "id": item.id,
                    "reviewItemId": item.review_item_id,
                    "canonicalProductId": item.canonical_product_id,
                    "listingId": item.listing_id,
                    "channelId": item.channel_id,
                    "field": item.field,
                    "status": item.status,
                    "attemptNumber": item.attempt_number,
                    "retryEligible": item.retry_eligible,
                    "externalResponseId": item.external_response_id,
                    "errorCategory": item.error_category,
                    "errorMessage": item.error_message,
                    "cacheSyncStatus": item.cache_sync_status,
                }
                for item in self.applies.items(job.id)
            ],
        }

    # -- Preferences, audit, mapping ----------------------------------------

    def preference(self, user: FlowHubUser) -> dict[str, Any]:
        row = self.preferences.for_user(user.id)
        if row is None:
            return {
                "visibleChannelIds": ["woocommerce:primary", "snappshop:main"],
                "channelOrder": ["woocommerce:primary", "snappshop:main"],
                "visibleFields": {"price": True, "stock": True, "status": True, "sku": True},
                "displayNameSource": "canonical",
                "version": 0,
            }
        return self._preference_shape(row)

    def save_preference(
        self, payload: dict[str, Any], expected_version: int, user: FlowHubUser
    ) -> dict[str, Any]:
        allowed = {item.channel_id for item in self.connectors.implemented()}
        visible = [str(item) for item in payload.get("visibleChannelIds") or []]
        order = [str(item) for item in payload.get("channelOrder") or []]
        if (
            any(item not in allowed for item in visible + order)
            or len(visible) != len(set(visible))
            or len(order) != len(set(order))
        ):
            raise self._unprocessable(
                "PREFERENCE_CHANNEL_INVALID",
                "Preferences may include each implemented Channel once.",
            )
        display = str(payload.get("displayNameSource") or "canonical")
        if display not in {"canonical", *allowed}:
            raise self._unprocessable(
                "DISPLAY_NAME_SOURCE_INVALID", "Display name source is unavailable."
            )
        row = self.preferences.for_user(user.id)
        if row and row.version != expected_version:
            raise self._conflict(
                "PREFERENCE_VERSION_CONFLICT", "Preferences were updated concurrently."
            )
        if row is None:
            if expected_version != 0:
                raise self._conflict(
                    "PREFERENCE_VERSION_CONFLICT", "Preferences were updated concurrently."
                )
            row = UserWorkspacePreference(id=_id(), user_id=user.id, version=0)
            self.db.add(row)
        previously_visible = set(row.visible_channel_ids_json or [])
        hidden = previously_visible.difference(visible)
        row.visible_channel_ids_json = visible
        row.channel_order_json = order
        row.visible_fields_json = dict(payload.get("visibleFields") or {})
        row.display_name_source = display
        row.version += 1
        row.updated_at = utcnow()
        if hidden:
            affected_reviews = (
                self.db.query(Review)
                .join(ReviewSelection, ReviewSelection.review_id == Review.id)
                .join(ReviewItem, ReviewItem.id == ReviewSelection.review_item_id)
                .filter(
                    ReviewSelection.selected_by_user_id == user.id,
                    ReviewItem.channel_id.in_(hidden),
                )
                .distinct()
                .all()
            )
            for review in affected_reviews:
                self.db.query(ReviewSelection).filter(
                    ReviewSelection.review_id == review.id,
                    ReviewSelection.review_item_id.in_(
                        self.db.query(ReviewItem.id).filter(
                            ReviewItem.review_id == review.id,
                            ReviewItem.channel_id.in_(hidden),
                        )
                    ),
                ).delete(synchronize_session=False)
                remaining_items = (
                    self.db.query(ReviewItem)
                    .join(ReviewSelection, ReviewSelection.review_item_id == ReviewItem.id)
                    .filter(ReviewSelection.review_id == review.id)
                    .all()
                )
                review.selection_version += 1
                review.selection_checksum = None
                review.selected_channel_ids_json = sorted(
                    {item.channel_id for item in remaining_items}
                )
        self.db.commit()
        return self._preference_shape(row)

    def audit(
        self, workspace_id: str, user: FlowHubUser, *, page: int, page_size: int
    ) -> dict[str, Any]:
        self._workspace_for_user(workspace_id, user)
        items, total = self.audits.list(
            workspace_id, page=max(page, 1), page_size=min(max(page_size, 1), 200)
        )
        return {
            "items": [self._audit_shape(item) for item in items],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def approve_mapping(
        self,
        workspace_id: str,
        listing_id: str,
        proposed_product_id: str,
        decision: str,
        reason: str,
        evidence: dict[str, Any],
        user: FlowHubUser,
        correlation_id: str,
    ) -> dict[str, Any]:
        workspace = self._workspace_for_user(workspace_id, user, edit=True)
        if decision not in {"approved", "rejected"}:
            raise self._unprocessable(
                "MAPPING_DECISION_INVALID", "Mapping decision must be approved or rejected."
            )
        listing = self.db.query(Listing).filter_by(id=listing_id).with_for_update().first()
        product = self.db.get(CanonicalProduct, proposed_product_id)
        snapshot = self.workspaces.snapshot(workspace.id)
        if (
            listing is None
            or product is None
            or snapshot is None
            or not self.db.query(SnapshotRow)
            .filter_by(snapshot_id=snapshot.id, listing_id=listing.id)
            .first()
        ):
            raise self._not_found(
                "MAPPING_NOT_FOUND", "Workspace Listing or proposed Canonical Product not found."
            )
        try:
            listing = acquire_listing_guard(self.db, listing.channel_id, listing.id)
        except ListingGuardConflict as exc:
            self.db.rollback()
            raise self._conflict(
                "LISTING_MUTATION_LOCKED",
                "Listing Mapping cannot change during Apply.",
                {"listingId": listing_id},
            ) from exc
        revision_number = listing.mapping_version + 1
        revision = MappingRevision(
            id=_id(),
            listing_id=listing.id,
            revision_number=revision_number,
            previous_canonical_product_id=listing.canonical_product_id,
            proposed_canonical_product_id=product.id,
            decision=decision,
            evidence_json=dict(evidence),
            reason=canonical_text(reason),
            approved_by_user_id=user.id,
            checksum=checksum(
                {
                    "listing": listing.id,
                    "revision": revision_number,
                    "previous": listing.canonical_product_id,
                    "proposed": product.id,
                    "decision": decision,
                    "evidence": evidence,
                    "reason": reason,
                }
            ),
        )
        self.db.add(revision)
        if decision == "approved":
            listing.canonical_product_id = product.id
            listing.mapping_state = MappingState.RESOLVED
            listing.mapping_version = revision_number
            listing.updated_at = utcnow()
        self._audit(
            f"mapping_{decision}",
            user,
            correlation_id,
            workspace_id=workspace.id,
            snapshot_id=snapshot.id,
            canonical_product_id=product.id,
            listing_id=listing.id,
            channel_id=listing.channel_id,
            reason=reason,
            metadata={"mapping_revision_id": revision.id, "evidence": evidence},
        )
        self.db.commit()
        return {
            "listingId": listing.id,
            "canonicalProductId": listing.canonical_product_id,
            "mappingState": listing.mapping_state,
            "mappingVersion": listing.mapping_version,
            "revisionId": revision.id,
            "decision": decision,
        }

    async def refresh_channel_cache(
        self, channel_id: str, user: FlowHubUser, correlation_id: str
    ) -> dict[str, Any]:
        self._seed_channels()
        channel = self.db.get(WorkspaceChannel, channel_id)
        if channel is None or channel.implementation_state != "implemented":
            raise self._unprocessable(
                "CHANNEL_NOT_IMPLEMENTED", "Coming Soon Channels cannot refresh cache."
            )
        active_locks = (
            self.db.query(WorkspaceLock)
            .join(Listing, Listing.id == WorkspaceLock.listing_id)
            .filter(Listing.channel_id == channel_id, WorkspaceLock.expires_at > utcnow())
            .count()
        )
        if active_locks:
            raise self._conflict(
                "CACHE_REFRESH_APPLY_CONFLICT",
                "Channel Cache cannot refresh while overlapping Apply locks are active.",
            )
        result = await self.commerce.refresh_channel_cache(channel_id, user.username)
        active_locks = (
            self.db.query(WorkspaceLock)
            .join(Listing, Listing.id == WorkspaceLock.listing_id)
            .filter(Listing.channel_id == channel_id, WorkspaceLock.expires_at > utcnow())
            .count()
        )
        if active_locks:
            raise self._conflict(
                "CACHE_REFRESH_APPLY_CONFLICT",
                "Apply acquired a Listing lock while cache refresh was in progress.",
            )
        synchronized = 0
        for row in self.db.query(DlProductCache).filter_by(connector_id=channel_id).all():
            listing = (
                self.db.query(Listing)
                .filter_by(channel_id=channel_id, external_primary_id=row.product_id)
                .first()
            )
            if listing is not None:
                self._assert_listing_unlocked(channel_id, listing.id)
                self._materialize_cache_identity(row)
                synchronized += 1
        self._audit(
            "channel_cache_refreshed",
            user,
            correlation_id,
            channel_id=channel_id,
            metadata={
                "synchronized_listings": synchronized,
                "provider_result": {
                    key: value for key, value in result.items() if key not in {"raw", "credentials"}
                },
            },
        )
        self.db.commit()
        return {"channelId": channel_id, "synchronizedListings": synchronized, "result": result}

    # -- Internal policies ----------------------------------------------------

    def _seed_channels(self) -> None:
        definitions = {
            connector.channel_id: (
                connector.capabilities(),
                connector.__class__.__name__.replace("WorkspaceConnector", ""),
            )
            for connector in self.connectors.implemented()
        }
        for channel_id, (capabilities, name) in definitions.items():
            row = self.db.get(WorkspaceChannel, channel_id)
            payload = self._channel_shape(capabilities)
            if row is None:
                self.db.add(
                    WorkspaceChannel(
                        id=channel_id,
                        connector_type=channel_id.split(":", 1)[0],
                        name=name,
                        implementation_state="implemented",
                        capabilities_json=payload,
                        capability_version=capabilities.version,
                        enabled=True,
                    )
                )
            else:
                row.capabilities_json = payload
                row.capability_version = capabilities.version
                row.updated_at = utcnow()
        for channel_id, name in (
            ("digikala:main", "Digikala"),
            ("technolife:main", "Technolife"),
            ("shopify:main", "Shopify"),
        ):
            if self.db.get(WorkspaceChannel, channel_id) is None:
                self.db.add(
                    WorkspaceChannel(
                        id=channel_id,
                        connector_type=channel_id.split(":", 1)[0],
                        name=name,
                        implementation_state="coming_soon",
                        capabilities_json={},
                        capability_version="none",
                        enabled=False,
                    )
                )
        self.db.flush()

    def _global_currency_profile(self) -> CurrencyProfile:
        currency = canonical_text(self.config.get("server.currency") or "").upper()
        configured_unit = canonical_text(self.config.get("server.currency_unit") or "").upper()
        if currency == "IRR" and not configured_unit:
            raise self._unprocessable(
                "CURRENCY_UNIT_REQUIRED",
                "IRR configuration must explicitly declare RIAL or TOMAN unit.",
            )
        unit = configured_unit or currency
        if not currency:
            raise self._unprocessable(
                "CURRENCY_CONFIGURATION_REQUIRED", "Global currency must be configured explicitly."
            )
        if currency == "IRR" and unit not in {"IRR", "RIAL", "TOMAN"}:
            raise self._unprocessable(
                "CURRENCY_UNIT_REQUIRED",
                "IRR configuration must explicitly use RIAL or TOMAN unit.",
            )
        reference = f"global:{currency}:{unit}"
        row = (
            self.db.query(CurrencyProfile)
            .filter_by(scope="global", scope_reference="default")
            .order_by(CurrencyProfile.version.desc())
            .first()
        )
        factor = Decimal("10") if unit == "TOMAN" else Decimal("1")
        if row is None:
            row = CurrencyProfile(
                id=_id(),
                scope="global",
                scope_reference="default",
                currency=currency,
                unit=unit,
                normalization_currency=currency,
                normalization_unit="RIAL" if currency == "IRR" else unit,
                conversion_factor=factor,
                conversion_rule="explicit-unit-v1",
                checksum=checksum(
                    {
                        "scope": "global",
                        "reference": "default",
                        "currency": currency,
                        "unit": unit,
                        "normalization_currency": currency,
                        "normalization_unit": "RIAL" if currency == "IRR" else unit,
                        "factor": str(factor),
                        "rule": "explicit-unit-v1",
                        "version": 1,
                    }
                ),
                version=1,
                enabled=True,
            )
            self.db.add(row)
            self.db.flush()
        elif (row.currency, row.unit) != (currency, unit):
            next_version = row.version + 1
            row = CurrencyProfile(
                id=_id(),
                scope="global",
                scope_reference="default",
                currency=currency,
                unit=unit,
                normalization_currency=currency,
                normalization_unit="RIAL" if currency == "IRR" else unit,
                conversion_factor=factor,
                conversion_rule="explicit-unit-v1",
                checksum=checksum(
                    {
                        "scope": "global",
                        "reference": "default",
                        "currency": currency,
                        "unit": unit,
                        "normalization_currency": currency,
                        "normalization_unit": "RIAL" if currency == "IRR" else unit,
                        "factor": str(factor),
                        "rule": "explicit-unit-v1",
                        "version": next_version,
                    }
                ),
                version=next_version,
                enabled=True,
            )
            self.db.add(row)
            self.db.flush()
        _ = reference
        return row

    def _source_currency_profile(
        self, source_id: str, currency: str | None, unit: str | None
    ) -> CurrencyProfile:
        currency_value = canonical_text(currency).upper()
        unit_value = canonical_text(unit).upper()
        if not currency_value or not unit_value:
            raise self._unprocessable(
                "SOURCE_CURRENCY_INCOMPLETE",
                "Source currency override requires both currency and unit.",
            )
        if currency_value == "IRR" and unit_value not in {"RIAL", "TOMAN"}:
            raise self._unprocessable(
                "SOURCE_CURRENCY_UNIT_INVALID", "IRR source override requires RIAL or TOMAN unit."
            )
        latest = (
            self.db.query(CurrencyProfile)
            .filter_by(scope="source", scope_reference=source_id)
            .order_by(CurrencyProfile.version.desc())
            .first()
        )
        if latest and (latest.currency, latest.unit) == (currency_value, unit_value):
            return latest
        factor = (
            Decimal("10") if currency_value == "IRR" and unit_value == "TOMAN" else Decimal("1")
        )
        row = CurrencyProfile(
            id=_id(),
            scope="source",
            scope_reference=source_id,
            currency=currency_value,
            unit=unit_value,
            normalization_currency=currency_value,
            normalization_unit="RIAL" if currency_value == "IRR" else unit_value,
            conversion_factor=factor,
            conversion_rule="explicit-source-unit-v1",
            version=(next_version := latest.version + 1 if latest else 1),
            checksum=checksum(
                {
                    "scope": "source",
                    "reference": source_id,
                    "currency": currency_value,
                    "unit": unit_value,
                    "normalization_currency": currency_value,
                    "normalization_unit": "RIAL" if currency_value == "IRR" else unit_value,
                    "factor": str(factor),
                    "rule": "explicit-source-unit-v1",
                    "version": next_version,
                }
            ),
            enabled=True,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _materialize_cache_identity(
        self,
        row: DlProductCache,
        *,
        listing_map: dict[tuple[str, str], Listing] | None = None,
        canonical_map: dict[str, CanonicalProduct] | None = None,
        cache_map: dict[str, ChannelCache] | None = None,
        channel_map: dict[str, WorkspaceChannel] | None = None,
    ) -> tuple[CanonicalProduct, Listing, ChannelCache]:
        connector_id = str(row.connector_id)
        product_id = str(row.product_id)
        channel = (
            channel_map.get(connector_id)
            if channel_map is not None
            else self.db.get(WorkspaceChannel, connector_id)
        )
        if channel is None or channel.implementation_state != "implemented":
            raise self._unprocessable(
                "CHANNEL_NOT_IMPLEMENTED",
                f"{connector_id} is not an implemented Workspace Channel.",
            )
        identity = (connector_id, product_id)
        listing = (
            listing_map.get(identity)
            if listing_map is not None
            else self.db.query(Listing)
            .filter_by(channel_id=connector_id, external_primary_id=product_id)
            .first()
        )
        if listing:
            canonical = (
                canonical_map.get(listing.canonical_product_id)
                if canonical_map is not None
                else self.db.get(CanonicalProduct, listing.canonical_product_id)
            )
            if canonical is None:
                raise self._conflict(
                    "CANONICAL_PRODUCT_MISSING", "Persisted Listing has no Canonical Product."
                )
        else:
            product_type = str(row.product_type or "simple").lower()
            if product_type not in {item.value for item in ProductKind}:
                product_type = ProductKind.SIMPLE
            raw_data: dict[str, Any] = row.raw_data if isinstance(row.raw_data, dict) else {}
            canonical = CanonicalProduct(
                id=_id(),
                name=canonical_text(row.name or product_id),
                sku=canonical_text(row.sku) or None,
                product_type=product_type,
                parent_id=None,
                brand=canonical_text(raw_data.get("brand")) or None,
                category=self._first_category(row.categories),
                status="active",
            )
            self.db.add(canonical)
            self.db.flush()
            listing = Listing(
                id=_id(),
                canonical_product_id=canonical.id,
                channel_id=connector_id,
                external_primary_id=product_id,
                external_id_type="product_or_variation_id"
                if connector_id == "woocommerce:primary"
                else "product_number",
                secondary_identifiers_json=self._secondary_identifiers(row),
                sku=canonical_text(row.sku) or None,
                label=canonical_text(row.name or product_id),
                mapping_state=MappingState.RESOLVED,
                mapping_version=1,
                capability_state_json=channel.capabilities_json,
                enabled=True,
            )
            self.db.add(listing)
            self.db.add(
                MappingRevision(
                    id=_id(),
                    listing_id=listing.id,
                    revision_number=1,
                    previous_canonical_product_id=None,
                    proposed_canonical_product_id=canonical.id,
                    decision="automatic",
                    evidence_json={
                        "method": "exact_channel_primary_identifier",
                        "connector_id": connector_id,
                        "external_primary_id": product_id,
                    },
                    reason="Canonical Product created from exact Channel primary identity.",
                    approved_by_user_id=None,
                    checksum=checksum(
                        {
                            "listing": listing.id,
                            "canonical": canonical.id,
                            "method": "exact_channel_primary_identifier",
                        }
                    ),
                )
            )
            self.db.flush()
            if listing_map is not None:
                listing_map[identity] = listing
            if canonical_map is not None:
                canonical_map[canonical.id] = canonical
        cache = (
            cache_map.get(listing.id)
            if cache_map is not None
            else self.db.query(ChannelCache).filter_by(listing_id=listing.id).first()
        )
        cache_payload = self._cache_payload(row, listing.id)
        if cache is None:
            cache = ChannelCache(
                id=_id(),
                listing_id=listing.id,
                channel_id=listing.channel_id,
                cache_version=1,
                **cache_payload,
            )
            self.db.add(cache)
            if cache_map is not None:
                cache_map[listing.id] = cache
        elif cache.checksum != cache_payload["checksum"]:
            for key, value in cache_payload.items():
                setattr(cache, key, value)
            cache.cache_version += 1
        self.db.flush()
        return canonical, listing, cache

    def _cache_payload(self, row: DlProductCache, listing_id: str) -> dict[str, Any]:
        capabilities = self._capabilities(str(row.connector_id))
        price = row.regular_price or row.price or row.last_price
        payload = {
            "listing": listing_id,
            "price": price,
            "stock": row.stock_qty,
            "status": row.status or row.stock_status,
            "manage_stock": row.manage_stock,
            "record_hash": row.record_hash,
            "fetched": str(row.last_successful_read or row.last_fetched_at),
        }
        return {
            "price_raw": str(price) if price is not None else None,
            "price_currency": capabilities.currency,
            "price_unit": capabilities.unit,
            "stock_quantity": row.stock_qty,
            "status": row.status or row.stock_status,
            "manage_stock": row.manage_stock,
            "checksum": checksum(payload),
            "connector_version": capabilities.version,
            "freshness": row.freshness or "stale",
            "fetch_status": "success" if row.freshness != "error" else "error",
            "external_updated_at": None,
            "fetched_at": row.last_successful_read or row.last_fetched_at or utcnow(),
            "error_category": "cache_error" if row.freshness == "error" else None,
            "error_message": None,
            "response_reference": row.record_hash,
        }

    def _assert_review_fresh(self, review: Review, user: FlowHubUser, correlation_id: str) -> None:
        stale_reasons: list[str] = []
        mapping_payload: list[dict[str, Any]] = []
        capability_payload: list[dict[str, Any]] = []
        currency_payload: list[dict[str, Any]] = []
        max_age_minutes = self._cache_max_age_minutes()
        if review.ruleset_version != VALIDATION_VERSION:
            stale_reasons.append("validation_ruleset")
        profile = self.db.get(CurrencyProfile, review.currency_profile_id)
        latest_profile = None
        if profile is not None:
            latest_profile = (
                self.db.query(CurrencyProfile)
                .filter_by(
                    scope=profile.scope,
                    scope_reference=profile.scope_reference,
                    enabled=True,
                )
                .order_by(CurrencyProfile.version.desc())
                .first()
            )
        if (
            profile is None
            or latest_profile is None
            or latest_profile.id != review.currency_profile_id
            or profile.version != review.currency_profile_version
            or profile.checksum != review.currency_profile_checksum
            or review.currency_source_reference != f"{profile.scope}:{profile.scope_reference}"
            or review.currency_ruleset_version != CURRENCY_RULESET_VERSION
        ):
            stale_reasons.append("currency_profile")
        for captured in self.reviews.cache_versions(review.id):
            listing = self.db.get(Listing, captured.listing_id)
            cache = self.db.query(ChannelCache).filter_by(listing_id=captured.listing_id).first()
            capabilities = self._capabilities(captured.channel_id)
            if (
                cache is None
                or cache.cache_version != captured.cache_version
                or cache.checksum != captured.cache_checksum
            ):
                stale_reasons.append(f"cache:{captured.listing_id}")
            elif cache.fetched_at < utcnow() - timedelta(minutes=max_age_minutes):
                stale_reasons.append(f"cache_age:{captured.listing_id}")
            if listing is None or listing.mapping_version != captured.mapping_version:
                stale_reasons.append(f"mapping:{captured.listing_id}")
            if capabilities.version != captured.capability_version:
                stale_reasons.append(f"capability:{captured.channel_id}")
            if listing:
                mapping_payload.append(
                    {
                        "listing": listing.id,
                        "version": listing.mapping_version,
                        "state": listing.mapping_state,
                    }
                )
            capability_payload.append(
                {"channel": capabilities.channel_id, "version": capabilities.version}
            )
            currency_payload.append(
                {
                    "channel": capabilities.channel_id,
                    "currency": capabilities.currency,
                    "unit": capabilities.unit,
                }
            )
        if (
            checksum(_unique_dicts(mapping_payload)) != review.mapping_digest
            or checksum(_unique_dicts(capability_payload)) != review.capability_digest
            or checksum(_unique_dicts(currency_payload)) != review.currency_digest
        ):
            stale_reasons.append("configuration_digest")
        current_channel_references = sorted(
            f"{item['channel']}:{item['currency']}:{item['unit']}"
            for item in _unique_dicts(currency_payload)
        )
        if current_channel_references != sorted(review.currency_channel_references_json):
            stale_reasons.append("currency_channel_override")
        # Capability digest includes field write decisions and is checked per captured version above.
        if stale_reasons:
            review.status = ReviewState.STALE
            review.invalidated_at = utcnow()
            review.stale_reason = ";".join(sorted(set(stale_reasons)))
            self._audit(
                "review_stale",
                user,
                correlation_id,
                workspace_id=review.workspace_id,
                snapshot_id=review.snapshot_id,
                draft_revision_id=review.draft_revision_id,
                review_id=review.id,
                review_result="stale",
                reason=review.stale_reason,
            )
            self.db.commit()
            raise self._conflict(
                "STALE_REVIEW",
                "Channel Cache, Mapping, capability, or currency configuration changed; regenerate Review.",
                {"reasons": stale_reasons},
            )

    def _selection_document(self, review: Review, items: list[ReviewItem]) -> dict[str, object]:
        ordered = sorted(
            items, key=lambda item: (item.channel_id, item.listing_id, item.field, item.id)
        )
        return {
            "workspace_id": review.workspace_id,
            "snapshot_id": review.snapshot_id,
            "draft_revision_id": review.draft_revision_id,
            "review_id": review.id,
            "review_checksum": review.checksum,
            "selection_version": review.selection_version,
            "channel_ids": sorted({item.channel_id for item in ordered}),
            "listing_ids": sorted({item.listing_id for item in ordered}),
            "review_item_ids": [item.id for item in ordered],
            "field_changes": [
                {"listing_id": item.listing_id, "channel_id": item.channel_id, "field": item.field}
                for item in ordered
            ],
        }

    def _recover_job_if_stale(self, job: ApplyJob, user: FlowHubUser, correlation_id: str) -> bool:
        if job.status != ApplyState.RUNNING:
            return False
        heartbeat = job.heartbeat_at or job.started_at
        if heartbeat is None or heartbeat >= utcnow() - timedelta(minutes=STALE_APPLY_MINUTES):
            return False
        attempts = (
            self.db.query(ProviderWriteAttempt)
            .filter(ProviderWriteAttempt.apply_job_id == job.id)
            .order_by(ProviderWriteAttempt.listing_id.asc())
            .all()
        )
        if not attempts:
            return False
        uncertain_item_ids: set[str] = set()
        recovered_verified_item_ids: set[str] = set()
        for attempt in attempts:
            latest = (
                self.db.query(ProviderWriteAttemptEvent)
                .filter_by(attempt_id=attempt.id)
                .order_by(
                    ProviderWriteAttemptEvent.occurred_at.desc(),
                    ProviderWriteAttemptEvent.id.desc(),
                )
                .first()
            )
            payload = dict(attempt.normalized_payload_json)
            attempt_item_ids = [str(value) for value in payload.get("apply_item_ids", [])]
            attempt_items: list[ApplyJobItem] = [
                item
                for item_id in attempt_item_ids
                if (item := self.db.get(ApplyJobItem, item_id)) is not None
            ]
            if latest is not None and latest.outcome == WriteOutcome.VERIFIED_APPLIED.value:
                if not all(item.status == "applied" for item in attempt_items):
                    intent = WorkspaceWriteIntent.from_persisted_payload(payload)
                    result = WorkspaceWriteResult(
                        listing_id=intent.listing_id,
                        outcome=WriteOutcome.VERIFIED_APPLIED,
                        provider_accepted=True,
                        response=dict(latest.provider_response_json),
                        accepted_price=intent.target_price,
                        accepted_stock=intent.target_stock,
                        accepted_status=intent.target_status,
                    )
                    review_items = (
                        self.db.query(ReviewItem)
                        .filter(ReviewItem.id.in_([item.review_item_id for item in attempt_items]))
                        .all()
                    )
                    self._record_listing_success(job, result, review_items, user)
                recovered_verified_item_ids.update(attempt_item_ids)
            elif latest is not None and latest.outcome in {
                WriteOutcome.DISPATCHED.value,
                WriteOutcome.PROVIDER_ACCEPTED.value,
                WriteOutcome.RECONCILIATION_REQUIRED.value,
                WriteOutcome.RECOVERING.value,
            }:
                uncertain_item_ids.update(attempt_item_ids)
            else:
                for item in attempt_items:
                    if item.status != "applied":
                        item.status = "failed"
                        item.error_category = "stale_before_dispatch"
                        item.error_message = "Worker stopped before provider dispatch."
                        item.retry_eligible = False
        for item in self.applies.items(job.id):
            if item.id in uncertain_item_ids and item.status not in {
                "applied",
                "failed",
                "cancelled",
            }:
                item.status = "reconciliation_required"
                item.retry_eligible = False
        job.status = self._apply_status_from_items(job.id)
        job.worker_id = None
        job.heartbeat_at = utcnow()
        if job.status != ApplyState.RECONCILIATION_REQUIRED:
            job.completed_at = utcnow()
            self._release_listing_locks(job.id)
        self._audit(
            "apply_stale_running_recovered",
            user,
            correlation_id,
            workspace_id=job.workspace_id,
            snapshot_id=job.snapshot_id,
            draft_revision_id=job.draft_revision_id,
            review_id=job.review_id,
            apply_job_id=job.id,
            apply_result=job.status,
            metadata={
                "uncertain_item_ids": sorted(uncertain_item_ids),
                "recovered_verified_item_ids": sorted(recovered_verified_item_ids),
                "redispatch_allowed": False,
            },
        )
        self.db.commit()
        return True

    def _intent_from_immutable_attempt(
        self, job: ApplyJob, listing_id: str
    ) -> WorkspaceWriteIntent:
        attempt = (
            self.db.query(ProviderWriteAttempt)
            .filter_by(apply_job_id=job.id, listing_id=listing_id)
            .order_by(ProviderWriteAttempt.attempt_number.desc())
            .first()
        )
        if attempt is None:
            raise self._conflict(
                "APPLY_ATTEMPT_MISSING",
                "Reconciliation requires an immutable dispatch attempt.",
            )
        try:
            return WorkspaceWriteIntent.from_persisted_payload(
                dict(attempt.normalized_payload_json)
            )
        except (TypeError, ValueError) as exc:
            raise self._conflict(
                "APPLY_ATTEMPT_PAYLOAD_INVALID",
                "Immutable dispatch evidence is incomplete and cannot be reconciled safely.",
            ) from exc

    def _apply_status_from_items(self, job_id: str) -> ApplyState:
        states = [item.status for item in self.applies.items(job_id)]
        if states and all(state == "applied" for state in states):
            return ApplyState.APPLIED
        if any(
            state in {"reconciliation_required", "recovering", "dispatched", "provider_accepted"}
            for state in states
        ):
            return ApplyState.RECONCILIATION_REQUIRED
        if any(state == "applied" for state in states):
            return ApplyState.PARTIALLY_APPLIED
        return ApplyState.FAILED

    def _acquire_listing_locks(
        self,
        workspace_id: str,
        apply_job_id: str,
        scopes: list[tuple[str, str]],
    ) -> None:
        now = utcnow()
        expires = now + timedelta(minutes=LOCK_MINUTES)
        ordered = sorted(scopes)
        try:
            # Serialize Apply lock creation with Mapping and cache commits on
            # the stable Listing rows. This closes the read-check/write TOCTOU.
            listings = {
                item.id: item
                for item in self.db.query(Listing)
                .filter(Listing.id.in_([listing_id for _, listing_id in ordered]))
                .order_by(Listing.channel_id.asc(), Listing.id.asc())
                .with_for_update()
                .all()
            }
            for channel_id, listing_id in ordered:
                listing = listings.get(listing_id)
                if listing is None or listing.channel_id != channel_id:
                    raise self._conflict(
                        "APPLY_LISTING_IDENTITY_CHANGED",
                        "Selected Listing identity changed before lock acquisition.",
                    )
                existing = (
                    self.db.query(WorkspaceLock)
                    .filter_by(channel_id=channel_id, listing_id=listing_id)
                    .with_for_update()
                    .first()
                )
                if existing is not None and existing.expires_at > now:
                    raise self._conflict(
                        "APPLY_SCOPE_LOCKED",
                        "Another Apply is running for a selected Listing.",
                        {"listingIds": [listing_id]},
                    )
                if existing is not None:
                    owner_job = self.db.get(ApplyJob, existing.apply_job_id)
                    if owner_job is not None and owner_job.status in {
                        ApplyState.PENDING,
                        ApplyState.RUNNING,
                        ApplyState.RECONCILIATION_REQUIRED,
                    }:
                        raise self._conflict(
                            "APPLY_SCOPE_RECONCILIATION_REQUIRED",
                            "An expired Listing lock belongs to an unfinished or uncertain Apply.",
                            {"listingIds": [listing_id], "applyJobId": owner_job.id},
                        )
                    self.db.delete(existing)
                    self.db.flush()
                self.db.add(
                    WorkspaceLock(
                        id=_id(),
                        workspace_id=workspace_id,
                        channel_id=channel_id,
                        listing_id=listing_id,
                        apply_job_id=apply_job_id,
                        acquired_at=now,
                        expires_at=expires,
                    )
                )
                self.db.flush()
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise self._conflict(
                "APPLY_SCOPE_LOCKED", "Another Apply acquired the selected Listing."
            ) from exc
        except Exception:
            self.db.rollback()
            raise

    def _assert_listing_unlocked(self, channel_id: str, listing_id: str) -> None:
        active = (
            self.db.query(WorkspaceLock)
            .filter_by(channel_id=channel_id, listing_id=listing_id)
            .filter(WorkspaceLock.expires_at > utcnow())
            .first()
        )
        if active is not None:
            raise self._conflict(
                "LISTING_MUTATION_LOCKED",
                "Listing Mapping or Cache cannot change during Apply.",
                {"listingId": listing_id},
            )

    def _release_listing_locks(self, apply_job_id: str) -> None:
        self.db.query(WorkspaceLock).filter_by(apply_job_id=apply_job_id).delete(
            synchronize_session=False
        )

    def _cache_max_age_minutes(self) -> int:
        raw = self.config.get("workspace.channel_cache_max_age_minutes") or "60"
        try:
            value = int(raw)
        except ValueError:
            value = 60
        return min(max(value, 1), 10_080)

    def _write_intent(
        self,
        job: ApplyJob,
        listing_id: str,
        items: list[ReviewItem],
        selection_checksum: str,
    ) -> WorkspaceWriteIntent:
        listing = self.db.get(Listing, listing_id)
        cache = self.db.query(ChannelCache).filter_by(listing_id=listing_id).first()
        product = self.db.get(CanonicalProduct, listing.canonical_product_id) if listing else None
        if listing is None or cache is None or product is None:
            raise WorkspaceDomainError("Apply Listing state is unavailable.")
        targets = {item.field: item.target_value for item in items}
        price_item = next((item for item in items if item.field == "price"), None)
        parent_external_id = None
        if product.parent_id:
            parent_listing = (
                self.db.query(Listing)
                .filter_by(canonical_product_id=product.parent_id, channel_id=listing.channel_id)
                .first()
            )
            parent_external_id = parent_listing.external_primary_id if parent_listing else None
        capabilities = self._capabilities(listing.channel_id)
        job_item_ids = tuple(
            row.id
            for row in self.db.query(ApplyJobItem)
            .filter(
                ApplyJobItem.apply_job_id == job.id,
                ApplyJobItem.review_item_id.in_([item.id for item in items]),
            )
            .order_by(ApplyJobItem.id)
            .all()
        )
        payload = {
            "listing": listing.id,
            "channel": listing.channel_id,
            "targets": targets,
            "mapping_version": listing.mapping_version,
            "cache_version": cache.cache_version,
            "cache_checksum": cache.checksum,
            "capability_version": capabilities.version,
        }
        review = self.db.get(Review, job.review_id)
        if review is None:
            raise WorkspaceDomainError("Apply Review state is unavailable.")
        return WorkspaceWriteIntent(
            apply_job_id=job.id,
            apply_item_ids=job_item_ids,
            workspace_id=job.workspace_id,
            snapshot_id=job.snapshot_id,
            draft_revision_id=job.draft_revision_id,
            review_id=job.review_id,
            selection_checksum=selection_checksum,
            listing_id=listing.id,
            channel_id=listing.channel_id,
            external_primary_id=listing.external_primary_id,
            sku=listing.sku,
            product_type=product.product_type,
            parent_external_id=parent_external_id,
            current_price=float(cache.price_raw) if cache.price_raw not in (None, "") else None,
            current_stock=float(cache.stock_quantity) if cache.stock_quantity is not None else None,
            current_status=cache.status,
            target_price=float(targets["price"]) if "price" in targets else None,
            target_stock=float(targets["stock"]) if "stock" in targets else None,
            target_status=targets.get("status"),
            currency=price_item.normalized_value_json.get("currency")
            if price_item
            else cache.price_currency,
            unit=price_item.normalized_value_json.get("unit") if price_item else cache.price_unit,
            mapping_version=listing.mapping_version,
            cache_version=cache.cache_version,
            cache_checksum=cache.checksum,
            capability_version=capabilities.version,
            currency_digest=review.currency_digest,
            idempotency_key=checksum(
                {"logical_operation": job.logical_operation_key, "listing": listing.id}
            ),
            payload_hash=checksum(payload),
        )

    def _record_listing_success(
        self,
        job: ApplyJob,
        result: WorkspaceWriteResult,
        affected: list[ReviewItem],
        user: FlowHubUser,
    ) -> None:
        cache = self.db.query(ChannelCache).filter_by(listing_id=result.listing_id).first()
        cache_patched = False
        for item in affected:
            job_item = (
                self.db.query(ApplyJobItem)
                .filter_by(apply_job_id=job.id, review_item_id=item.id)
                .one()
            )
            job_item.status = "applied"
            job_item.attempt_number += 1
            job_item.connector_response_json = dict(result.response)
            job_item.external_response_id = result.external_response_id
            job_item.retry_eligible = False
            job_item.cache_sync_status = "patched_verified"
            job_item.started_at = job.started_at
            job_item.completed_at = utcnow()
            if cache:
                if item.field == "price" and result.accepted_price is not None:
                    cache.price_raw = _number_text(result.accepted_price)
                    cache_patched = True
                elif item.field == "stock" and result.accepted_stock is not None:
                    cache.stock_quantity = Decimal(str(result.accepted_stock))
                    cache_patched = True
                elif item.field == "status" and result.accepted_status is not None:
                    cache.status = result.accepted_status
                    cache_patched = True
            self._audit(
                "apply_item_succeeded",
                user,
                job.correlation_id,
                workspace_id=job.workspace_id,
                snapshot_id=job.snapshot_id,
                draft_revision_id=job.draft_revision_id,
                review_id=job.review_id,
                apply_job_id=job.id,
                canonical_product_id=item.canonical_product_id,
                listing_id=item.listing_id,
                channel_id=item.channel_id,
                changed_field=item.field,
                previous_value=item.current_value,
                target_value=item.target_value,
                apply_result="applied",
            )
        if cache and cache_patched:
            cache.cache_version += 1
            cache.checksum = checksum(
                {
                    "listing": cache.listing_id,
                    "price": cache.price_raw,
                    "stock": str(cache.stock_quantity),
                    "status": cache.status,
                    "apply": job.id,
                }
            )
            cache.freshness = "fresh"
            cache.fetch_status = "success"
            cache.fetched_at = utcnow()

    def _record_listing_failure(
        self,
        job: ApplyJob,
        result: WorkspaceWriteResult,
        affected: list[ReviewItem],
        user: FlowHubUser,
    ) -> None:
        for item in affected:
            job_item = (
                self.db.query(ApplyJobItem)
                .filter_by(apply_job_id=job.id, review_item_id=item.id)
                .one()
            )
            job_item.status = "failed"
            job_item.attempt_number += 1
            job_item.connector_response_json = dict(result.response)
            job_item.error_category = result.error_category
            job_item.error_message = result.error_message
            job_item.retry_eligible = result.retry_eligible
            job_item.cache_sync_status = "not_updated"
            job_item.started_at = job.started_at
            job_item.completed_at = utcnow()
            self._audit(
                "apply_item_failed",
                user,
                job.correlation_id,
                workspace_id=job.workspace_id,
                snapshot_id=job.snapshot_id,
                draft_revision_id=job.draft_revision_id,
                review_id=job.review_id,
                apply_job_id=job.id,
                canonical_product_id=item.canonical_product_id,
                listing_id=item.listing_id,
                channel_id=item.channel_id,
                changed_field=item.field,
                previous_value=item.current_value,
                target_value=item.target_value,
                apply_result="failed",
                reason=result.error_message,
            )

    def _record_listing_reconciliation(
        self,
        job: ApplyJob,
        result: WorkspaceWriteResult,
        affected: list[ReviewItem],
        user: FlowHubUser,
    ) -> None:
        for item in affected:
            job_item = (
                self.db.query(ApplyJobItem)
                .filter_by(apply_job_id=job.id, review_item_id=item.id)
                .one()
            )
            job_item.status = WriteOutcome.RECONCILIATION_REQUIRED
            job_item.attempt_number += 1
            job_item.connector_response_json = dict(result.response)
            job_item.external_response_id = result.external_response_id
            job_item.error_category = result.error_category or "provider_unknown"
            job_item.error_message = result.error_message
            job_item.retry_eligible = False
            job_item.cache_sync_status = "reconciliation_required"
            job_item.started_at = job.started_at
            job_item.completed_at = utcnow()
            self._audit(
                "apply_item_reconciliation_required",
                user,
                job.correlation_id,
                workspace_id=job.workspace_id,
                snapshot_id=job.snapshot_id,
                draft_revision_id=job.draft_revision_id,
                review_id=job.review_id,
                apply_job_id=job.id,
                canonical_product_id=item.canonical_product_id,
                listing_id=item.listing_id,
                channel_id=item.channel_id,
                changed_field=item.field,
                previous_value=item.current_value,
                target_value=item.target_value,
                apply_result=WriteOutcome.RECONCILIATION_REQUIRED,
                reason=result.error_message or "Provider outcome requires reconciliation.",
            )

    def _mark_listing_failed(
        self, job: ApplyJob, listing_id: str, message: str, user: FlowHubUser
    ) -> None:
        items = (
            self.db.query(ApplyJobItem).filter_by(apply_job_id=job.id, listing_id=listing_id).all()
        )
        for item in items:
            item.status = "failed"
            item.attempt_number += 1
            item.error_category = "connector_batch_error"
            item.error_message = canonical_text(message)[:1000]
            item.cache_sync_status = "not_updated"
            item.completed_at = utcnow()
            self._audit(
                "apply_item_failed",
                user,
                job.correlation_id,
                workspace_id=job.workspace_id,
                snapshot_id=job.snapshot_id,
                draft_revision_id=job.draft_revision_id,
                review_id=job.review_id,
                apply_job_id=job.id,
                canonical_product_id=item.canonical_product_id,
                listing_id=item.listing_id,
                channel_id=item.channel_id,
                changed_field=item.field,
                apply_result="failed",
                reason=item.error_message,
            )

    def _workspace_for_user(
        self, workspace_id: str, user: FlowHubUser, *, edit: bool = False
    ) -> UnifiedWorkspace:
        workspace = self.workspaces.get(workspace_id)
        if workspace is None:
            raise self._not_found("WORKSPACE_NOT_FOUND", "Workspace not found.")
        permission = "workspace.edit" if edit else "workspace.read"
        if workspace.owner_user_id != user.id and not has_workspace_permission(
            user, "workspace.admin"
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                {"code": "WORKSPACE_ACCESS_DENIED", "message": "Workspace access denied."},
            )
        if not has_workspace_permission(user, permission):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                {
                    "code": "WORKSPACE_PERMISSION_DENIED",
                    "message": f"Permission {permission} is required.",
                },
            )
        return workspace

    def _capabilities(self, channel_id: str) -> ChannelCapabilities:
        return self.connectors.get(channel_id).capabilities()

    def _money(self, target: str, capabilities: ChannelCapabilities) -> Money:
        factor = (
            "10" if capabilities.currency == "IRR" and capabilities.unit.upper() == "TOMAN" else "1"
        )
        return Money.create(
            target,
            currency=capabilities.currency,
            unit=capabilities.unit,
            normalized_currency=capabilities.currency,
            normalized_unit="RIAL" if capabilities.currency == "IRR" else capabilities.unit,
            conversion_factor=factor,
            conversion_rule="explicit-channel-unit-v1",
            conversion_context=VALIDATION_VERSION,
            configuration_reference=f"{capabilities.channel_id}:{capabilities.version}",
        )

    def _normalized_target(
        self, change: DraftRevisionChange, capabilities: ChannelCapabilities
    ) -> dict[str, Any]:
        if change.field == "price":
            return cast(dict[str, Any], self._money(change.target_value, capabilities).as_dict())
        return {"raw_value": change.target_value, "field": change.field}

    @staticmethod
    def _current_value(cache: ChannelCache, field: str) -> str | None:
        if field == "price":
            return cache.price_raw
        if field == "stock":
            return str(cache.stock_quantity) if cache.stock_quantity is not None else None
        return cache.status

    @staticmethod
    def _normalized_snapshot_data(
        product: CanonicalProduct, listing: Listing, cache: ChannelCache
    ) -> dict[str, Any]:
        return {
            "canonical_product_id": product.id,
            "canonical_name": product.name,
            "product_type": product.product_type,
            "listing_id": listing.id,
            "channel_id": listing.channel_id,
            "external_primary_id": listing.external_primary_id,
            "mapping_version": listing.mapping_version,
            "cache_version": cache.cache_version,
            "cache_checksum": cache.checksum,
        }

    @staticmethod
    def _secondary_identifiers(row: DlProductCache) -> dict[str, Any]:
        raw: dict[str, Any] = row.raw_data if isinstance(row.raw_data, dict) else {}
        return {
            key: raw[key]
            for key in ("product_number", "parent_product_number")
            if raw.get(key) not in (None, "")
        }

    @staticmethod
    def _first_category(categories: object) -> str | None:
        if not isinstance(categories, list) or not categories:
            return None
        first = categories[0]
        if isinstance(first, dict):
            return canonical_text(first.get("name")) or None
        return canonical_text(first) or None

    @staticmethod
    def _channel_shape(capabilities: ChannelCapabilities) -> dict[str, Any]:
        return {
            "channelId": capabilities.channel_id,
            "readPrice": capabilities.read_price,
            "writePrice": capabilities.write_price,
            "readStock": capabilities.read_stock,
            "writeStock": capabilities.write_stock,
            "readStatus": capabilities.read_status,
            "writeStatus": capabilities.write_status,
            "supportsBulkUpdate": capabilities.supports_bulk_update,
            "supportsPartialUpdate": capabilities.supports_partial_update,
            "supportsMultipleListings": capabilities.supports_multiple_listings,
            "supportsVariations": capabilities.supports_variations,
            "requiresStockManagement": capabilities.requires_stock_management,
            "maximumBatchSize": capabilities.maximum_batch_size,
            "rateLimitPerMinute": capabilities.rate_limit_per_minute,
            "healthState": capabilities.health_state,
            "primaryIdentifierType": capabilities.primary_identifier_type,
            "supportedStatuses": list(capabilities.supported_statuses),
            "currency": capabilities.currency,
            "unit": capabilities.unit,
            "writeAvailable": capabilities.write_available,
            "version": capabilities.version,
        }

    @staticmethod
    def _revision_shape(revision: DraftRevision) -> dict[str, Any]:
        return {
            "id": revision.id,
            "draftId": revision.draft_id,
            "workspaceId": revision.workspace_id,
            "snapshotId": revision.snapshot_id,
            "revisionNumber": revision.revision_number,
            "parentRevisionId": revision.parent_revision_id,
            "restoredFromRevisionId": revision.restored_from_revision_id,
            "creatorUserId": revision.creator_user_id,
            "checksum": revision.checksum,
            "metadata": revision.metadata_json,
            "createdAt": revision.created_at,
        }

    @staticmethod
    def _preference_shape(row: UserWorkspacePreference) -> dict[str, Any]:
        return {
            "visibleChannelIds": row.visible_channel_ids_json,
            "channelOrder": row.channel_order_json,
            "visibleFields": row.visible_fields_json,
            "displayNameSource": row.display_name_source,
            "version": row.version,
        }

    @staticmethod
    def _audit_shape(row: UnifiedAuditEntry) -> dict[str, Any]:
        return {
            "id": row.id,
            "correlationId": row.correlation_id,
            "eventType": row.event_type,
            "userId": row.user_id,
            "occurredAt": row.occurred_at,
            "workspaceId": row.workspace_id,
            "snapshotId": row.snapshot_id,
            "draftId": row.draft_id,
            "draftRevisionId": row.draft_revision_id,
            "reviewId": row.review_id,
            "applyJobId": row.apply_job_id,
            "canonicalProductId": row.canonical_product_id,
            "listingId": row.listing_id,
            "channelId": row.channel_id,
            "changedField": row.changed_field,
            "previousValue": row.previous_value,
            "targetValue": row.target_value,
            "validationResult": row.validation_result,
            "reviewResult": row.review_result,
            "applyResult": row.apply_result,
            "reason": row.reason,
            "metadata": row.metadata_json,
            "metadataChecksum": row.metadata_checksum,
        }

    def _audit(
        self, event_type: str, user: FlowHubUser, correlation_id: str, **fields: Any
    ) -> None:
        self.events.publish(
            DomainEvent(
                event_type=event_type,
                correlation_id=correlation_id,
                user_id=user.id,
                attributes=fields,
            )
        )
        logger.info(
            "unified_workspace_event",
            extra={
                "event_type": event_type,
                "correlation_id": correlation_id,
                "workspace_id": fields.get("workspace_id"),
                "draft_revision_id": fields.get("draft_revision_id"),
                "review_id": fields.get("review_id"),
                "apply_job_id": fields.get("apply_job_id"),
                "channel_id": fields.get("channel_id"),
            },
        )

    @staticmethod
    def _error(
        status_code: int, code: str, message: str, context: dict[str, Any] | None = None
    ) -> HTTPException:
        return HTTPException(
            status_code, {"code": code, "message": message, "context": context or {}}
        )

    def _unprocessable(
        self, code: str, message: str, context: dict[str, Any] | None = None
    ) -> HTTPException:
        return self._error(status.HTTP_422_UNPROCESSABLE_ENTITY, code, message, context)

    def _conflict(
        self, code: str, message: str, context: dict[str, Any] | None = None
    ) -> HTTPException:
        return self._error(status.HTTP_409_CONFLICT, code, message, context)

    def _not_found(self, code: str, message: str) -> HTTPException:
        return self._error(status.HTTP_404_NOT_FOUND, code, message)


# SQLAlchemy tuple comparison keeps selection loading set-based and deterministic.
from sqlalchemy import tuple_  # noqa: E402


def _unique_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_value = {stable_json(item): item for item in items}
    return [by_value[key] for key in sorted(by_value)]


def _number_text(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else format(value, ".15g")
