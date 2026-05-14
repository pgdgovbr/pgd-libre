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
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base
from .institucional import OrigemUnidade


class TipoMeta(enum.StrEnum):
    UNIDADE = "unidade"
    PERCENTUAL = "percentual"


class DecisaoRecurso(enum.StrEnum):
    ACATADO = "acatado"
    NAO_ACATADO = "nao_acatado"


class StatusRecurso(enum.StrEnum):
    ABERTO = "aberto"
    ENCERRADO = "encerrado"


# Status values match the API PGD Central integer codes
STATUS_PE_CANCELADO = 1
STATUS_PE_APROVADO = 2
STATUS_PE_EM_EXECUCAO = 3
STATUS_PE_CONCLUIDO = 4
STATUS_PE_AVALIADO = 5

STATUS_PT_CANCELADO = 1
STATUS_PT_APROVADO = 2
STATUS_PT_EM_EXECUCAO = 3
STATUS_PT_CONCLUIDO = 4


class PlanoEntregas(Base):
    __tablename__ = "planos_entregas"
    __table_args__ = (
        UniqueConstraint(
            "origem_unidade",
            "cod_unidade_autorizadora",
            "id_plano_entregas",
            name="uq_plano_entregas_api_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_plano_entregas: Mapped[str] = mapped_column(String(50))
    origem_unidade: Mapped[OrigemUnidade] = mapped_column(
        Enum(OrigemUnidade, name="origemunidade"), nullable=False
    )
    cod_unidade_autorizadora: Mapped[int] = mapped_column(BigInteger)
    cod_unidade_instituidora: Mapped[int] = mapped_column(BigInteger)
    cod_unidade_executora: Mapped[int] = mapped_column(BigInteger)
    unidade_execucao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("unidades_execucao.id", ondelete="RESTRICT")
    )
    status: Mapped[int] = mapped_column(Integer, default=STATUS_PE_APROVADO)
    data_inicio: Mapped[date] = mapped_column(Date)
    data_termino: Mapped[date] = mapped_column(Date)
    avaliacao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_avaliacao: Mapped[date | None] = mapped_column(Date, nullable=True)
    avaliado_por_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    aprovado_por_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    data_aprovacao: Mapped[date | None] = mapped_column(Date, nullable=True)
    ajustes_comunicados_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    api_sincronizado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    entregas: Mapped[list["Entrega"]] = relationship(
        back_populates="plano_entregas", cascade="all, delete-orphan"
    )


class Entrega(Base):
    __tablename__ = "entregas"
    __table_args__ = (
        UniqueConstraint(
            "plano_entregas_id",
            "id_entrega",
            name="uq_entrega_api_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_entrega: Mapped[str] = mapped_column(String(50))
    plano_entregas_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("planos_entregas.id", ondelete="CASCADE")
    )
    nome_entrega: Mapped[str] = mapped_column(String(300))
    meta_entrega: Mapped[int] = mapped_column(Integer)
    tipo_meta: Mapped[TipoMeta] = mapped_column(Enum(TipoMeta, name="tipometa"))
    data_entrega: Mapped[date] = mapped_column(Date)
    nome_unidade_demandante: Mapped[str] = mapped_column(String(300))
    nome_unidade_destinataria: Mapped[str] = mapped_column(String(300))
    entrega_cancelada: Mapped[bool] = mapped_column(Boolean, default=False)

    plano_entregas: Mapped["PlanoEntregas"] = relationship(back_populates="entregas")


class PlanoTrabalho(Base):
    __tablename__ = "planos_trabalho"
    __table_args__ = (
        UniqueConstraint(
            "origem_unidade",
            "cod_unidade_autorizadora",
            "id_plano_trabalho",
            name="uq_plano_trabalho_api_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_plano_trabalho: Mapped[str] = mapped_column(String(50))
    origem_unidade: Mapped[OrigemUnidade] = mapped_column(
        Enum(OrigemUnidade, name="origemunidade"), nullable=False
    )
    cod_unidade_autorizadora: Mapped[int] = mapped_column(BigInteger)
    cod_unidade_executora: Mapped[int] = mapped_column(BigInteger)
    cod_unidade_lotacao_participante: Mapped[int] = mapped_column(BigInteger)
    participante_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participantes.id", ondelete="RESTRICT")
    )
    cpf_participante: Mapped[str] = mapped_column(String(11))
    matricula_siape: Mapped[str] = mapped_column(String(7))
    tcr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tcrs.id", ondelete="RESTRICT")
    )
    status: Mapped[int] = mapped_column(Integer, default=STATUS_PT_APROVADO)
    data_inicio: Mapped[date] = mapped_column(Date)
    data_termino: Mapped[date] = mapped_column(Date)
    carga_horaria_disponivel: Mapped[int] = mapped_column(Integer)
    criterios_avaliacao: Mapped[str] = mapped_column(Text)
    declaracao_ausencia_prejuizo_plano: Mapped[bool] = mapped_column(Boolean, default=False)
    declaracao_ausencia_prejuizo_comparecer: Mapped[bool] = mapped_column(Boolean, default=False)
    declaracao_ausencia_prejuizo_contato: Mapped[bool] = mapped_column(Boolean, default=False)
    declaracao_ausencia_prejuizo_sincrono: Mapped[bool] = mapped_column(Boolean, default=False)
    trabalho_noturno: Mapped[bool] = mapped_column(Boolean, default=False)
    plano_entregas_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("planos_entregas.id", ondelete="SET NULL"),
        nullable=True,
    )
    api_sincronizado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    contribuicoes: Mapped[list["Contribuicao"]] = relationship(
        back_populates="plano_trabalho", cascade="all, delete-orphan"
    )
    avaliacoes: Mapped[list["AvaliacaoRegistrosExecucao"]] = relationship(
        back_populates="plano_trabalho", cascade="all, delete-orphan"
    )


class Contribuicao(Base):
    __tablename__ = "contribuicoes"
    __table_args__ = (
        UniqueConstraint(
            "plano_trabalho_id",
            "id_contribuicao",
            name="uq_contribuicao_api_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_contribuicao: Mapped[str] = mapped_column(String(50))
    rotulo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    plano_trabalho_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("planos_trabalho.id", ondelete="CASCADE")
    )
    tipo_contribuicao: Mapped[int] = mapped_column(Integer)  # 1, 2, 3
    percentual_contribuicao: Mapped[int] = mapped_column(Integer)  # 0-100
    id_plano_entregas: Mapped[str | None] = mapped_column(String(50), nullable=True)
    id_entrega: Mapped[str | None] = mapped_column(String(50), nullable=True)
    descricao: Mapped[str] = mapped_column(Text)

    plano_trabalho: Mapped["PlanoTrabalho"] = relationship(back_populates="contribuicoes")


class AvaliacaoRegistrosExecucao(Base):
    __tablename__ = "avaliacoes_registros_execucao"
    __table_args__ = (
        UniqueConstraint(
            "plano_trabalho_id",
            "id_periodo_avaliativo",
            name="uq_avaliacao_periodo",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_periodo_avaliativo: Mapped[str] = mapped_column(String(50))
    plano_trabalho_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("planos_trabalho.id", ondelete="CASCADE")
    )
    data_inicio_periodo_avaliativo: Mapped[date] = mapped_column(Date)
    data_fim_periodo_avaliativo: Mapped[date] = mapped_column(Date)
    descricao_execucao: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocorrencias: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_registro_participante: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    avaliacao_registros_execucao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_avaliacao_registros_execucao: Mapped[date | None] = mapped_column(Date, nullable=True)
    avaliacao_justificativa: Mapped[str | None] = mapped_column(Text, nullable=True)
    avaliacao_escala_customizada: Mapped[str | None] = mapped_column(String(100), nullable=True)
    horas_inexecucao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recurso_texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    recurso_data: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recurso_decisao: Mapped[DecisaoRecurso | None] = mapped_column(
        Enum(DecisaoRecurso, name="decisaorecurso"), nullable=True
    )
    recurso_decisao_justificativa: Mapped[str | None] = mapped_column(Text, nullable=True)
    recurso_decisao_data: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status_recurso: Mapped[StatusRecurso | None] = mapped_column(
        Enum(StatusRecurso, name="statusrecurso"), nullable=True
    )

    plano_trabalho: Mapped["PlanoTrabalho"] = relationship(back_populates="avaliacoes")
