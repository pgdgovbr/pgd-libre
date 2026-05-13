import enum
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AuditAction(enum.StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    table_name: Mapped[str] = mapped_column(String(100), index=True)
    record_id: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction, name="auditaction"))
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    old_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
