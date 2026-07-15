"""Persistence adapters for source-centric workspace resources."""

from __future__ import annotations

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session, aliased

from app.flowhub.source_workspace.models import (
    FlowHubSheet,
    SheetCell,
    SheetColumn,
    SheetRevision,
    SheetRow,
    SourceChannelFieldMapping,
    SourceChannelMapping,
    SourceDataQualityIssue,
    SourceDataQualityScan,
    SourceDataQualityScanSource,
    SourceFieldMapping,
    SourceMappingRevision,
    SourceProfile,
    SourceWorksheetChannelFieldMapping,
    SourceWorksheetChannelMapping,
    SourceWorksheetFieldMapping,
    SourceWorksheetRule,
    SourceWorksheetRuleSet,
)


class SourceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, source_id: str) -> SourceProfile | None:
        return self.db.get(SourceProfile, source_id)

    def list_for_user(self, user_id: int) -> list[SourceProfile]:
        return (
            self.db.query(SourceProfile)
            .filter(SourceProfile.owner_user_id == user_id)
            .order_by(SourceProfile.created_at.desc(), SourceProfile.id)
            .all()
        )

    def latest_mapping(self, source_id: str) -> SourceMappingRevision | None:
        return (
            self.db.query(SourceMappingRevision)
            .filter(SourceMappingRevision.source_id == source_id)
            .order_by(SourceMappingRevision.version.desc())
            .first()
        )

    def source_fields(self, revision_id: str) -> list[SourceFieldMapping]:
        return (
            self.db.query(SourceFieldMapping)
            .filter(SourceFieldMapping.mapping_revision_id == revision_id)
            .order_by(SourceFieldMapping.field)
            .all()
        )

    def channel_mappings(self, revision_id: str) -> list[SourceChannelMapping]:
        return (
            self.db.query(SourceChannelMapping)
            .filter(SourceChannelMapping.mapping_revision_id == revision_id)
            .order_by(SourceChannelMapping.channel_id)
            .all()
        )

    def channel_fields(self, channel_mapping_ids: list[str]) -> list[SourceChannelFieldMapping]:
        if not channel_mapping_ids:
            return []
        return (
            self.db.query(SourceChannelFieldMapping)
            .filter(SourceChannelFieldMapping.channel_mapping_id.in_(channel_mapping_ids))
            .order_by(SourceChannelFieldMapping.channel_mapping_id, SourceChannelFieldMapping.field)
            .all()
        )

    def worksheet_rule_set(self, revision_id: str) -> SourceWorksheetRuleSet | None:
        return (
            self.db.query(SourceWorksheetRuleSet)
            .filter(SourceWorksheetRuleSet.mapping_revision_id == revision_id)
            .first()
        )

    def worksheet_rules(self, rule_set_id: str) -> list[SourceWorksheetRule]:
        return (
            self.db.query(SourceWorksheetRule)
            .filter(SourceWorksheetRule.rule_set_id == rule_set_id)
            .order_by(SourceWorksheetRule.worksheet_name)
            .all()
        )

    def worksheet_fields(self, rule_ids: list[str]) -> list[SourceWorksheetFieldMapping]:
        if not rule_ids:
            return []
        return (
            self.db.query(SourceWorksheetFieldMapping)
            .filter(SourceWorksheetFieldMapping.worksheet_rule_id.in_(rule_ids))
            .order_by(SourceWorksheetFieldMapping.worksheet_rule_id, SourceWorksheetFieldMapping.field)
            .all()
        )

    def worksheet_channels(self, rule_ids: list[str]) -> list[SourceWorksheetChannelMapping]:
        if not rule_ids:
            return []
        return (
            self.db.query(SourceWorksheetChannelMapping)
            .filter(SourceWorksheetChannelMapping.worksheet_rule_id.in_(rule_ids))
            .order_by(SourceWorksheetChannelMapping.worksheet_rule_id, SourceWorksheetChannelMapping.channel_id)
            .all()
        )

    def worksheet_channel_fields(
        self, channel_mapping_ids: list[str]
    ) -> list[SourceWorksheetChannelFieldMapping]:
        if not channel_mapping_ids:
            return []
        return (
            self.db.query(SourceWorksheetChannelFieldMapping)
            .filter(
                SourceWorksheetChannelFieldMapping.worksheet_channel_mapping_id.in_(
                    channel_mapping_ids
                )
            )
            .order_by(
                SourceWorksheetChannelFieldMapping.worksheet_channel_mapping_id,
                SourceWorksheetChannelFieldMapping.field,
            )
            .all()
        )


class SheetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, sheet_id: str) -> FlowHubSheet | None:
        return self.db.get(FlowHubSheet, sheet_id)

    def for_source(self, source_id: str) -> FlowHubSheet | None:
        return self.db.query(FlowHubSheet).filter(FlowHubSheet.source_id == source_id).first()

    def revision(self, revision_id: str) -> SheetRevision | None:
        return self.db.get(SheetRevision, revision_id)

    def latest_revision(self, sheet_id: str) -> SheetRevision | None:
        return (
            self.db.query(SheetRevision)
            .filter(SheetRevision.sheet_id == sheet_id)
            .order_by(SheetRevision.version.desc())
            .first()
        )

    def columns(self, revision_id: str) -> list[SheetColumn]:
        return (
            self.db.query(SheetColumn)
            .filter(SheetColumn.revision_id == revision_id)
            .order_by(SheetColumn.position)
            .all()
        )

    def rows(
        self,
        revision_id: str,
        *,
        offset: int,
        limit: int,
        search: str | None = None,
        sort_column: str | None = None,
        sort_direction: str = "asc",
    ) -> tuple[list[SheetRow], int]:
        query = self.db.query(SheetRow).filter(SheetRow.revision_id == revision_id)
        if search:
            matching_cell = aliased(SheetCell)
            query = query.filter(
                self.db.query(matching_cell.id)
                .filter(
                    matching_cell.revision_id == revision_id,
                    matching_cell.row_id == SheetRow.id,
                    or_(
                        matching_cell.calculated_value.ilike(f"%{search}%"),
                        matching_cell.raw_value.ilike(f"%{search}%"),
                    ),
                )
                .exists()
            )
        total = query.count()
        if sort_column:
            sort_cell = aliased(SheetCell)
            query = query.outerjoin(
                sort_cell,
                (sort_cell.revision_id == revision_id)
                & (sort_cell.row_id == SheetRow.id)
                & (sort_cell.column_key == sort_column),
            )
            ordering = sort_cell.calculated_value.desc() if sort_direction == "desc" else sort_cell.calculated_value.asc()
            query = query.order_by(ordering, SheetRow.position, SheetRow.id)
        else:
            query = query.order_by(SheetRow.position, SheetRow.id)
        return (
            query.offset(offset).limit(limit).all(),
            total,
        )

    def all_rows(self, revision_id: str) -> list[SheetRow]:
        return (
            self.db.query(SheetRow)
            .filter(SheetRow.revision_id == revision_id)
            .order_by(SheetRow.position)
            .all()
        )

    def cells(self, revision_id: str, row_ids: list[str]) -> list[SheetCell]:
        if not row_ids:
            return []
        return (
            self.db.query(SheetCell)
            .filter(SheetCell.revision_id == revision_id, SheetCell.row_id.in_(row_ids))
            .all()
        )


class DataQualityRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        user_id: int,
        scan_id: str,
        source_id: str | None,
        channel_id: str | None,
        worksheet: str | None,
        category: str | None,
        severity: str | None,
        product: str | None,
        mapping_state: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[SourceDataQualityIssue], int, dict[str, int]]:
        query = self.db.query(SourceDataQualityIssue).join(
            SourceDataQualityScan,
            SourceDataQualityScan.id == SourceDataQualityIssue.scan_id,
        ).filter(
            SourceDataQualityScan.owner_user_id == user_id,
            SourceDataQualityIssue.scan_id == scan_id,
        )
        if source_id:
            query = query.filter(SourceDataQualityIssue.source_id == source_id)
        if channel_id:
            query = query.filter(SourceDataQualityIssue.channel_id == channel_id)
        if worksheet:
            query = query.filter(SourceDataQualityIssue.worksheet_name == worksheet)
        if category:
            query = query.filter(SourceDataQualityIssue.category == category)
        if severity:
            query = query.filter(SourceDataQualityIssue.severity == severity)
        if product:
            query = query.filter(SourceDataQualityIssue.source_product_name.ilike(f"%{product}%"))
        if mapping_state:
            query = query.filter(SourceDataQualityIssue.mapping_state == mapping_state)
        total = query.count()
        category_counts = {
            str(category): int(count)
            for category, count in query.with_entities(
                SourceDataQualityIssue.category,
                func.count(SourceDataQualityIssue.id),
            )
            .group_by(SourceDataQualityIssue.category)
            .all()
        }
        severity_priority = case(
            (SourceDataQualityIssue.severity == "blocked", 0),
            (SourceDataQualityIssue.severity == "error", 1),
            (SourceDataQualityIssue.severity == "warning", 2),
            else_=3,
        )
        return (
            query.order_by(
                severity_priority.asc(),
                SourceDataQualityIssue.created_at.desc(),
                SourceDataQualityIssue.id.asc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all(),
            total,
            category_counts,
        )

    def latest_scan(
        self, *, user_id: int, source_id: str | None
    ) -> SourceDataQualityScan | None:
        query = self.db.query(SourceDataQualityScan).filter(
            SourceDataQualityScan.owner_user_id == user_id
        )
        if source_id is None:
            query = query.filter(SourceDataQualityScan.source_id.is_(None))
        else:
            query = query.join(
                SourceDataQualityScanSource,
                SourceDataQualityScanSource.scan_id == SourceDataQualityScan.id,
            ).filter(SourceDataQualityScanSource.source_id == source_id)
        return (
            query.order_by(
                SourceDataQualityScan.created_at.desc(),
                SourceDataQualityScan.id.desc(),
            )
            .limit(1)
            .one_or_none()
        )

    def previous_completed_scan(
        self,
        *,
        user_id: int,
        source_id: str | None,
        exclude_scan_id: str,
    ) -> SourceDataQualityScan | None:
        query = self.db.query(SourceDataQualityScan).filter(
            SourceDataQualityScan.owner_user_id == user_id,
            SourceDataQualityScan.status == "completed",
            SourceDataQualityScan.id != exclude_scan_id,
        )
        if source_id is None:
            query = query.filter(SourceDataQualityScan.source_id.is_(None))
        else:
            query = query.join(
                SourceDataQualityScanSource,
                SourceDataQualityScanSource.scan_id == SourceDataQualityScan.id,
            ).filter(SourceDataQualityScanSource.source_id == source_id)
        return (
            query.order_by(
                SourceDataQualityScan.checked_at.desc(),
                SourceDataQualityScan.id.desc(),
            )
            .limit(1)
            .one_or_none()
        )

    def issue_identity_keys(
        self, scan_id: str, *, source_id: str | None = None
    ) -> set[tuple[str, str, str, str, str, str, str, str]]:
        query = self.db.query(
            SourceDataQualityIssue.source_id,
            SourceDataQualityIssue.worksheet_name,
            SourceDataQualityIssue.source_row_key,
            SourceDataQualityIssue.source_product_name,
            SourceDataQualityIssue.channel_id,
            SourceDataQualityIssue.mapping_state,
            SourceDataQualityIssue.category,
            SourceDataQualityIssue.code,
        ).filter(SourceDataQualityIssue.scan_id == scan_id)
        if source_id is not None:
            query = query.filter(SourceDataQualityIssue.source_id == source_id)
        return {
            (
                str(issue_source_id or ""),
                str(worksheet_name or ""),
                str(source_row_key or ""),
                str(source_product_name or ""),
                str(channel_id or ""),
                str(mapping_state or ""),
                str(category or ""),
                str(code or ""),
            )
            for (
                issue_source_id,
                worksheet_name,
                source_row_key,
                source_product_name,
                channel_id,
                mapping_state,
                category,
                code,
            ) in query.all()
        }

    def categories(self, scan_id: str, *, source_id: str | None = None) -> dict[str, int]:
        query = self.db.query(
            SourceDataQualityIssue.category,
            func.count(SourceDataQualityIssue.id),
        ).filter(SourceDataQualityIssue.scan_id == scan_id)
        if source_id is not None:
            query = query.filter(SourceDataQualityIssue.source_id == source_id)
        return {
            str(category): int(count)
            for category, count in query.group_by(SourceDataQualityIssue.category).all()
        }
