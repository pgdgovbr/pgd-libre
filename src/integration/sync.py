"""Sincronização periódica com a API PGD Central."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.participante import Participante
from ..models.plano import PlanoEntregas, PlanoTrabalho
from .client import ApiPgdClient
from .mapper import participante_to_payload, plano_entregas_to_payload, plano_trabalho_to_payload


async def sincronizar_tudo(db: AsyncSession, client: ApiPgdClient) -> dict:
    """Envia para a API Central todos os registos ainda não sincronizados.

    Retorna {"sucesso": N, "erros": [{"tipo", "id", "erro"}, ...]}.
    Um erro num registo não interrompe os demais.
    """
    sucesso = 0
    erros: list[dict] = []
    now = datetime.now(timezone.utc)

    # --- Participantes ---
    result = await db.execute(
        select(Participante).where(Participante.api_sincronizado_em.is_(None))
    )
    for p in result.scalars():
        try:
            await client.send_participante(
                cod_unidade_lotacao=p.cod_unidade_lotacao,
                matricula_siape=p.matricula_siape,
                payload=participante_to_payload(p),
            )
            p.api_sincronizado_em = now
            sucesso += 1
        except Exception as exc:
            erros.append({"tipo": "participante", "id": str(p.id), "erro": str(exc)})

    # --- Planos de Entregas ---
    result = await db.execute(
        select(PlanoEntregas)
        .options(selectinload(PlanoEntregas.entregas))
        .where(PlanoEntregas.api_sincronizado_em.is_(None))
    )
    for pe in result.scalars():
        try:
            await client.send_plano_entregas(
                origem_unidade=pe.origem_unidade.value,
                cod_unidade_autorizadora=pe.cod_unidade_autorizadora,
                id_plano_entregas=pe.id_plano_entregas,
                payload=plano_entregas_to_payload(pe),
            )
            pe.api_sincronizado_em = now
            sucesso += 1
        except Exception as exc:
            erros.append(
                {"tipo": "plano_entregas", "id": pe.id_plano_entregas, "erro": str(exc)}
            )

    # --- Planos de Trabalho ---
    result = await db.execute(
        select(PlanoTrabalho)
        .options(
            selectinload(PlanoTrabalho.contribuicoes),
            selectinload(PlanoTrabalho.avaliacoes),
        )
        .where(PlanoTrabalho.api_sincronizado_em.is_(None))
    )
    for pt in result.scalars():
        try:
            await client.send_plano_trabalho(
                origem_unidade=pt.origem_unidade.value,
                cod_unidade_autorizadora=pt.cod_unidade_autorizadora,
                id_plano_trabalho=pt.id_plano_trabalho,
                payload=plano_trabalho_to_payload(pt),
            )
            pt.api_sincronizado_em = now
            sucesso += 1
        except Exception as exc:
            erros.append(
                {"tipo": "plano_trabalho", "id": pt.id_plano_trabalho, "erro": str(exc)}
            )

    await db.commit()
    return {"sucesso": sucesso, "erros": erros}
