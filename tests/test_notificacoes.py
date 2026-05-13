"""Sprint 1.6 — Notificações: testes de criação de registros (TC-M08)."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notificacao import Notificacao, TipoEvento
from src.models.user import UserRole
from src.services.notificacao import criar_notificacao

from .conftest import persist_user


async def test_criar_notificacao_avaliacao_realizada(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    n = await criar_notificacao(
        db,
        tipo_evento=TipoEvento.AVALIACAO_REALIZADA,
        conteudo="Sua avaliação do período foi registrada: Adequado (3).",
        destinatario_user_id=admin.id,
        contexto={"nota": 3, "periodo": "2024-03"},
    )
    await db.commit()
    assert n.id is not None
    assert n.enviada is False


async def test_criar_notificacao_todos_tipos_eventos():
    """Verify all 8 mandatory event types are defined (RF-029)."""
    tipos = {e.value for e in TipoEvento}
    obrigatorios = {
        "avaliacao_realizada",
        "recurso_aberto",
        "recurso_decidido",
        "prazo_registro_iminente",
        "convocacao_emitida",
        "desligamento_registrado",
        "pgd_suspenso_revogado",
        "plano_aprovado",
    }
    assert obrigatorios.issubset(tipos)


async def test_criar_notificacao_sem_usuario(db: AsyncSession):
    n = await criar_notificacao(
        db,
        tipo_evento=TipoEvento.PGD_SUSPENSO_REVOGADO,
        conteudo="O PGD foi suspenso.",
        destinatario_email="servidor@orgao.gov.br",
    )
    await db.commit()
    assert n.destinatario_user_id is None
    assert n.destinatario_email == "servidor@orgao.gov.br"


async def test_criar_notificacao_com_contexto(db: AsyncSession):
    n = await criar_notificacao(
        db,
        tipo_evento=TipoEvento.CONVOCACAO_EMITIDA,
        conteudo="Você foi convocado para comparecer presencialmente.",
        contexto={
            "data_comparecimento": "2024-04-15",
            "local": "Sala 301",
        },
    )
    await db.commit()
    assert n.contexto["local"] == "Sala 301"


async def test_notificacoes_persistidas_no_db(db: AsyncSession):
    for i, tipo in enumerate(list(TipoEvento)[:3]):
        await criar_notificacao(
            db,
            tipo_evento=tipo,
            conteudo=f"Notificação {i}",
        )
    await db.commit()

    result = await db.execute(select(Notificacao))
    todas = result.scalars().all()
    assert len(todas) == 3
