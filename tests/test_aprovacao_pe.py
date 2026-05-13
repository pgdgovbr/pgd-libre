"""RF-011 — Aprovação do Plano de Entregas pelo Nível Hierárquico Superior (TC-M03-009 a 011)."""
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade, UnidadeExecucao
from src.models.plano import STATUS_PE_APROVADO, STATUS_PE_EM_EXECUCAO, TipoMeta
from src.models.user import UserRole
from src.services.institucional import (
    ValidationError,
    criar_ato_autorizacao,
    criar_unidade_autorizadora,
    criar_unidade_instituidora,
)
from src.services.plano_entregas import (
    aprovar_plano_entregas,
    criar_entrega,
    criar_plano_entregas,
    iniciar_execucao_pe,
)

from .conftest import persist_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup(db: AsyncSession, admin, cod_ua: int = 70001, coincide: bool = False):
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=cod_ua,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="UA Aprov",
        sigla="UAP",
        user=admin,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Min.",
        data_publicacao=date(2024, 1, 1),
        referencia="P1",
        user=admin,
    )
    await db.refresh(ua)
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=70010,
        nome="UI Aprov",
        sigla="UIP",
        ato_instituicao_ref="P1",
        data_instituicao=date(2024, 1, 1),
        tipos_atividades="T",
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    chefia = await persist_user(db, email=f"chefia{cod_ua}@t.com", role=UserRole.CHEFE_IMEDIATO)
    nivel_sup = await persist_user(db, email=f"sup{cod_ua}@t.com", role=UserRole.GESTOR_UNIDADE)
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=cod_ua + 20,
        nome="UE Aprov",
        sigla="UEP",
        chefia_user_id=chefia.id,
        nivel_superior_user_id=nivel_sup.id,
        coincide_com_instituidora=coincide,
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)

    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-APROV-001",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=cod_ua,
        cod_unidade_instituidora=70010,
        cod_unidade_executora=cod_ua + 20,
        unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 6, 30),
        user=chefia,
    )
    await criar_entrega(
        db,
        id_entrega="E-001",
        plano_entregas_id=pe.id,
        nome_entrega="Entrega 1",
        meta_entrega=10,
        tipo_meta=TipoMeta.UNIDADE,
        data_entrega=date(2026, 6, 30),
        nome_unidade_demandante="Dem",
        nome_unidade_destinataria="Dest",
        user=chefia,
    )
    await db.refresh(pe)
    return ua, ui, ue, pe, chefia, nivel_sup


# ---------------------------------------------------------------------------
# TC-M03-009 — Aprovação registra campos e notifica chefia [I]
# ---------------------------------------------------------------------------


async def test_aprovar_plano_entregas_ok(db: AsyncSession):
    """TC-M03-009."""
    admin = await persist_user(db, email="adm09@t.com", role=UserRole.ADMIN)
    ua, ui, ue, pe, chefia, nivel_sup = await _setup(db, admin)

    pe_aprovado = await aprovar_plano_entregas(
        db,
        plano_id=pe.id,
        aprovador_user_id=nivel_sup.id,
        user=nivel_sup,
    )

    assert pe_aprovado.aprovado_por_user_id == nivel_sup.id
    assert pe_aprovado.data_aprovacao is not None


# ---------------------------------------------------------------------------
# TC-M03-010 — Unidade instituidora dispensa aprovação hierárquica [I]
# ---------------------------------------------------------------------------


async def test_instituidora_dispensa_aprovacao(db: AsyncSession):
    """TC-M03-010: coincide_com_instituidora=True → aprovar levanta ValidationError."""
    admin = await persist_user(db, email="adm10@t.com", role=UserRole.ADMIN)
    ua, ui, ue, pe, chefia, nivel_sup = await _setup(db, admin, cod_ua=70100, coincide=True)

    with pytest.raises(ValidationError, match="[Ii]nstituidora"):
        await aprovar_plano_entregas(
            db,
            plano_id=pe.id,
            aprovador_user_id=nivel_sup.id,
            user=nivel_sup,
        )

    # Mas a chefia pode iniciar execução diretamente (sem aprovação hierárquica)
    pe_execucao = await iniciar_execucao_pe(db, plano_id=pe.id, user=chefia)
    assert pe_execucao.status == STATUS_PE_EM_EXECUCAO


# ---------------------------------------------------------------------------
# TC-M03-011 — Chefia não pode aprovar o próprio plano [I]
# ---------------------------------------------------------------------------


async def test_chefia_nao_aprova_proprio_plano(db: AsyncSession):
    """TC-M03-011."""
    admin = await persist_user(db, email="adm11@t.com", role=UserRole.ADMIN)
    ua, ui, ue, pe, chefia, nivel_sup = await _setup(db, admin, cod_ua=70200)

    with pytest.raises(ValidationError, match="[Cc]hefia"):
        await aprovar_plano_entregas(
            db,
            plano_id=pe.id,
            aprovador_user_id=chefia.id,
            user=chefia,
        )
