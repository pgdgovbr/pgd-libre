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
from .institucional import OrigemUnidade


class MotivoDesligamento(enum.StrEnum):
    A_PEDIDO = "a_pedido"
    INTERESSE_ADMINISTRACAO = "interesse_administracao"
    MUDANCA_UNIDADE = "mudanca_unidade"
    PGD_REVOGADO = "pgd_revogado"


class TipoVinculo(enum.StrEnum):
    EFETIVO = "efetivo"
    COMISSIONADO = "comissionado"
    EMPREGADO_PUBLICO = "empregado_publico"
    CONTRATO_DETERMINADO = "contrato_determinado"
    ESTAGIARIO = "estagiario"


class RegimeExecucao(enum.StrEnum):
    INTEGRAL = "integral"
    PARCIAL = "parcial"


class StatusTCR(enum.StrEnum):
    PENDENTE = "pendente"
    ATIVO = "ativo"
    SUBSTITUIDO = "substituido"
    CANCELADO = "cancelado"


class StatusConvocacao(enum.StrEnum):
    PENDENTE = "pendente"
    ATENDIDA = "atendida"
    NAO_ATENDIDA = "nao_atendida"
    CANCELADA = "cancelada"


class Participante(Base):
    __tablename__ = "participantes"
    __table_args__ = (
        UniqueConstraint(
            "origem_unidade",
            "cod_unidade_autorizadora",
            "cod_unidade_lotacao",
            "matricula_siape",
            name="uq_participante_api_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    origem_unidade: Mapped[OrigemUnidade] = mapped_column(
        Enum(OrigemUnidade, name="origemunidade"), nullable=False
    )
    cod_unidade_autorizadora: Mapped[int] = mapped_column(BigInteger)
    cod_unidade_lotacao: Mapped[int] = mapped_column(BigInteger)
    matricula_siape: Mapped[str] = mapped_column(String(7))
    cod_unidade_instituidora: Mapped[int] = mapped_column(BigInteger)
    cpf: Mapped[str] = mapped_column(String(11))
    nome: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))
    situacao: Mapped[int] = mapped_column(Integer, default=1)  # 0=Inativo, 1=Ativo
    modalidade_execucao: Mapped[int] = mapped_column(Integer)  # 1-5
    data_assinatura_tcr: Mapped[date] = mapped_column(Date)
    data_ingresso_pgd: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_desligamento: Mapped[date | None] = mapped_column(Date, nullable=True)
    motivo_desligamento: Mapped[MotivoDesligamento | None] = mapped_column(
        Enum(MotivoDesligamento, name="motivodesligamento"), nullable=True
    )
    cumpriu_estagio_probatorio: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    data_fim_estagio_probatorio: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )
    tipo_vinculo: Mapped[TipoVinculo] = mapped_column(
        Enum(TipoVinculo, name="tipovinculo")
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    unidade_execucao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("unidades_execucao.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tcrs: Mapped[list["TCR"]] = relationship(
        back_populates="participante", cascade="all, delete-orphan"
    )
    convocacoes: Mapped[list["Convocacao"]] = relationship(
        back_populates="participante", cascade="all, delete-orphan"
    )


class TCR(Base):
    __tablename__ = "tcrs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    participante_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participantes.id", ondelete="CASCADE")
    )
    chefia_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    modalidade_execucao: Mapped[int] = mapped_column(Integer)
    regime_execucao: Mapped[RegimeExecucao] = mapped_column(
        Enum(RegimeExecucao, name="regimeexecucao")
    )
    prazo_antecedencia_convocacao_dias: Mapped[int] = mapped_column(Integer)
    canais_comunicacao: Mapped[list] = mapped_column(JSON, default=list)
    responsabilidades: Mapped[str] = mapped_column(Text)
    ciencia_instalacoes_ergonomia: Mapped[bool] = mapped_column(Boolean, default=False)
    ciencia_nao_direito_adquirido: Mapped[bool] = mapped_column(Boolean, default=False)
    ciencia_custeio_estrutura: Mapped[bool] = mapped_column(Boolean, default=False)
    acoes_melhoria: Mapped[str | None] = mapped_column(Text, nullable=True)
    outras_providencias_inadequado: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    saldo_banco_horas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prazo_compensacao_banco_horas: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )
    carga_horaria_compensacao: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    prazo_compensacao_inexecucao: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )
    data_assinatura_participante: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    data_assinatura_chefia: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[StatusTCR] = mapped_column(
        Enum(StatusTCR, name="statustcr"), default=StatusTCR.PENDENTE
    )
    tcr_anterior_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tcrs.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    participante: Mapped["Participante"] = relationship(back_populates="tcrs")


class Convocacao(Base):
    __tablename__ = "convocacoes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    participante_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("participantes.id", ondelete="CASCADE")
    )
    unidade_execucao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("unidades_execucao.id", ondelete="CASCADE")
    )
    chefia_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    canal_comunicacao: Mapped[str] = mapped_column(String(255))
    data_convocacao: Mapped[date] = mapped_column(Date)
    data_comparecimento_prevista: Mapped[date] = mapped_column(Date)
    horario_comparecimento: Mapped[str] = mapped_column(String(20))
    local_comparecimento: Mapped[str] = mapped_column(String(255))
    periodo_presencial_inicio: Mapped[date] = mapped_column(Date)
    periodo_presencial_fim: Mapped[date] = mapped_column(Date)
    motivo: Mapped[str] = mapped_column(Text)
    data_comparecimento_efetivo: Mapped[date | None] = mapped_column(
        Date, nullable=True
    )
    status: Mapped[StatusConvocacao] = mapped_column(
        Enum(StatusConvocacao, name="statusconvocacao"),
        default=StatusConvocacao.PENDENTE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    participante: Mapped["Participante"] = relationship(back_populates="convocacoes")
