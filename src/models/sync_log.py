import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TipoEntidadeSync(enum.StrEnum):
    PARTICIPANTE = "participante"
    PLANO_ENTREGAS = "plano_entregas"
    PLANO_TRABALHO = "plano_trabalho"


class RegistroEnvioAPI(Base):
    """Histórico de tentativas de envio para a API PGD Central."""

    __tablename__ = "registros_envio_api"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo_entidade: Mapped[TipoEntidadeSync] = mapped_column(
        Enum(TipoEntidadeSync, name="tipoentidadesync")
    )
    entidade_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    tentativa: Mapped[int] = mapped_column(Integer)
    sucesso: Mapped[bool] = mapped_column(Boolean)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    erro_mensagem: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
