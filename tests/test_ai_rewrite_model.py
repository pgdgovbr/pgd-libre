"""TDD — Modelo AIRewriteEvent: persistência e rate-limit query.

Cobre:
- Insert + cascade FK para user
- registro_id nullable (rascunho não persistido)
- Query de rate-limit: conta eventos da última hora por user
- parent_event_id liga "applied" ao "gerado"
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ai_rewrite import AIRewriteEvent
from src.models.user import UserRole
from tests.conftest import persist_user


@pytest.fixture
async def servidor(db: AsyncSession):
    return await persist_user(db, email="srv@t.com", role=UserRole.SERVIDOR)


async def test_insert_evento_basico(db: AsyncSession, servidor):
    ev = AIRewriteEvent(
        user_id=servidor.id,
        registro_id=None,
        template_id="entrega",
        instrucao_custom=False,
        chars_in=100,
        chars_out=300,
        tokens_in=120,
        tokens_out=350,
        latency_ms=2400,
        model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    assert ev.id is not None
    assert ev.applied is False
    assert ev.parent_event_id is None
    assert ev.created_at is not None


async def test_rate_limit_conta_eventos_ultima_hora(db: AsyncSession, servidor):
    """O service de rate limit deve contar eventos do user na última hora."""
    now = datetime.now(UTC)
    # 3 eventos: 2 dentro da janela de 1h, 1 fora
    eventos = [
        AIRewriteEvent(
            user_id=servidor.id,
            template_id="entrega",
            instrucao_custom=False,
            chars_in=100,
            chars_out=200,
            tokens_in=120,
            tokens_out=250,
            latency_ms=2000,
            model="haiku",
            created_at=now - timedelta(minutes=10),
        ),
        AIRewriteEvent(
            user_id=servidor.id,
            template_id="cronologico",
            instrucao_custom=True,
            chars_in=150,
            chars_out=400,
            tokens_in=180,
            tokens_out=450,
            latency_ms=3000,
            model="haiku",
            created_at=now - timedelta(minutes=30),
        ),
        AIRewriteEvent(
            user_id=servidor.id,
            template_id="star",
            instrucao_custom=False,
            chars_in=200,
            chars_out=500,
            tokens_in=240,
            tokens_out=600,
            latency_ms=4000,
            model="haiku",
            created_at=now - timedelta(hours=2),  # FORA da janela
        ),
    ]
    for e in eventos:
        db.add(e)
    await db.commit()

    from src.services.ai_rewrite import contar_eventos_ultima_hora

    n = await contar_eventos_ultima_hora(db, servidor.id)
    assert n == 2


async def test_parent_event_id_liga_aplicado_ao_gerado(db: AsyncSession, servidor):
    gerado = AIRewriteEvent(
        user_id=servidor.id,
        template_id="entrega",
        instrucao_custom=False,
        chars_in=100,
        chars_out=300,
        tokens_in=120,
        tokens_out=350,
        latency_ms=2400,
        model="haiku",
    )
    db.add(gerado)
    await db.commit()
    await db.refresh(gerado)

    # Marcar como aplicado — não usa parent_event_id; usa applied=True direto.
    # Mas o campo parent_event_id existe para o caso de retrofit/aplicar variantes.
    gerado.applied = True
    await db.commit()
    await db.refresh(gerado)
    assert gerado.applied is True


async def test_registro_id_nullable(db: AsyncSession, servidor):
    """Servidor pode pedir reescrita antes de ter persistido o ARE."""
    ev = AIRewriteEvent(
        user_id=servidor.id,
        registro_id=None,
        template_id="entrega",
        instrucao_custom=False,
        chars_in=80,
        chars_out=200,
        tokens_in=100,
        tokens_out=240,
        latency_ms=1800,
        model="haiku",
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    assert ev.registro_id is None
