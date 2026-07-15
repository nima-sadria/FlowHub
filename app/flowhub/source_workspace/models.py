"""Normalized persistence for source mappings and internal FlowHub Sheets."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.flowhub.database import FlowHubBase
from app.flowhub.unified_workspace.domain import utcnow


class SourceProfile(FlowHubBase):
    __tablename__ = "sc_sources"
    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('flowhub_sheet','imported_sheet','external')",
            name="ck_sc_source_kind",
        ),
        CheckConstraint("status IN ('active','disabled')", name="ck_sc_source_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    external_source_id: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    worksheet_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="selected")
    worksheet_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    data_start_row: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SourceMappingRevision(FlowHubBase):
    __tablename__ = "sc_source_mapping_revisions"
    __table_args__ = (
        UniqueConstraint("source_id", "version", name="uq_sc_mapping_revision_version"),
        UniqueConstraint("source_id", "checksum", name="uq_sc_mapping_revision_checksum"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    worksheet_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    worksheet_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    data_start_row: Mapped[int] = mapped_column(Integer, nullable=False)
    value_policy_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SourceFieldMapping(FlowHubBase):
    __tablename__ = "sc_source_field_mappings"
    __table_args__ = (
        UniqueConstraint("mapping_revision_id", "field", name="uq_sc_source_field_mapping"),
        CheckConstraint(
            "field IN ('name','source_key','category','brand','cost')",
            name="ck_sc_source_field",
        ),
        CheckConstraint(
            "reference_type IN ('column_letter','header_name','column_id','disabled')",
            name="ck_sc_source_reference_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mapping_revision_id: Mapped[str] = mapped_column(
        ForeignKey("sc_source_mapping_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    field: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_value: Mapped[str | None] = mapped_column(String(240), nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SourceChannelMapping(FlowHubBase):
    __tablename__ = "sc_source_channel_mappings"
    __table_args__ = (
        UniqueConstraint("mapping_revision_id", "channel_id", name="uq_sc_channel_mapping"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mapping_revision_id: Mapped[str] = mapped_column(
        ForeignKey("sc_source_mapping_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    worksheet_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SourceChannelFieldMapping(FlowHubBase):
    __tablename__ = "sc_source_channel_field_mappings"
    __table_args__ = (
        UniqueConstraint("channel_mapping_id", "field", name="uq_sc_channel_field_mapping"),
        CheckConstraint(
            "field IN ('external_id','price','stock','status')", name="ck_sc_channel_field"
        ),
        CheckConstraint(
            "reference_type IN ('column_letter','header_name','column_id','disabled')",
            name="ck_sc_channel_reference_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_mapping_id: Mapped[str] = mapped_column(
        ForeignKey("sc_source_channel_mappings.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    field: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_value: Mapped[str | None] = mapped_column(String(240), nullable=True)


class SourceWorksheetRuleSet(FlowHubBase):
    """Immutable worksheet-scoping policy owned by one Mapping revision."""

    __tablename__ = "sc_source_worksheet_rule_sets"
    __table_args__ = (
        UniqueConstraint(
            "mapping_revision_id",
            name="uq_sc_worksheet_rule_set_revision",
        ),
        CheckConstraint("mode IN ('shared','per_worksheet')", name="ck_sc_worksheet_rule_mode"),
        CheckConstraint(
            "duplicate_product_policy IN ('block','last_sheet_wins')",
            name="ck_sc_worksheet_duplicate_policy",
        ),
        Index("ix_sc_worksheet_rule_set_revision", "mapping_revision_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    mapping_revision_id: Mapped[str] = mapped_column(
        ForeignKey("sc_source_mapping_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(String(30), nullable=False)
    duplicate_product_policy: Mapped[str] = mapped_column(String(30), nullable=False)
    sealed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SourceWorksheetRule(FlowHubBase):
    """One immutable set of Source rules for a workbook worksheet."""

    __tablename__ = "sc_source_worksheet_rules"
    __table_args__ = (
        UniqueConstraint("rule_set_id", "worksheet_name", name="uq_sc_worksheet_rule_name"),
        Index("ix_sc_worksheet_rule_set", "rule_set_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rule_set_id: Mapped[str] = mapped_column(
        ForeignKey("sc_source_worksheet_rule_sets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    worksheet_name: Mapped[str] = mapped_column(String(240), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    data_start_row: Mapped[int] = mapped_column(Integer, nullable=False)
    value_policy_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class SourceWorksheetFieldMapping(FlowHubBase):
    __tablename__ = "sc_source_worksheet_fields"
    __table_args__ = (
        UniqueConstraint("worksheet_rule_id", "field", name="uq_sc_worksheet_source_field"),
        CheckConstraint(
            "field IN ('name','source_key','category','brand','cost')",
            name="ck_sc_worksheet_source_field",
        ),
        CheckConstraint(
            "reference_type IN ('column_letter','header_name','column_id','disabled')",
            name="ck_sc_worksheet_source_reference_type",
        ),
        Index("ix_sc_worksheet_source_field_rule", "worksheet_rule_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    worksheet_rule_id: Mapped[str] = mapped_column(
        ForeignKey("sc_source_worksheet_rules.id", ondelete="RESTRICT"),
        nullable=False,
    )
    field: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_value: Mapped[str | None] = mapped_column(String(240), nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SourceWorksheetChannelMapping(FlowHubBase):
    __tablename__ = "sc_source_worksheet_channels"
    __table_args__ = (
        UniqueConstraint("worksheet_rule_id", "channel_id", name="uq_sc_worksheet_channel"),
        Index("ix_sc_worksheet_channel_rule", "worksheet_rule_id"),
        Index("ix_sc_worksheet_channel_identity", "channel_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    worksheet_rule_id: Mapped[str] = mapped_column(
        ForeignKey("sc_source_worksheet_rules.id", ondelete="RESTRICT"),
        nullable=False,
    )
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False
    )
    worksheet_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SourceWorksheetChannelFieldMapping(FlowHubBase):
    __tablename__ = "sc_source_worksheet_channel_fields"
    __table_args__ = (
        UniqueConstraint(
            "worksheet_channel_mapping_id",
            "field",
            name="uq_sc_worksheet_channel_field",
        ),
        CheckConstraint(
            "field IN ('external_id','price','stock','status')",
            name="ck_sc_worksheet_channel_field",
        ),
        CheckConstraint(
            "reference_type IN ('column_letter','header_name','column_id','disabled')",
            name="ck_sc_worksheet_channel_reference_type",
        ),
        Index(
            "ix_sc_worksheet_channel_field_mapping",
            "worksheet_channel_mapping_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    worksheet_channel_mapping_id: Mapped[str] = mapped_column(
        ForeignKey("sc_source_worksheet_channels.id", ondelete="RESTRICT"),
        nullable=False,
    )
    field: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_value: Mapped[str | None] = mapped_column(String(240), nullable=True)


class FlowHubSheet(FlowHubBase):
    __tablename__ = "sc_sheets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sources.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SheetRevision(FlowHubBase):
    __tablename__ = "sc_sheet_revisions"
    __table_args__ = (
        UniqueConstraint("sheet_id", "version", name="uq_sc_sheet_revision_version"),
        UniqueConstraint("sheet_id", "checksum", name="uq_sc_sheet_revision_checksum"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sheet_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sheets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    formula_engine_version: Mapped[str] = mapped_column(String(40), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SheetColumn(FlowHubBase):
    __tablename__ = "sc_sheet_columns"
    __table_args__ = (
        UniqueConstraint("revision_id", "position", name="uq_sc_sheet_column_position"),
        UniqueConstraint("revision_id", "column_key", name="uq_sc_sheet_column_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sheet_revisions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    column_key: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    data_type: Mapped[str] = mapped_column(String(30), nullable=False, default="text")


class SheetRow(FlowHubBase):
    __tablename__ = "sc_sheet_rows"
    __table_args__ = (
        UniqueConstraint("revision_id", "row_key", name="uq_sc_sheet_row_key"),
        UniqueConstraint("revision_id", "position", name="uq_sc_sheet_row_position"),
        Index("ix_sc_sheet_row_revision_position", "revision_id", "position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sheet_revisions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    row_key: Mapped[str] = mapped_column(String(36), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class SheetCell(FlowHubBase):
    __tablename__ = "sc_sheet_cells"
    __table_args__ = (
        UniqueConstraint("row_id", "column_key", name="uq_sc_sheet_cell_coordinate"),
        Index("ix_sc_sheet_cell_revision_column", "revision_id", "column_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sheet_revisions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    row_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sheet_rows.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    column_key: Mapped[str] = mapped_column(String(36), nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    calculated_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    formula_expression: Mapped[str | None] = mapped_column(Text, nullable=True)
    formula_dependencies_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    calculation_error: Mapped[str | None] = mapped_column(String(120), nullable=True)


class SheetImportJob(FlowHubBase):
    __tablename__ = "sc_sheet_import_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('validated','completed','failed')", name="ck_sc_import_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sheet_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sheets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    worksheet_name: Mapped[str] = mapped_column(String(240), nullable=False)
    imported_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SourceDataQualityScan(FlowHubBase):
    """Durable evidence for one explicit Data Quality evaluation."""

    __tablename__ = "sc_data_quality_scans"
    __table_args__ = (
        CheckConstraint(
            "status IN ('checking','completed','failed')",
            name="ck_sc_data_quality_scan_status",
        ),
        Index("ix_sc_data_quality_scan_owner_created", "owner_user_id", "created_at"),
        Index("ix_sc_data_quality_scan_source_created", "source_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sc_sources.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_results_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sources_checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    products_checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocking_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    affected_product_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    affected_channel_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    affected_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    previous_issue_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolved_since_previous: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SourceDataQualityScanSource(FlowHubBase):
    """Immutable, indexed membership of a Source in one Data Quality scan."""

    __tablename__ = "sc_data_quality_scan_sources"
    __table_args__ = (
        Index("ix_sc_data_quality_scan_source_scope", "source_id", "scan_id"),
    )

    scan_id: Mapped[str] = mapped_column(
        ForeignKey("sc_data_quality_scans.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sources.id", ondelete="RESTRICT"),
        primary_key=True,
    )


class SourceDataQualityIssue(FlowHubBase):
    __tablename__ = "sc_data_quality_issues"
    __table_args__ = (
        CheckConstraint("severity IN ('warning','error','blocked')", name="ck_sc_issue_severity"),
        Index("ix_sc_issue_filters", "source_id", "channel_id", "category", "severity"),
        Index("ix_sc_issue_snapshot", "snapshot_id"),
        Index("ix_sc_issue_product", "source_product_name"),
        Index("ix_sc_issue_mapping_state", "mapping_state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scan_id: Mapped[str | None] = mapped_column(
        ForeignKey("sc_data_quality_scans.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sources.id", ondelete="RESTRICT"), nullable=False
    )
    snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_workspace_snapshots.id", ondelete="RESTRICT"), nullable=True
    )
    worksheet_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    # External Source identities include the worksheet name and row number.
    # FLOWHUB_019 widens the legacy UUID-sized field so that the complete,
    # human-traceable identity is retained for long and non-Latin sheet names.
    source_row_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_product_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    mapping_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    channel_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=True
    )
    canonical_product_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_canonical_products.id", ondelete="RESTRICT"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(1000), nullable=False)
    technical_details_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
