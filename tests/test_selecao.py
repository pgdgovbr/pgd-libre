"""RF-006 — Seleção de Participantes com Critérios de Prioridade (TC-M02-012 a TC-M02-014)."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditLog
from src.models.institucional import OrigemUnidade, UnidadeExecucao
from src.models.participante import CriteriosPrioridade
from src.models.user import UserRole
from src.services.institucional import (
    ValidationError,
    criar_ato_autorizacao,
    criar_unidade_autorizadora,
    criar_unidade_instituidora,
)
from src.services.participante import (
    CandidatoSelecao,
    confirmar_selecao,
    ordenar_candidatos,
)

from .conftest import persist_user


# ---------------------------------------------------------------------------
# TC-M02-012 — Ordenação por prioridade legal [U]
# ---------------------------------------------------------------------------


def test_ordenar_candidatos_por_prioridade_legal():
    """TC-M02-012 — PcD > Resp.PcD > Mob.Reduzida > HorEspecial > SemPrioridade."""
    candidatos = [
        CandidatoSelecao(id="E", nome="Sem Prioridade", criterio=CriteriosPrioridade.SEM_PRIORIDADE),
        CandidatoSelecao(id="D", nome="Horário Especial", criterio=CriteriosPrioridade.HORARIO_ESPECIAL),
        CandidatoSelecao(id="C", nome="Mobilidade Reduzida", criterio=CriteriosPrioridade.MOBILIDADE_REDUZIDA),
        CandidatoSelecao(id="B", nome="Responsável PcD", criterio=CriteriosPrioridade.RESP_PCD),
        CandidatoSelecao(id="A", nome="PcD", criterio=CriteriosPrioridade.PCD),
    ]
    selecionados, nao_selecionados = ordenar_candidatos(candidatos, n_vagas=3)

    assert [c.id for c in selecionados] == ["A", "B", "C"]
    assert [c.id for c in nao_selecionados] == ["D", "E"]


def test_ordenar_candidatos_mais_vagas_que_candidatos():
    """Quando vagas >= candidatos, todos são selecionados."""
    candidatos = [
        CandidatoSelecao(id="X", nome="X", criterio=CriteriosPrioridade.PCD),
    ]
    selecionados, nao_selecionados = ordenar_candidatos(candidatos, n_vagas=5)
    assert len(selecionados) == 1
    assert len(nao_selecionados) == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_ue(db: AsyncSession, admin, cod_ua: int = 60001) -> UnidadeExecucao:
    from datetime import date

    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=cod_ua,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="UA Sel",
        sigla="UAS",
        user=admin,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Min.",
        data_publicacao=date(2024, 1, 1),
        referencia="Port. 1",
        user=admin,
    )
    await db.refresh(ua)
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=60010,
        nome="UI Sel",
        sigla="UIS",
        ato_instituicao_ref="P1",
        data_instituicao=date(2024, 1, 1),
        tipos_atividades="T",
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=60020,
        nome="UE Sel",
        sigla="UES",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)
    return ue


# ---------------------------------------------------------------------------
# TC-M02-013 — Critérios registrados no log de auditoria [I]
# ---------------------------------------------------------------------------


async def test_selecao_registrada_no_log_auditoria(db: AsyncSession):
    """TC-M02-013."""
    admin = await persist_user(db, email="sel013@t.com", role=UserRole.ADMIN)
    ue = await _make_ue(db, admin)

    candidatos = [
        CandidatoSelecao(id="X1", nome="PcD", criterio=CriteriosPrioridade.PCD),
        CandidatoSelecao(id="X2", nome="Normal", criterio=CriteriosPrioridade.SEM_PRIORIDADE),
    ]
    processo = await confirmar_selecao(
        db,
        unidade_execucao_id=ue.id,
        candidatos=candidatos,
        n_vagas=1,
        criterios_tecnicos="Experiência em análise; PcD prioritário conforme D11 Art.7º",
        user=admin,
    )

    assert processo.criterios_tecnicos.startswith("Experiência")
    assert processo.n_vagas == 1
    resultado_ids = [r["id"] for r in processo.resultado if r["selecionado"]]
    assert resultado_ids == ["X1"]

    logs = (
        await db.execute(
            select(AuditLog).where(AuditLog.table_name == "processos_selecao")
        )
    ).scalars().all()
    assert len(logs) >= 1
    assert logs[0].user_id == admin.id


# ---------------------------------------------------------------------------
# TC-M02-014 — Seleção impessoal exige critérios técnicos [I]
# ---------------------------------------------------------------------------


async def test_selecao_sem_criterios_tecnicos_rejeitada(db: AsyncSession):
    """TC-M02-014."""
    admin = await persist_user(db, email="sel014@t.com", role=UserRole.ADMIN)
    candidatos = [CandidatoSelecao(id="X1", nome="N", criterio=CriteriosPrioridade.PCD)]

    with pytest.raises(ValidationError, match="[Cc]ritérios técnicos"):
        await confirmar_selecao(
            db,
            unidade_execucao_id=uuid.uuid4(),
            candidatos=candidatos,
            n_vagas=1,
            criterios_tecnicos="   ",
            user=admin,
        )


async def test_selecao_criterios_vazios_rejeitada(db: AsyncSession):
    """Variante de TC-M02-014 com string vazia."""
    admin = await persist_user(db, email="sel014b@t.com", role=UserRole.ADMIN)
    candidatos = [CandidatoSelecao(id="X1", nome="N", criterio=CriteriosPrioridade.SEM_PRIORIDADE)]

    with pytest.raises(ValidationError, match="[Cc]ritérios técnicos"):
        await confirmar_selecao(
            db,
            unidade_execucao_id=uuid.uuid4(),
            candidatos=candidatos,
            n_vagas=1,
            criterios_tecnicos="",
            user=admin,
        )
