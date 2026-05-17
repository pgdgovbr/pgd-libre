"""Modelo de auditoria/uso da feature "Reescrever com IA" no Registro de Execução.

Cada chamada ao LLM gera um AIRewriteEvent. Quando o servidor clica em "Aplicar",
o mesmo evento ganha applied=True. parent_event_id existe para o caso futuro de
encadear variantes.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AIRewriteEvent(Base):
    __tablename__ = "ai_rewrite_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    registro_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("avaliacoes_registros_execucao.id", ondelete="SET NULL"),
        nullable=True,
    )
    template_id: Mapped[str] = mapped_column(String(20))
    instrucao_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    chars_in: Mapped[int] = mapped_column(Integer)
    chars_out: Mapped[int] = mapped_column(Integer)
    tokens_in: Mapped[int] = mapped_column(Integer)
    tokens_out: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(120))
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_rewrite_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
