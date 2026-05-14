"""Sincronização periódica com a API PGD Central."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.participante import Participante
from ..models.plano import PlanoEntregas, PlanoTrabalho
from ..models.sync_log import RegistroEnvioAPI, TipoEntidadeSync
from .client import ApiPgdClient
from .mapper import (
    participante_to_payload,
    plano_entregas_to_payload,
    plano_trabalho_to_payload,
)

# Backoff delays in seconds: 1 min → 5 min → 30 min
RETRY_DELAYS = [60, 300, 1800]
MAX_TENTATIVAS = len(RETRY_DELAYS)


async def _ultimo_registro(
    db: AsyncSession,
    tipo: TipoEntidadeSync,
    entidade_id: uuid.UUID,
) -> RegistroEnvioAPI | None:
    result = await db.execute(
        select(RegistroEnvioAPI)
        .where(
            RegistroEnvioAPI.tipo_entidade == tipo,
            RegistroEnvioAPI.entidade_id == entidade_id,
        )
        .order_by(RegistroEnvioAPI.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _elegivel(ultimo: RegistroEnvioAPI | None, now: datetime) -> bool:
    """True se a entidade deve ser tentada neste ciclo."""
    if ultimo is None:
        return True
    if ultimo.sucesso:
        return False  # já enviado (não deveria aparecer com api_sincronizado_em=None)
    if ultimo.tentativa >= MAX_TENTATIVAS:
        return False  # esgotou tentativas — requer reprocessamento manual
    delay = RETRY_DELAYS[ultimo.tentativa - 1]
    elapsed = (now - ultimo.created_at).total_seconds()
    return elapsed >= delay


async def _registrar(
    db: AsyncSession,
    tipo: TipoEntidadeSync,
    entidade_id: uuid.UUID,
    tentativa: int,
    sucesso: bool,
    erro_mensagem: str | None = None,
    http_status: int | None = None,
) -> None:
    reg = RegistroEnvioAPI(
        tipo_entidade=tipo,
        entidade_id=entidade_id,
        tentativa=tentativa,
        sucesso=sucesso,
        http_status=http_status,
        erro_mensagem=erro_mensagem,
    )
    db.add(reg)


async def sincronizar_tudo(db: AsyncSession, client: ApiPgdClient) -> dict:
    """Envia para a API Central todos os registos ainda não sincronizados.

    Respeita backoff exponencial por entidade usando RegistroEnvioAPI.
    Retorna {"sucesso": N, "erros": [{"tipo", "id", "erro"}, ...]}.
    Um erro num registo não interrompe os demais.
    """
    sucesso = 0
    erros: list[dict] = []
    now = datetime.now(UTC)

    # --- Participantes ---
    result_p = await db.execute(
        select(Participante).where(Participante.api_sincronizado_em.is_(None))
    )
    for p in result_p.scalars():
        ultimo = await _ultimo_registro(db, TipoEntidadeSync.PARTICIPANTE, p.id)
        if not _elegivel(ultimo, now):
            continue
        tentativa = (ultimo.tentativa + 1) if ultimo else 1
        try:
            await client.send_participante(
                cod_unidade_lotacao=p.cod_unidade_lotacao,
                matricula_siape=p.matricula_siape,
                payload=participante_to_payload(p),
            )
            p.api_sincronizado_em = now
            await _registrar(db, TipoEntidadeSync.PARTICIPANTE, p.id, tentativa, sucesso=True)
            sucesso += 1
        except Exception as exc:
            await _registrar(
                db,
                TipoEntidadeSync.PARTICIPANTE,
                p.id,
                tentativa,
                sucesso=False,
                erro_mensagem=str(exc),
            )
            erros.append({"tipo": "participante", "id": str(p.id), "erro": str(exc)})

    # --- Planos de Entregas ---
    result_pe = await db.execute(
        select(PlanoEntregas)
        .options(selectinload(PlanoEntregas.entregas))
        .where(PlanoEntregas.api_sincronizado_em.is_(None))
    )
    for pe in result_pe.scalars():
        ultimo = await _ultimo_registro(db, TipoEntidadeSync.PLANO_ENTREGAS, pe.id)
        if not _elegivel(ultimo, now):
            continue
        tentativa = (ultimo.tentativa + 1) if ultimo else 1
        try:
            await client.send_plano_entregas(
                origem_unidade=pe.origem_unidade.value,
                cod_unidade_autorizadora=pe.cod_unidade_autorizadora,
                id_plano_entregas=pe.id_plano_entregas,
                payload=plano_entregas_to_payload(pe),
            )
            pe.api_sincronizado_em = now
            await _registrar(db, TipoEntidadeSync.PLANO_ENTREGAS, pe.id, tentativa, sucesso=True)
            sucesso += 1
        except Exception as exc:
            await _registrar(
                db,
                TipoEntidadeSync.PLANO_ENTREGAS,
                pe.id,
                tentativa,
                sucesso=False,
                erro_mensagem=str(exc),
            )
            erros.append({"tipo": "plano_entregas", "id": pe.id_plano_entregas, "erro": str(exc)})

    # --- Planos de Trabalho ---
    result_pt = await db.execute(
        select(PlanoTrabalho)
        .options(
            selectinload(PlanoTrabalho.contribuicoes),
            selectinload(PlanoTrabalho.avaliacoes),
        )
        .where(PlanoTrabalho.api_sincronizado_em.is_(None))
    )
    for pt in result_pt.scalars():
        ultimo = await _ultimo_registro(db, TipoEntidadeSync.PLANO_TRABALHO, pt.id)
        if not _elegivel(ultimo, now):
            continue
        tentativa = (ultimo.tentativa + 1) if ultimo else 1
        try:
            await client.send_plano_trabalho(
                origem_unidade=pt.origem_unidade.value,
                cod_unidade_autorizadora=pt.cod_unidade_autorizadora,
                id_plano_trabalho=pt.id_plano_trabalho,
                payload=plano_trabalho_to_payload(pt),
            )
            pt.api_sincronizado_em = now
            await _registrar(db, TipoEntidadeSync.PLANO_TRABALHO, pt.id, tentativa, sucesso=True)
            sucesso += 1
        except Exception as exc:
            await _registrar(
                db,
                TipoEntidadeSync.PLANO_TRABALHO,
                pt.id,
                tentativa,
                sucesso=False,
                erro_mensagem=str(exc),
            )
            erros.append({"tipo": "plano_trabalho", "id": pt.id_plano_trabalho, "erro": str(exc)})

    await db.commit()
    return {"sucesso": sucesso, "erros": erros}
