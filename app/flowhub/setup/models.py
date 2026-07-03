"""FlowHub - AppConfig ORM model (BU4).

Stores runtime configuration as key-value pairs in the flowhub_app_config table.
Bootstrap values (database URL, JWT secret, REST secret) remain in .env
and are never stored here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.flowhub.database import FlowHubBase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FlowHubAppConfig(FlowHubBase):
    __tablename__ = "flowhub_app_config"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
