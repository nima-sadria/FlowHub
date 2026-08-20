"""Read-only spreadsheet Source mapping, read policy, and import helpers."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.flowhub.config.nextcloud_url import NextcloudUrlValidationError, normalize_nextcloud_url
from app.connectors.common.source_http import SourceHttpClient, parse_trusted_private_networks
from app.flowhub.data_layer.models import (
    DlSourceDiscoveryLock,
    DlSourceDiscoveryReservation,
    DlSourceReadLock,
    DlSourceReadReservation,
    DlSourceSnapshot,
    DlWorksheetDiscoveryCache,
)
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.integrations.errors import IntegrationError
from app.flowhub.integrations.spreadsheet import load_workbook_bytes, parse_source_price_rows
from app.flowhub.security.upstream_errors import UpstreamServiceError, normalize_upstream_error
from app.flowhub.setup.service import AppConfigService
from app.flowhub.source_acquisition.execution import SourceAcquisitionExecutor
from app.flowhub.source_acquisition.models import (
    SourceObservationDataset,
    SourceObservationWorksheetDataset,
)
from app.flowhub.source_acquisition.nextcloud_provider import NextcloudWebDavAcquisitionProvider
from app.flowhub.source_workspace.models import SourceProfile
from app.flowhub.source_workspace.repositories import SourceRepository
from app.flowhub.sources.xlsx_discovery import RangedXlsxDiscovery, XlsxDiscoveryError
from app.flowhub.unified_workspace.domain import checksum

SOURCE_ID = "nextcloud:primary"
SOURCE_TYPE = "nextcloud_spreadsheet"
SOURCE_DATASET_PARSER_VERSION = "openpyxl-v1"
SOURCE_DATASET_FORMULA_EVALUATION_VERSION = "openpyxl-data-only-v1"


def resolve_participating_worksheet_scope(
    *,
    mapping_mode: str | None,
    mapping_name: str | None,
    enabled_rule_names: list[str] | None = None,
    rule_mode: str | None = None,
    legacy_mode: str = "all",
    legacy_name: str = "",
) -> dict[str, object]:
    """Resolve one canonical worksheet scope for a Source read."""
    mode = str(mapping_mode or "").strip().lower()
    if not mode:
        mode = str(legacy_mode or "all").strip().lower()
        name = str(legacy_name or "").strip()
        if mode == "selected" and not name:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Selected worksheet name is required.",
            )
        return {"mode": mode, "name": name, "names": []}
    if mode not in {"all", "selected"}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Unsupported worksheet mode.",
        )
    names = list(
        dict.fromkeys(
            str(name).strip()
            for name in (enabled_rule_names or [])
            if str(name).strip() and str(name).strip() != "*"
        )
    )
    if mode == "all" and not names:
        return {"mode": "all", "name": "", "names": []}
    if not names and mapping_name:
        names = [str(mapping_name).strip()]
    if not names:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Selected worksheet name is required.",
        )
    return {
        "mode": "selected",
        "name": names[0] if len(names) == 1 else "",
        "names": names,
    }

DEFAULT_SOURCE_MAPPING: dict[str, dict[str, object]] = {
    "id": {"enabled": True, "column": "B"},
    "price": {"enabled": True, "column": "C"},
    "stock": {"enabled": False, "column": "D"},
}

DEFAULT_READ_POLICY: dict[str, object] = {
    "enabled": True,
    "max_reads_per_24h": 10,
    "manual_read_allowed": True,
}

DEFAULT_DISCOVERY_POLICY: dict[str, object] = {
    "enabled": True,
    "max_refreshes_per_24h": 30,
}

_COLUMN_REF_RE = re.compile(r"^[A-Za-z]{1,3}$")
_HEADER_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _./()-]{0,63}$")
_HISTORY_KEY = "nextcloud.source_read_history"
_LAST_READ_AT_KEY = "nextcloud.last_read_at"
_LAST_READ_STATUS_KEY = "nextcloud.last_read_status"
_LAST_READ_ROWS_KEY = "nextcloud.last_read_row_count"
_LAST_READ_WARNINGS_KEY = "nextcloud.last_read_warning_count"
_LAST_READ_ERRORS_KEY = "nextcloud.last_read_error_count"
_DISCOVERY_POLICY_KEY = "nextcloud.worksheet_discovery_policy"


@dataclass(frozen=True)
class SourceImportResult:
    source_id: str
    source_type: str
    spreadsheet_path: str
    rows: list[dict]
    duplicate_info: dict
    snapshot: DlSourceSnapshot
    read_policy: dict
    stats: dict
    worksheets: dict[str, list[list[Any]]] | None = None
    dataset_id: str | None = None
    observation_id: str | None = None


class SpreadsheetSourceReadService:
    def __init__(
        self,
        db: Session,
        *,
        connector_id: str = SOURCE_ID,
        source_http_client: SourceHttpClient | None = None,
    ) -> None:
        self.db = db
        self.connector_id = connector_id
        self.config = AppConfigService(db)
        self.integration = IntegrationPlatformService(db)
        self.source_http_client = source_http_client or SourceHttpClient()

    def configured_resource_scope(self) -> str | None:
        """Return the local connector binding used to scope Observation evidence."""

        spreadsheet_path = self._connector_setting("spreadsheet_path")
        return f"webdav:{spreadsheet_path}" if spreadsheet_path else None

    def configured_binding_fingerprint(self) -> str | None:
        """Return a stable, non-secret identity for the configured workbook."""

        spreadsheet_path = self._connector_setting("spreadsheet_path")
        username = self._connector_setting("username").strip()
        if not spreadsheet_path or not username:
            return None
        try:
            normalized = normalize_nextcloud_url(
                self._connector_setting("url"), username
            )
        except NextcloudUrlValidationError:
            return None
        return self._resource_binding_fingerprint(
            spreadsheet_path=spreadsheet_path,
            normalized=normalized,
        )

    def _resource_binding_fingerprint(
        self,
        *,
        spreadsheet_path: str,
        normalized: dict[str, str],
    ) -> str:
        return checksum(
            {
                "contract": "nextcloud-resource-binding-v1",
                "connectorId": self.connector_id,
                "serverRootUrl": normalized["server_root_url"],
                "username": normalized["username"],
                "spreadsheetPath": spreadsheet_path,
            }
        )

    async def read_nextcloud_spreadsheet(
        self,
        *,
        triggered_by: str,
        triggered_by_id: str | int | None = None,
        manual: bool,
        capture_raw_worksheets: bool = False,
        source_profile_id: str | None = None,
        worksheet_scope: dict[str, object] | None = None,
        idempotency_key: str | None = None,
    ) -> SourceImportResult:
        spreadsheet_path = self._required_connector_setting("spreadsheet_path")
        mapping = None if capture_raw_worksheets else self.mapping()
        worksheet = self.worksheet_selection(source_profile_id=source_profile_id)
        resolved_worksheet_scope = worksheet_scope or self.worksheet_scope(
            source_profile_id=source_profile_id
        )
        try:
            normalize_nextcloud_url(
                self._connector_setting("url"),
                self._connector_setting("username"),
            )
        except NextcloudUrlValidationError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"code": exc.code, "message": str(exc)},
            ) from exc
        username = self._connector_setting("username").strip()
        password = self._connector_setting("password")
        normalized = normalize_nextcloud_url(
            self._connector_setting("url"),
            username,
        )
        if not username or not password:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nextcloud source credentials are incomplete.")
        source_profile = self._acquisition_source(
            source_profile_id=source_profile_id,
            triggered_by_id=triggered_by_id,
            worksheet=worksheet,
        )
        reservation_user_id = str(triggered_by_id if triggered_by_id is not None else triggered_by)
        quota_source_id = source_profile.id
        reservation = self.reserve_read_slot(
            reservation_user_id, manual=manual, source_id=quota_source_id
        )
        policy_state = self.read_policy_state(source_id=quota_source_id)

        self._record_event(
            "source_read_started",
            "Source read started.",
            triggered_by,
            {
                "source_id": quota_source_id,
                "source_type": SOURCE_TYPE,
                "spreadsheet_path": spreadsheet_path,
                "worksheet_mode": resolved_worksheet_scope["mode"],
                "worksheet_name": resolved_worksheet_scope["name"],
                "worksheet_names": resolved_worksheet_scope["names"],
                "reservation_id": reservation.id if reservation else None,
                "reservation_status": reservation.status if reservation else None,
                "read_only": True,
                "source_write": False,
            },
        )
        try:
            validated: dict[str, Any] = {}

            def validate_capture(content: bytes) -> dict[str, object]:
                workbook = load_workbook_bytes(content)
                validated["workbook"] = workbook
                headers = self._assessment_headers(workbook, source_profile)
                return {"schema_headers": headers} if headers is not None else {}

            capture_contract = checksum(
                {
                    "parser": "openpyxl-v1",
                    "source_version": source_profile.version,
                    "worksheet_mode": source_profile.worksheet_mode,
                    "worksheet_name": source_profile.worksheet_name,
                    "data_start_row": source_profile.data_start_row,
                    "capture_raw_worksheets": capture_raw_worksheets,
                }
            )
            provider = NextcloudWebDavAcquisitionProvider(
                webdav_files_root_url=normalized["webdav_files_root_url"],
                spreadsheet_path=spreadsheet_path,
                username=normalized["username"],
                app_password=password,
                capture_contract=capture_contract,
                validator=validate_capture,
            )
            execution = await SourceAcquisitionExecutor(
                self.db, http_client=self._nextcloud_http_client()
            ).request_and_execute(
                source_id=source_profile.id,
                provider=provider,
                worker_id=f"inline:{triggered_by}",
                lease_seconds=60,
                trigger_kind="manual" if manual else "system",
                resource_scope=f"webdav:{spreadsheet_path}",
                idempotency_key=idempotency_key or f"read:{uuid.uuid4()}",
                actor_user_id=(
                    int(triggered_by_id)
                    if triggered_by_id is not None and str(triggered_by_id).isdigit()
                    else None
                ),
                request_payload={
                    "operation": "acquire",
                    "capture_contract": capture_contract,
                },
            )
            if execution.run["status"] != "succeeded" or execution.capture is None:
                code = str(execution.run.get("failureCode") or execution.run["status"])
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY,
                    {"code": code, "message": "Source acquisition failed."},
                )
            content = execution.capture.content
            if content is None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    {"code": "raw_capture_unavailable", "message": "Source capture cannot be replayed."},
                )
            workbook = validated.get("workbook") or load_workbook_bytes(content)
            file_meta = {
                "etag": execution.capture.provenance.get("provider_change_token"),
                "last_modified": next(
                    (
                        item.get("metadata", {}).get("last_modified")
                        for item in execution.capture.evidence
                        if item.get("kind") == "capture_manifest"
                    ),
                    None,
                ),
                "content_length": str(len(content)),
            }
            # Every explicit acquisition retains one provider-neutral local
            # dataset. Returning raw worksheets remains opt-in for existing
            # callers, but persistence never depends on that presentation flag.
            acquired_worksheets = {
                sheet.title: [list(row) for row in sheet.iter_rows(values_only=True)]
                for sheet in workbook.worksheets
            }
            raw_worksheets = acquired_worksheets if capture_raw_worksheets else None
            if capture_raw_worksheets:
                rows = []
                duplicate_info: dict[str, Any] = {
                    "duplicate_product_ids": [],
                    "duplicate_skus": [],
                }
            else:
                if mapping is None:
                    raise RuntimeError("Legacy Source mapping was not loaded.")
                try:
                    rows, duplicate_info = parse_source_price_rows(
                        workbook,
                        mapping=mapping,
                        worksheet_mode=resolved_worksheet_scope["mode"],
                        worksheet_name=resolved_worksheet_scope["name"],
                        selected_worksheet_names=resolved_worksheet_scope["names"],
                    )
                except ValueError as exc:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_ENTITY,
                        {"code": "WORKSHEET_SCOPE_INVALID", "message": str(exc)},
                    ) from exc
            if not rows and not capture_raw_worksheets and source_profile_id is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Spreadsheet contains no importable source rows.")
            persisted_row_count = (
                sum(len(sheet_rows) for sheet_rows in raw_worksheets.values())
                if raw_worksheets is not None
                else len(rows)
            )
            stats = source_row_stats(rows, duplicate_info)
            if capture_raw_worksheets:
                stats["total_rows"] = persisted_row_count
                stats["valid_rows"] = persisted_row_count
            snapshot = self._upsert_source_snapshot(
                file_path=spreadsheet_path,
                content=content,
                file_meta=file_meta,
                sheet_names=list(workbook.sheetnames),
                row_count=persisted_row_count,
                duplicate_count=len(duplicate_info["duplicate_product_ids"]) + len(duplicate_info["duplicate_skus"]),
                invalid_row_count=stats["error_rows"],
            )
            observation = execution.observation
            if observation is None:
                raise RuntimeError("Successful Source acquisition is missing its Observation.")
            dataset = self._persist_observation_dataset(
                observation_id=str(observation["id"]),
                source_id=quota_source_id,
                resource_scope=str(observation["resourceScope"]),
                binding_fingerprint=self._resource_binding_fingerprint(
                    spreadsheet_path=spreadsheet_path,
                    normalized=normalized,
                ),
                source_snapshot=snapshot,
                workbook_checksum=hashlib.sha256(content).hexdigest(),
                worksheets=acquired_worksheets,
            )
            self._record_event(
                "source_read_completed",
                "Source read completed.",
                triggered_by,
                {
                    "source_id": quota_source_id,
                    "source_type": SOURCE_TYPE,
                    "spreadsheet_path": spreadsheet_path,
                    "worksheets": list(workbook.sheetnames),
                    "row_count": persisted_row_count,
                    "valid_rows": stats["valid_rows"],
                    "warning_rows": stats["warning_rows"],
                    "error_rows": stats["error_rows"],
                    "duplicate_rows": stats["duplicate_rows"],
                    "reservation_id": reservation.id if reservation else None,
                    "read_only": True,
                    "source_write": False,
                },
            )
            if reservation:
                policy_state = self.finalize_read_reservation(
                    reservation.id, "succeeded", stats=stats, source_id=quota_source_id
                )
            return SourceImportResult(
                source_id=quota_source_id,
                source_type=SOURCE_TYPE,
                spreadsheet_path=spreadsheet_path,
                rows=rows,
                duplicate_info=duplicate_info,
                snapshot=snapshot,
                read_policy=policy_state,
                stats=stats,
                worksheets=raw_worksheets,
                dataset_id=dataset.id,
                observation_id=str(observation["id"]),
            )
        except IntegrationError as exc:
            safe_error = normalize_upstream_error(exc, source="nextcloud")
            if reservation:
                self.finalize_read_reservation(
                    reservation.id, "failed", error_code="INTEGRATION_ERROR", source_id=quota_source_id
                )
            self.config.set_many(
                {
                    _LAST_READ_AT_KEY: _iso(datetime.now(timezone.utc).replace(tzinfo=None)),
                    _LAST_READ_STATUS_KEY: "failed",
                },
                updated_by="source_read",
            )
            self._record_event(
                "source_read_failed",
                "Source read failed.",
                triggered_by,
                {
                    "source_id": quota_source_id,
                    "source_type": SOURCE_TYPE,
                    "spreadsheet_path": spreadsheet_path,
                    "error": safe_error["message"],
                    "error_code": safe_error["code"],
                    "reservation_id": reservation.id if reservation else None,
                    "read_only": True,
                    "source_write": False,
                },
                severity="error",
            )
            raise UpstreamServiceError(exc, source="nextcloud") from exc
        except ValueError as exc:
            safe_message = str(exc)
            if reservation:
                self.finalize_read_reservation(
                    reservation.id, "failed", error_code="SOURCE_VALIDATION_ERROR", source_id=quota_source_id
                )
            self.config.set_many(
                {
                    _LAST_READ_AT_KEY: _iso(datetime.now(timezone.utc).replace(tzinfo=None)),
                    _LAST_READ_STATUS_KEY: "failed",
                },
                updated_by="source_read",
            )
            self._record_event(
                "source_read_failed",
                "Source read failed.",
                triggered_by,
                {
                    "source_id": quota_source_id,
                    "source_type": SOURCE_TYPE,
                    "spreadsheet_path": spreadsheet_path,
                    "error": safe_message,
                    "reservation_id": reservation.id if reservation else None,
                    "read_only": True,
                    "source_write": False,
                },
                severity="error",
            )
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, safe_message) from exc
        except Exception as exc:
            if reservation:
                self.finalize_read_reservation(
                    reservation.id, "failed", error_code=type(exc).__name__[:120], source_id=quota_source_id
                )
            self.config.set_many(
                {
                    _LAST_READ_AT_KEY: _iso(datetime.now(timezone.utc).replace(tzinfo=None)),
                    _LAST_READ_STATUS_KEY: "failed",
                },
                updated_by="source_read",
            )
            self._record_event(
                "source_read_failed",
                "Source read failed.",
                triggered_by,
                {
                    "source_id": quota_source_id,
                    "source_type": SOURCE_TYPE,
                    "spreadsheet_path": spreadsheet_path,
                    "error": _safe_error_message(exc),
                    "reservation_id": reservation.id if reservation else None,
                    "read_only": True,
                    "source_write": False,
                },
                severity="error",
            )
            raise

    def _acquisition_source(
        self,
        *,
        source_profile_id: str | None,
        triggered_by_id: str | int | None,
        worksheet: dict[str, str],
    ) -> SourceProfile:
        source = self.db.get(SourceProfile, source_profile_id) if source_profile_id else None
        if source is None:
            source = (
                self.db.query(SourceProfile)
                .filter(SourceProfile.external_source_id == self.connector_id)
                .one_or_none()
            )
        if source is not None:
            if source.external_source_id != self.connector_id or source.status != "active":
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    {"code": "source_profile_invalid", "message": "Source profile is not active Nextcloud."},
                )
            return source
        if triggered_by_id is None or not str(triggered_by_id).isdigit():
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "source_profile_required", "message": "Source profile is required."},
            )
        source = SourceProfile(
            id=str(uuid.uuid4()),
            name="Nextcloud",
            source_kind="external",
            external_source_id=self.connector_id,
            worksheet_mode=worksheet["mode"],
            worksheet_name=worksheet["name"] or None,
            data_start_row=2,
            status="active",
            version=1,
            owner_user_id=int(triggered_by_id),
        )
        try:
            self.db.add(source)
            self.db.commit()
            return source
        except IntegrityError:
            self.db.rollback()
            existing = (
                self.db.query(SourceProfile)
                .filter(SourceProfile.external_source_id == self.connector_id)
                .one_or_none()
            )
            if existing is None or existing.status != "active":
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    {"code": "source_profile_conflict", "message": "Source profile could not be established."},
                )
            return existing

    @staticmethod
    def _assessment_headers(workbook: Any, source: SourceProfile) -> list[str] | None:
        if source.worksheet_mode != "selected" or not source.worksheet_name:
            return None
        if source.worksheet_name not in workbook.sheetnames:
            raise ValueError("Selected worksheet was not found.")
        row_number = max(1, int(source.data_start_row) - 1)
        values = next(
            workbook[source.worksheet_name].iter_rows(
                min_row=row_number,
                max_row=row_number,
                values_only=True,
            ),
            None,
        )
        if values is None:
            raise ValueError("Worksheet header row was not found.")
        headers = ["" if value is None else str(value) for value in values]
        while headers and headers[-1] == "":
            headers.pop()
        return headers or None

    def manual_read_response(self, result: SourceImportResult) -> dict:
        return {
            "ok": True,
            "rows_read": result.stats["total_rows"],
            "valid_rows": result.stats["valid_rows"],
            "warning_rows": result.stats["warning_rows"],
            "error_rows": result.stats["error_rows"],
            "duplicate_rows": result.stats["duplicate_rows"],
            "last_read_at": result.read_policy["last_read_at"],
            "remaining_reads_today": result.read_policy["reads_remaining"],
            "reads_used_last_24h": result.read_policy["reads_used_last_24h"],
            "reads_remaining": result.read_policy["reads_remaining"],
            "reset_at": result.read_policy["reset_at"],
            "warnings": result.stats["warnings"],
            "errors": result.stats["errors"],
            "error_details": result.stats["error_details"],
            "source_id": result.source_id,
            "source_type": result.source_type,
            "spreadsheet_path": result.spreadsheet_path,
            "external_call_performed": True,
            "read_only": True,
            "source_write": False,
            "write_blocked": True,
        }

    def mapping(self) -> dict[str, dict[str, object]]:
        raw = _json_config(self.config.get("nextcloud.source_mapping"))
        return normalize_source_mapping(raw)

    def read_policy(self) -> dict[str, object]:
        raw = _json_config(self.config.get("nextcloud.source_read_policy"))
        return normalize_read_policy(raw)

    def worksheet_selection(self, *, source_profile_id: str | None = None) -> dict[str, str]:
        source = self.db.get(SourceProfile, source_profile_id) if source_profile_id else None
        if source is not None and source.external_source_id == self.connector_id:
            return {
                "mode": source.worksheet_mode,
                "name": str(source.worksheet_name or "").strip(),
            }
        mode = str(self.config.get("nextcloud.worksheet_mode") or "all").strip().lower()
        if mode not in {"all", "selected"}:
            mode = "all"
        return {
            "mode": mode,
            "name": str(self.config.get("nextcloud.worksheet_name") or "").strip(),
        }

    def worksheet_scope(self, *, source_profile_id: str | None = None) -> dict[str, object]:
        """Resolve the authoritative participating worksheet set.

        A v2 Source mapping is authoritative for Workspace Preview. Legacy
        connector settings are used only when no v2 mapping exists.
        """
        source = self.db.get(SourceProfile, source_profile_id) if source_profile_id else None
        if source is None and self.connector_id:
            source = (
                self.db.query(SourceProfile)
                .filter(SourceProfile.external_source_id == self.connector_id)
                .one_or_none()
            )
        mapping = (
            SourceRepository(self.db).latest_mapping(source.id)
            if source is not None
            else None
        )
        if mapping is None:
            legacy = self.worksheet_selection(source_profile_id=source_profile_id)
            return resolve_participating_worksheet_scope(
                mapping_mode=None,
                mapping_name=None,
                legacy_mode=legacy["mode"],
                legacy_name=legacy["name"],
            )

        repository = SourceRepository(self.db)
        rule_set = repository.worksheet_rule_set(mapping.id)
        enabled_rule_names = (
            [
                rule.worksheet_name
                for rule in repository.worksheet_rules(rule_set.id)
                if rule.enabled
            ]
            if rule_set is not None
            else []
        )
        return resolve_participating_worksheet_scope(
            mapping_mode=mapping.worksheet_mode,
            mapping_name=mapping.worksheet_name,
            enabled_rule_names=enabled_rule_names,
            rule_mode=rule_set.mode if rule_set is not None else None,
        )

    def read_status(self, *, source_id: str | None = None) -> dict:
        return {
            **self.read_policy_state(source_id=source_id),
            "last_read_status": self.config.get(_LAST_READ_STATUS_KEY),
            "last_row_count": _int_or_none(self.config.get(_LAST_READ_ROWS_KEY)),
            "last_warning_count": _int_or_none(self.config.get(_LAST_READ_WARNINGS_KEY)),
            "last_error_count": _int_or_none(self.config.get(_LAST_READ_ERRORS_KEY)),
        }

    def read_quota_contract(self, *, source_id: str | None = None) -> dict[str, object]:
        """Return the public read-allowance view from the durable reservation ledger."""
        state = self.read_policy_state(source_id=source_id)
        remaining = int(state["reads_remaining"])
        return {
            "enabled": bool(state["enabled"]),
            "limit": int(state["max_reads_per_24h"]),
            "usage": int(state["reads_used_last_24h"]),
            "remaining": remaining,
            "reset_at": state["reset_at"],
            "exhausted": bool(state["enabled"] and remaining <= 0),
        }

    def worksheet_discovery_state(self, *, source_id: str | None = None) -> dict[str, object]:
        """Describe whether worksheet discovery can use persisted Snapshot metadata.

        Snapshot names are reused for the exact selected workbook path. Cached
        discovery metadata is also local, but never represents a business
        Snapshot. No provider I/O occurs in this method.
        """
        spreadsheet_path = self._connector_setting("spreadsheet_path").strip()
        if not spreadsheet_path:
            return {
                "requires_remote_read": False,
                "metadata_source": "unavailable",
                "reason": "spreadsheet_not_selected",
                "snapshot_id": None,
                "snapshot_version": None,
                "snapshot_at": None,
                "worksheet_names": [],
                "worksheets": [],
            }
        snapshot = (
            self.db.query(DlSourceSnapshot)
            .filter(DlSourceSnapshot.connector_id == self.connector_id)
            .filter(DlSourceSnapshot.file_path == spreadsheet_path)
            .one_or_none()
        )
        worksheet_names = _safe_worksheet_names(snapshot.sheet_names if snapshot else None)
        cache = self.db.get(DlWorksheetDiscoveryCache, source_id) if source_id else None
        cached_worksheets = (
            list(cache.worksheets)
            if cache is not None and cache.file_path == spreadsheet_path and isinstance(cache.worksheets, list)
            else []
        )
        if snapshot is not None and worksheet_names:
            cached_by_name = {
                str(item.get("name") or ""): item
                for item in cached_worksheets
                if isinstance(item, dict)
            }
            return {
                "requires_remote_read": False,
                "metadata_source": "snapshot",
                "reason": None,
                "snapshot_id": snapshot.id,
                "snapshot_version": snapshot.version_seq,
                "snapshot_at": _iso(snapshot.snapshotted_at),
                "worksheet_names": worksheet_names,
                "worksheets": [
                    {
                        "name": name,
                        "rowCount": None,
                        **(
                            {"columns": list(cached_by_name[name].get("columns") or [])}
                            if name in cached_by_name else {}
                        ),
                    }
                    for name in worksheet_names
                ],
            }
        if cached_worksheets:
            return {
                "requires_remote_read": False,
                "metadata_source": "discovery_cache",
                "reason": None,
                "snapshot_id": None,
                "snapshot_version": None,
                "snapshot_at": None,
                "worksheet_names": [str(item.get("name") or "") for item in cached_worksheets],
                "worksheets": cached_worksheets,
                "discovered_at": _iso(cache.discovered_at),
            }
        return {
            "requires_remote_read": True,
            "metadata_source": "remote",
            "reason": "snapshot_metadata_unavailable",
            "snapshot_id": None,
            "snapshot_version": None,
            "snapshot_at": None,
            "worksheet_names": [],
            "worksheets": [],
        }

    def discovery_policy(self) -> dict[str, object]:
        raw = _json_config(self.config.get(_DISCOVERY_POLICY_KEY))
        data = raw if isinstance(raw, dict) else {}
        try:
            limit = int(data.get("max_refreshes_per_24h", DEFAULT_DISCOVERY_POLICY["max_refreshes_per_24h"]))
        except (TypeError, ValueError):
            limit = int(DEFAULT_DISCOVERY_POLICY["max_refreshes_per_24h"])
        return {
            "enabled": bool(data.get("enabled", DEFAULT_DISCOVERY_POLICY["enabled"])),
            "max_refreshes_per_24h": min(max(limit, 1), 1000),
        }

    def discovery_quota_contract(self, *, source_id: str) -> dict[str, object]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        policy = self.discovery_policy()
        reservations = (
            self.db.query(DlSourceDiscoveryReservation)
            .filter(DlSourceDiscoveryReservation.source_id == source_id)
            .filter(DlSourceDiscoveryReservation.reserved_at >= now - timedelta(hours=24))
            .all()
        )
        limit = int(policy["max_refreshes_per_24h"])
        usage = len(reservations) if policy["enabled"] else 0
        reset_at = _iso(min(item.reserved_at for item in reservations) + timedelta(hours=24)) if reservations else None
        return {
            "enabled": bool(policy["enabled"]),
            "limit": limit,
            "usage": usage,
            "remaining": max(limit - usage, 0) if policy["enabled"] else limit,
            "reset_at": reset_at,
            "exhausted": bool(policy["enabled"] and usage >= limit),
        }

    def reserve_discovery_slot(self, user_id: str, *, source_id: str) -> DlSourceDiscoveryReservation:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.commit()
        dialect = self.db.get_bind().dialect.name
        if dialect == "sqlite":
            self.db.execute(text("BEGIN IMMEDIATE"))
            self.db.execute(
                text("INSERT OR IGNORE INTO dl_source_discovery_locks (source_id, updated_at) VALUES (:source_id, :updated_at)"),
                {"source_id": source_id, "updated_at": now},
            )
        elif dialect == "postgresql":
            self.db.execute(
                text("INSERT INTO dl_source_discovery_locks (source_id, updated_at) VALUES (:source_id, :updated_at) ON CONFLICT (source_id) DO NOTHING"),
                {"source_id": source_id, "updated_at": now},
            )
        else:
            if self.db.get(DlSourceDiscoveryLock, source_id) is None:
                self.db.add(DlSourceDiscoveryLock(source_id=source_id, updated_at=now))
                self.db.flush()
        lock = self.db.query(DlSourceDiscoveryLock).filter(DlSourceDiscoveryLock.source_id == source_id).with_for_update().one()
        lock.updated_at = now
        self.db.flush()
        state = self.discovery_quota_contract(source_id=source_id)
        if state["exhausted"]:
            self.db.rollback()
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                {
                    "code": "SOURCE_DISCOVERY_LIMIT_REACHED",
                    "message": "The worksheet discovery allowance has been used.",
                    "limit": state["limit"],
                    "usage": state["usage"],
                    "reset_at": state["reset_at"],
                },
            )
        reservation = DlSourceDiscoveryReservation(
            id=f"sdr_{uuid.uuid4().hex[:20]}", source_id=source_id, user_id=str(user_id), reserved_at=now, status="reserved"
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        return reservation

    async def refresh_worksheet_discovery(
        self, *, source_profile_id: str, user_id: str | int
    ) -> dict[str, object]:
        spreadsheet_path = self._required_connector_setting("spreadsheet_path")
        username = self._connector_setting("username").strip()
        password = self._connector_setting("password")
        try:
            normalized = normalize_nextcloud_url(self._connector_setting("url"), username)
        except NextcloudUrlValidationError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"code": exc.code, "message": str(exc)}) from exc
        if not username or not password:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nextcloud source credentials are incomplete.")
        provider = NextcloudWebDavAcquisitionProvider(
            webdav_files_root_url=normalized["webdav_files_root_url"], spreadsheet_path=spreadsheet_path,
            username=normalized["username"], app_password=password, capture_contract="worksheet-metadata-v1",
        )
        http = self._nextcloud_http_client()
        reservation = self.reserve_discovery_slot(str(user_id), source_id=source_profile_id)
        try:
            # Reserve before DNS/egress preflight so every external refresh
            # attempt is covered by the separate abuse allowance.
            await http.preflight(provider.resource_url)
            worksheets, change_token = await RangedXlsxDiscovery(http).discover(
                provider.resource_url, basic_auth=(normalized["username"], password)
            )
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            cache = self.db.get(DlWorksheetDiscoveryCache, source_profile_id)
            if cache is None:
                cache = DlWorksheetDiscoveryCache(source_id=source_profile_id)
                self.db.add(cache)
            cache.file_path = spreadsheet_path
            cache.provider_change_token = change_token
            cache.worksheets = worksheets
            cache.metadata_checksum = checksum(worksheets)
            cache.discovered_at = now
            reservation.status = "succeeded"
            reservation.completed_at = now
            self.db.commit()
            return {
                "worksheets": worksheets,
                "discovered_at": _iso(now),
                "change_token": change_token,
                "quota": self.discovery_quota_contract(source_id=source_profile_id),
            }
        except (XlsxDiscoveryError, SourceHttpError) as exc:
            reservation.status = "failed"
            reservation.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            reservation.error_code = getattr(exc, "code", type(exc).__name__)[:120]
            self.db.commit()
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"code": reservation.error_code, "message": "Worksheet metadata refresh could not be completed without a full workbook acquisition."},
            ) from exc

    def read_policy_state(self, *, source_id: str | None = None, now: datetime | None = None) -> dict:
        source_id = self._quota_source_id(source_id, required=False)
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        policy = self.read_policy()
        reservations = [] if source_id is None else (
            self.db.query(DlSourceReadReservation)
            .filter(DlSourceReadReservation.source_id == source_id)
            .filter(DlSourceReadReservation.reserved_at >= now - timedelta(hours=24))
            .all()
        )
        max_reads = int(policy["max_reads_per_24h"])
        used = len(reservations) if policy["enabled"] else 0
        reset_at = None
        timestamps = [row.reserved_at for row in reservations]
        if timestamps:
            reset_at = _iso(min(timestamps) + timedelta(hours=24))
        return {
            "enabled": bool(policy["enabled"]),
            "max_reads_per_24h": max_reads,
            "manual_read_allowed": bool(policy["manual_read_allowed"]),
            "reads_used_last_24h": used,
            "reads_remaining": max(max_reads - used, 0) if policy["enabled"] else max_reads,
            "reset_at": reset_at,
            "last_read_at": self.config.get(_LAST_READ_AT_KEY),
        }

    def check_read_allowed(self, *, manual: bool, source_id: str | None = None) -> dict:
        state = self.read_policy_state(source_id=source_id)
        if manual and not state["manual_read_allowed"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Manual source read is disabled by source read policy.")
        if state["enabled"] and state["reads_remaining"] <= 0:
            raise _source_read_limit_exception(state)
        return state

    def reserve_read_slot(
        self, user_id: str, *, manual: bool, source_id: str | None = None
    ) -> DlSourceReadReservation:
        """Reserve atomically before outbound access.

        Every committed reservation consumes the rolling quota, including a
        failed outbound attempt. Configuration validation happens before this
        method, so local validation failures do not consume a slot.
        """
        source_id = self._quota_source_id(source_id)
        policy = self.read_policy()
        if manual and not policy["manual_read_allowed"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Manual source read is disabled by source read policy.")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.commit()
        dialect = self.db.get_bind().dialect.name
        if dialect == "sqlite":
            self.db.execute(text("BEGIN IMMEDIATE"))
            self.db.execute(
                text("INSERT OR IGNORE INTO dl_source_read_locks (source_id, updated_at) VALUES (:source_id, :updated_at)"),
                {"source_id": source_id, "updated_at": now},
            )
        elif dialect == "postgresql":
            self.db.execute(
                text(
                    "INSERT INTO dl_source_read_locks (source_id, updated_at) VALUES (:source_id, :updated_at) "
                    "ON CONFLICT (source_id) DO NOTHING"
                ),
                {"source_id": source_id, "updated_at": now},
            )
        elif dialect in {"mysql", "mariadb"}:
            self.db.execute(
                text("INSERT IGNORE INTO dl_source_read_locks (source_id, updated_at) VALUES (:source_id, :updated_at)"),
                {"source_id": source_id, "updated_at": now},
            )
        else:
            if self.db.get(DlSourceReadLock, source_id) is None:
                self.db.add(DlSourceReadLock(source_id=source_id, updated_at=now))
                self.db.flush()

        lock = (
            self.db.query(DlSourceReadLock)
            .filter(DlSourceReadLock.source_id == source_id)
            .with_for_update()
            .one()
        )
        lock.updated_at = now
        self.db.flush()

        state = self.read_policy_state(source_id=source_id, now=now)
        if state["enabled"] and state["reads_remaining"] <= 0:
            error = _source_read_limit_exception(state, now=now)
            self.db.rollback()
            raise error

        reservation = DlSourceReadReservation(
            id=f"srr_{uuid.uuid4().hex[:20]}",
            source_id=source_id,
            user_id=str(user_id),
            reserved_at=now,
            status="reserved",
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        self._record_event(
            "source_read_reserved",
            "Source read quota slot reserved before outbound access.",
            str(user_id),
            {"source_id": source_id, "reservation_id": reservation.id, "reservation_status": "reserved"},
        )
        return reservation

    def finalize_read_reservation(
        self,
        reservation_id: str,
        final_status: str,
        *,
        stats: dict | None = None,
        error_code: str | None = None,
        source_id: str | None = None,
    ) -> dict:
        self.db.rollback()
        reservation = self.db.get(DlSourceReadReservation, reservation_id)
        if reservation is None:
            raise RuntimeError("Source read reservation is missing.")
        if source_id is not None and reservation.source_id != source_id:
            raise RuntimeError("Source read reservation belongs to another Source profile.")
        if reservation.status == "reserved":
            reservation.status = final_status
            reservation.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            reservation.error_code = error_code
            self.db.commit()

        values = {
            _LAST_READ_AT_KEY: _iso(reservation.completed_at or datetime.now(timezone.utc).replace(tzinfo=None)),
            _LAST_READ_STATUS_KEY: (
                "failed" if final_status == "failed" else "completed_with_errors" if stats and stats["error_rows"] else "completed"
            ),
        }
        if stats:
            values.update({
                _LAST_READ_ROWS_KEY: str(stats["total_rows"]),
                _LAST_READ_WARNINGS_KEY: str(stats["warning_rows"]),
                _LAST_READ_ERRORS_KEY: str(stats["error_rows"]),
            })
        self.config.set_many(
            values,
            updated_by="source_read",
        )
        self._record_event(
            "source_read_reservation_finalized",
            "Source read reservation finalized.",
            reservation.user_id,
            {
                "source_id": reservation.source_id,
                "reservation_id": reservation.id,
                "reservation_status": final_status,
                "error_code": error_code,
            },
            severity="error" if final_status == "failed" else "info",
        )
        return self.read_policy_state(
            source_id=reservation.source_id,
            now=reservation.completed_at or datetime.now(timezone.utc).replace(tzinfo=None),
        )

    def _quota_source_id(self, source_id: str | None, *, required: bool = True) -> str | None:
        if source_id:
            return source_id
        profile_id = (
            self.db.query(SourceProfile.id)
            .filter(SourceProfile.external_source_id == self.connector_id)
            .scalar()
        )
        if profile_id:
            return str(profile_id)
        if not required:
            return None
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "source_profile_required", "message": "Source profile is required."},
        )

    def _nextcloud_http_client(self) -> SourceHttpClient:
        networks = parse_trusted_private_networks(
            self.config.get("nextcloud.trusted_private_networks")
        )
        return self.source_http_client.with_allowed_private_networks(networks)

    def _connector_setting(self, key: str) -> str:
        # The primary identity is the explicit compatibility boundary for the
        # pre-v2 AppConfig-backed connector. Independent replacements never
        # read through this singleton namespace.
        if self.connector_id == SOURCE_ID:
            return str(self.config.get(f"nextcloud.{key}") or "")
        connector = self.db.get(IntegrationConnectorInstance, self.connector_id)
        if connector is not None:
            setting = next(
                (
                    item
                    for item in connector.settings
                    if item.key == key and item.configured
                ),
                None,
            )
            if setting is not None:
                if setting.secret:
                    scoped_secret = self.config.get(
                        f"connector_secret.{self.connector_id}.{key}"
                    )
                    if scoped_secret is not None:
                        return str(scoped_secret)
                return str(setting.value_json or "")
        return ""

    def _required_connector_setting(self, key: str) -> str:
        value = self._connector_setting(key)
        if not value:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Missing required setting: {key}",
            )
        return value

    def _persist_observation_dataset(
        self,
        *,
        observation_id: str,
        source_id: str,
        resource_scope: str,
        binding_fingerprint: str,
        source_snapshot: DlSourceSnapshot,
        workbook_checksum: str,
        worksheets: dict[str, list[list[Any]]],
    ) -> SourceObservationDataset:
        """Retain one immutable, JSON-safe worksheet dataset per Observation."""

        normalized = [
            {
                "name": worksheet_name,
                "order": worksheet_order,
                "rows": [
                    [_json_safe_source_cell(value) for value in row]
                    for row in worksheet_rows
                ],
            }
            for worksheet_order, (worksheet_name, worksheet_rows) in enumerate(
                worksheets.items(), start=1
            )
        ]
        expected_rows = [
            {
                **item,
                "checksum": checksum(
                    {
                        "worksheetName": item["name"],
                        "worksheetOrder": item["order"],
                        "rows": item["rows"],
                    }
                ),
            }
            for item in normalized
        ]
        existing = (
            self.db.query(SourceObservationDataset)
            .filter(SourceObservationDataset.observation_id == observation_id)
            .one_or_none()
        )
        if existing is not None:
            self._assert_observation_dataset_replay(
                existing,
                source_id=source_id,
                resource_scope=resource_scope,
                binding_fingerprint=binding_fingerprint,
                source_snapshot=source_snapshot,
                workbook_checksum=workbook_checksum,
                expected_rows=expected_rows,
            )
            return existing

        dataset = SourceObservationDataset(
            id=str(uuid.uuid4()),
            observation_id=observation_id,
            source_id=source_id,
            resource_scope=resource_scope,
            binding_fingerprint=binding_fingerprint,
            parser_version=SOURCE_DATASET_PARSER_VERSION,
            formula_evaluation_version=SOURCE_DATASET_FORMULA_EVALUATION_VERSION,
            source_snapshot_id=int(source_snapshot.id),
            source_snapshot_version=int(source_snapshot.version_seq or 1),
            workbook_checksum=workbook_checksum,
            row_count=sum(len(item["rows"]) for item in expected_rows),
            worksheet_count=len(expected_rows),
        )
        try:
            self.db.add(dataset)
            self.db.flush()
            for item in expected_rows:
                self.db.add(
                    SourceObservationWorksheetDataset(
                        id=str(uuid.uuid4()),
                        dataset_id=dataset.id,
                        worksheet_name=str(item["name"]),
                        worksheet_order=int(item["order"]),
                        rows_json=item["rows"],
                        row_count=len(item["rows"]),
                        checksum=str(item["checksum"]),
                    )
                )
            self.db.commit()
        except IntegrityError:
            # An idempotent/concurrent replay may have inserted the immutable
            # Observation dataset after the initial lookup.
            self.db.rollback()
            existing = (
                self.db.query(SourceObservationDataset)
                .filter(SourceObservationDataset.observation_id == observation_id)
                .one_or_none()
            )
            if existing is None:
                raise
            self._assert_observation_dataset_replay(
                existing,
                source_id=source_id,
                resource_scope=resource_scope,
                binding_fingerprint=binding_fingerprint,
                source_snapshot=source_snapshot,
                workbook_checksum=workbook_checksum,
                expected_rows=expected_rows,
            )
            return existing
        except Exception:
            self.db.rollback()
            raise
        self.db.refresh(dataset)
        return dataset

    def _assert_observation_dataset_replay(
        self,
        dataset: SourceObservationDataset,
        *,
        source_id: str,
        resource_scope: str,
        binding_fingerprint: str,
        source_snapshot: DlSourceSnapshot,
        workbook_checksum: str,
        expected_rows: list[dict[str, Any]],
    ) -> None:
        stored_rows = (
            self.db.query(SourceObservationWorksheetDataset)
            .filter(SourceObservationWorksheetDataset.dataset_id == dataset.id)
            .order_by(SourceObservationWorksheetDataset.worksheet_order)
            .all()
        )
        expected_identity = [
            (
                str(item["name"]),
                int(item["order"]),
                len(item["rows"]),
                str(item["checksum"]),
                item["rows"],
            )
            for item in expected_rows
        ]
        stored_identity = [
            (
                item.worksheet_name,
                item.worksheet_order,
                item.row_count,
                item.checksum,
                item.rows_json,
            )
            for item in stored_rows
        ]
        if (
            dataset.source_id != source_id
            or dataset.resource_scope != resource_scope
            or dataset.binding_fingerprint != binding_fingerprint
            or dataset.parser_version != SOURCE_DATASET_PARSER_VERSION
            or dataset.formula_evaluation_version
            != SOURCE_DATASET_FORMULA_EVALUATION_VERSION
            or dataset.source_snapshot_id != int(source_snapshot.id)
            or dataset.source_snapshot_version > int(source_snapshot.version_seq or 1)
            or dataset.workbook_checksum != workbook_checksum
            or dataset.row_count != sum(len(item["rows"]) for item in expected_rows)
            or dataset.worksheet_count != len(expected_rows)
            or stored_identity != expected_identity
        ):
            raise RuntimeError("Source Observation dataset replay conflict.")

    def _upsert_source_snapshot(
        self,
        *,
        file_path: str,
        content: bytes,
        file_meta: dict[str, str | None],
        sheet_names: list[str],
        row_count: int,
        duplicate_count: int,
        invalid_row_count: int,
    ) -> DlSourceSnapshot:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        integrity_hash = hashlib.sha256(content).hexdigest()
        snapshot = (
            self.db.query(DlSourceSnapshot)
            .filter(DlSourceSnapshot.connector_id == self.connector_id)
            .filter(DlSourceSnapshot.file_path == file_path)
            .one_or_none()
        )
        if snapshot is None:
            snapshot = DlSourceSnapshot(
                connector_id=self.connector_id,
                file_path=file_path,
                version_seq=1,
                snapshotted_at=now,
            )
            self.db.add(snapshot)
        else:
            snapshot.version_seq = (snapshot.version_seq or 0) + 1
            snapshot.snapshotted_at = now
        snapshot.etag = file_meta.get("etag")
        snapshot.last_modified = file_meta.get("last_modified")
        snapshot.parsed_row_count = row_count
        snapshot.duplicate_count = duplicate_count
        snapshot.invalid_row_count = invalid_row_count
        snapshot.integrity_hash = integrity_hash
        snapshot.sheet_names = sheet_names
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def _record_event(
        self,
        event_name: str,
        message: str,
        actor: str,
        metadata: dict,
        *,
        severity: str = "info",
    ) -> None:
        self.integration.record_event(
            connector_id=self.connector_id,
            event_name=event_name,
            message=message,
            severity=severity,
            metadata={**metadata, "actor": actor, "timestamp": _iso(datetime.now(timezone.utc).replace(tzinfo=None))},
        )


def source_row_stats(rows: list[dict], duplicate_info: dict) -> dict:
    warnings: list[str] = []
    errors: list[str] = []
    error_details: list[dict[str, str]] = []
    for product_id in duplicate_info.get("duplicate_product_ids", []):
        errors.append(f"Duplicate product ID in spreadsheet: {product_id}")
    for sku in duplicate_info.get("duplicate_skus", []):
        errors.append(f"Duplicate SKU in spreadsheet: {sku}")
    for row in rows:
        for item in row.get("row_warnings") or []:
            if item not in warnings:
                warnings.append(str(item))
        for item in row.get("row_errors") or []:
            if item not in errors:
                errors.append(str(item))
        for detail in row.get("row_error_details") or []:
            if isinstance(detail, dict) and detail not in error_details:
                error_details.append({
                    "code": str(detail.get("code") or "SOURCE_ROW_INVALID"),
                    "message": str(detail.get("message") or "Source row is invalid."),
                })
    error_rows = sum(1 for row in rows if row.get("row_errors"))
    warning_rows = sum(1 for row in rows if not row.get("row_errors") and row.get("row_warnings"))
    valid_rows = len(rows) - error_rows - warning_rows
    duplicate_rows = sum(
        1 for row in rows if row.get("duplicate_product_id") or row.get("duplicate_sku")
    )
    return {
        "total_rows": len(rows),
        "valid_rows": valid_rows,
        "warning_rows": warning_rows,
        "error_rows": error_rows,
        "duplicate_rows": duplicate_rows,
        "duplicate_rows_are_error_subset": True,
        "warnings": warnings,
        "errors": errors,
        "error_details": error_details,
    }


def normalize_source_mapping(raw: object | None) -> dict[str, dict[str, object]]:
    data = raw if isinstance(raw, dict) else {}
    normalized: dict[str, dict[str, object]] = {}
    for field, defaults in DEFAULT_SOURCE_MAPPING.items():
        item = data.get(field) if isinstance(data.get(field), dict) else {}
        enabled = bool(item.get("enabled", defaults["enabled"]))
        column = str(item.get("column", defaults["column"]) or "").strip()
        if enabled and not column:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{field} column is required when enabled.")
        if column:
            column = normalize_column_reference(column)
        normalized[field] = {"enabled": enabled, "column": column}
    enabled_columns: dict[str, str] = {}
    for field, item in normalized.items():
        if not item["enabled"]:
            continue
        column_key = str(item["column"]).casefold()
        previous = enabled_columns.get(column_key)
        if previous:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Duplicate enabled source mapping column: {item['column']}.")
        enabled_columns[column_key] = field
    return normalized


def normalize_read_policy(raw: object | None) -> dict[str, object]:
    data = raw if isinstance(raw, dict) else {}
    enabled = bool(data.get("enabled", DEFAULT_READ_POLICY["enabled"]))
    manual_allowed = bool(data.get("manual_read_allowed", DEFAULT_READ_POLICY["manual_read_allowed"]))
    try:
        max_reads = int(data.get("max_reads_per_24h", DEFAULT_READ_POLICY["max_reads_per_24h"]))
    except (TypeError, ValueError):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "max_reads_per_24h must be a positive integer.",
        ) from None
    if max_reads < 1 or max_reads > 1000:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "max_reads_per_24h must be between 1 and 1000.")
    return {
        "enabled": enabled,
        "max_reads_per_24h": max_reads,
        "manual_read_allowed": manual_allowed,
    }


def normalize_column_reference(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _COLUMN_REF_RE.fullmatch(text):
        return text.upper()
    if _HEADER_REF_RE.fullmatch(text):
        return " ".join(text.split())
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid column reference.")


def serialize_source_mapping(mapping: dict[str, dict[str, object]]) -> str:
    return json.dumps(mapping, sort_keys=True)


def serialize_read_policy(policy: dict[str, object]) -> str:
    return json.dumps(policy, sort_keys=True)


def _json_safe_source_cell(value: Any) -> str | int | float | bool | None:
    """Normalize spreadsheet scalars without collapsing physical null cells."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        if math.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    return str(value)


def _json_config(value: str | None) -> object | None:
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _recent_history(value: str | None, now: datetime) -> list[datetime]:
    raw = _json_config(value)
    if not isinstance(raw, list):
        return []
    cutoff = now - timedelta(hours=24)
    history: list[datetime] = []
    for item in raw:
        try:
            parsed = datetime.fromisoformat(str(item).replace("Z", ""))
        except ValueError:
            continue
        if parsed >= cutoff:
            history.append(parsed)
    return sorted(history)


def _source_read_limit_exception(state: dict, *, now: datetime | None = None) -> HTTPException:
    current = now or datetime.now(timezone.utc).replace(tzinfo=None)
    reset_at = str(state.get("reset_at") or "") or None
    retry_after = 0
    if reset_at:
        try:
            reset_time = datetime.fromisoformat(reset_at.replace("Z", ""))
            retry_after = max(1, math.ceil((reset_time - current).total_seconds()))
        except ValueError:
            retry_after = 0
    detail = {
        "code": "SOURCE_READ_LIMIT_REACHED",
        "message": "The source read allowance has been used.",
        "limit": int(state.get("max_reads_per_24h") or 0),
        "usage": int(state.get("reads_used_last_24h") or 0),
        "reset_at": reset_at,
        "retry_after_seconds": retry_after or None,
    }
    headers = {"Retry-After": str(retry_after)} if retry_after else None
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail, headers=headers)


def _iso(value: datetime) -> str:
    return value.isoformat() + "Z"


def _int_or_none(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _safe_worksheet_names(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for item in value:
        name = str(item or "").strip()
        if not name or len(name) > 240 or name in seen:
            continue
        names.append(name)
        seen.add(name)
    return names


def _safe_error_message(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return str(exc)[:200] or type(exc).__name__
