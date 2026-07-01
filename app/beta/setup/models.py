"""FlowHub â€” AppConfig ORM model (BU4).

Stores runtime configuration as key-value pairs in the beta_app_config table.
Bootstrap values (database URL, JWT secret, REST secret) remain in .env.beta
and are never stored here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.beta.database import BetaBase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BetaAppConfig(BetaBase):
    __tablename__ = "beta_app_config"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(150), nullable=True)
