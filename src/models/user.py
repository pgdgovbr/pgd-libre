import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    GESTOR_UNIDADE = "gestor_unidade"
    CHEFE_IMEDIATO = "chefe_imediato"
    SERVIDOR = "servidor"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="userrole"), default=UserRole.SERVIDOR
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    oauth_sub: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    oauth_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
