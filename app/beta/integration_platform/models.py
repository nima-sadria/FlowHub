"""Integration Platform ORM models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.beta.database import BetaBase


def _utcnow() -> datetime:
    return datetime.utcnow()


class IntegrationConnectorInstance(BetaBase):
    __tablename__ = "ip_connector_instances"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    connector_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="1.0.0")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    read_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="disabled")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    settings: Mapped[list[IntegrationConnectorSetting]] = relationship(
        "IntegrationConnectorSetting",
        back_populates="connector",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class IntegrationConnectorSetting(BetaBase):
    __tablename__ = "ip_connector_settings"
    __table_args__ = (UniqueConstraint("connector_id", "key", name="uq_ip_connector_setting"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("ip_connector_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    configured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    connector: Mapped[IntegrationConnectorInstance] = relationship(
        "IntegrationConnectorInstance",
        back_populates="settings",
    )


class IntegrationConnectorHealthSnapshot(BetaBase):
    __tablename__ = "ip_connector_health_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    details_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class IntegrationConnectorEvent(BetaBase):
    __tablename__ = "ip_connector_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(30), nullable=False, default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

