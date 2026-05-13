import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class OrigemUnidade(enum.StrEnum):
    SIAPE = "SIAPE"
    SIORG = "SIORG"


class StatusAto(enum.StrEnum):
    ATIVO = "ativo"
    SUSPENSO = "suspenso"
    REVOGADO = "revogado"


class StatusPgd(enum.StrEnum):
    EM_VIGOR = "em_vigor"
    SUSPENSO = "suspenso"
    REVOGADO = "revogado"


class UnidadeAutorizadora(Base):
    __tablename__ = "unidades_autorizadoras"
    __table_args__ = (
        UniqueConstraint(
            "origem_unidade",
            "cod_unidade_autorizadora",
            name="uq_unidades_autorizadoras_origem_cod",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    origem_unidade: Mapped[OrigemUnidade] = mapped_column(
        Enum(OrigemUnidade, name="origemunidade"), default=OrigemUnidade.SIAPE
    )
    cod_unidade_autorizadora: Mapped[int] = mapped_column(BigInteger, nullable=False)
    nome: Mapped[str] = mapped_column(String(255))
    sigla: Mapped[str] = mapped_column(String(20))
    pgd_autorizado: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    atos_autorizacao: Mapped[list["AtoAutorizacao"]] = relationship(
        back_populates="unidade_autorizadora", cascade="all, delete-orphan"
    )
    unidades_instituidoras: Mapped[list["UnidadeInstituidora"]] = relationship(
        back_populates="unidade_autorizadora", cascade="all, delete-orphan"
    )


class AtoAutorizacao(Base):
    __tablename__ = "atos_autorizacao"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    unidade_autorizadora_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("unidades_autorizadoras.id", ondelete="CASCADE")
    )
    autoridade: Mapped[str] = mapped_column(String(255))
    data_publicacao: Mapped[date] = mapped_column(Date)
    referencia: Mapped[str] = mapped_column(String(255))
    status: Mapped[StatusAto] = mapped_column(
        Enum(StatusAto, name="statusato"), default=StatusAto.ATIVO
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    unidade_autorizadora: Mapped["UnidadeAutorizadora"] = relationship(
        back_populates="atos_autorizacao"
    )


class UnidadeInstituidora(Base):
    __tablename__ = "unidades_instituidoras"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    unidade_autorizadora_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("unidades_autorizadoras.id", ondelete="CASCADE")
    )
    cod_unidade_instituidora: Mapped[int] = mapped_column(BigInteger)
    nome: Mapped[str] = mapped_column(String(255))
    sigla: Mapped[str] = mapped_column(String(20))
    ato_instituicao_ref: Mapped[str] = mapped_column(String(255))
    data_instituicao: Mapped[date] = mapped_column(Date)
    tipos_atividades: Mapped[str] = mapped_column(Text)
    modalidades_autorizadas: Mapped[list] = mapped_column(JSON, default=list)
    vagas_percentual_presencial: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    vagas_percentual_tt_parcial: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    vagas_percentual_tt_integral: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    vagas_percentual_tt_exterior: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    conteudo_minimo_tcr: Mapped[str] = mapped_column(Text)
    prazo_antecedencia_convocacao_dias: Mapped[int] = mapped_column(Integer)
    nivel_produtividade_adicional_tt: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    vedacoes_participacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    criterios_selecao_adicionais: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    procedimento_registro_comparecimento: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    status: Mapped[StatusPgd] = mapped_column(
        Enum(StatusPgd, name="statuspgd"), default=StatusPgd.EM_VIGOR
    )
    data_suspensao_revogacao: Mapped[date | None] = mapped_column(Date, nullable=True)
    motivo_suspensao_revogacao: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    unidade_autorizadora: Mapped["UnidadeAutorizadora"] = relationship(
        back_populates="unidades_instituidoras"
    )
    unidades_execucao: Mapped[list["UnidadeExecucao"]] = relationship(
        back_populates="unidade_instituidora", cascade="all, delete-orphan"
    )


class UnidadeExecucao(Base):
    __tablename__ = "unidades_execucao"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    unidade_instituidora_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("unidades_instituidoras.id", ondelete="CASCADE")
    )
    cod_unidade_executora: Mapped[int] = mapped_column(BigInteger)
    nome: Mapped[str] = mapped_column(String(255))
    sigla: Mapped[str] = mapped_column(String(20))
    chefia_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    nivel_superior_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    coincide_com_instituidora: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    unidade_instituidora: Mapped["UnidadeInstituidora"] = relationship(
        back_populates="unidades_execucao"
    )
