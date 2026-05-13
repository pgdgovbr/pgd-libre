import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TipoEvento(enum.StrEnum):
    AVALIACAO_REALIZADA = "avaliacao_realizada"
    RECURSO_ABERTO = "recurso_aberto"
    RECURSO_DECIDIDO = "recurso_decidido"
    PRAZO_REGISTRO_IMINENTE = "prazo_registro_iminente"
    CONVOCACAO_EMITIDA = "convocacao_emitida"
    DESLIGAMENTO_REGISTRADO = "desligamento_registrado"
    PGD_SUSPENSO_REVOGADO = "pgd_suspenso_revogado"
    PLANO_APROVADO = "plano_aprovado"


class Notificacao(Base):
    __tablename__ = "notificacoes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tipo_evento: Mapped[TipoEvento] = mapped_column(
        Enum(TipoEvento, name="tipoevento")
    )
    destinatario_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    destinatario_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    conteudo: Mapped[str] = mapped_column(Text)
    contexto: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enviada: Mapped[bool] = mapped_column(Boolean, default=False)
    enviada_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
