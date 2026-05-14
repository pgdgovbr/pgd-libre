"""Tipos Strawberry e helpers para Notificações (Sprint 1.6)."""

import enum
from datetime import datetime

import strawberry


@strawberry.enum
class TipoEventoGql(enum.Enum):
    AVALIACAO_REALIZADA = "avaliacao_realizada"
    RECURSO_ABERTO = "recurso_aberto"
    RECURSO_DECIDIDO = "recurso_decidido"
    PRAZO_REGISTRO_IMINENTE = "prazo_registro_iminente"
    CONVOCACAO_EMITIDA = "convocacao_emitida"
    DESLIGAMENTO_REGISTRADO = "desligamento_registrado"
    PGD_SUSPENSO_REVOGADO = "pgd_suspenso_revogado"
    PLANO_APROVADO = "plano_aprovado"


@strawberry.type
class NotificacaoType:
    id: strawberry.ID
    tipo_evento: TipoEventoGql
    conteudo: str
    enviada: bool
    created_at: datetime
    enviada_em: datetime | None
    contexto: strawberry.scalars.JSON | None


def _notificacao_to_type(n) -> NotificacaoType:  # type: ignore[no-untyped-def]
    return NotificacaoType(
        id=strawberry.ID(str(n.id)),
        tipo_evento=TipoEventoGql(n.tipo_evento.value),
        conteudo=n.conteudo,
        enviada=n.enviada,
        created_at=n.created_at,
        enviada_em=n.enviada_em,
        contexto=n.contexto,
    )
