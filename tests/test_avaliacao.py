"""Sprint 1.5 — Avaliação e Recurso: service tests (TC-M04 avaliação + TC-M08 recurso)."""
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade
from src.models.participante import RegimeExecucao, TipoVinculo
from src.models.plano import DecisaoRecurso, StatusRecurso
from src.models.user import UserRole
from src.services.avaliacao import (
    abrir_recurso,
    avaliar_registros_execucao,
    decidir_recurso,
    validate_justificativa_obrigatoria,
)
from src.services.institucional import (
    ValidationError,
    criar_ato_autorizacao,
    criar_unidade_autorizadora,
    criar_unidade_instituidora,
)
from src.services.participante import (
    assinar_tcr_chefia,
    cadastrar_participante,
    pactu_tcr,
)
from src.services.plano_trabalho import (
    criar_plano_trabalho,
    iniciar_execucao_pt,
    registrar_execucao,
)

from .conftest import persist_user


# ---------------------------------------------------------------------------
# Pure validators
# ---------------------------------------------------------------------------


def test_justificativa_nao_obrigatoria_avaliacao_2():
    validate_justificativa_obrigatoria(2, None)  # no exception


def test_justificativa_nao_obrigatoria_avaliacao_3():
    validate_justificativa_obrigatoria(3, None)  # no exception


def test_justificativa_obrigatoria_avaliacao_1():
    with pytest.raises(ValidationError, match="[Jj]ustificativa"):
        validate_justificativa_obrigatoria(1, None)


def test_justificativa_obrigatoria_avaliacao_4():
    with pytest.raises(ValidationError, match="[Jj]ustificativa"):
        validate_justificativa_obrigatoria(4, "")


def test_justificativa_obrigatoria_avaliacao_5():
    with pytest.raises(ValidationError, match="[Jj]ustificativa"):
        validate_justificativa_obrigatoria(5, "   ")


def test_justificativa_preenchida_avaliacao_1():
    validate_justificativa_obrigatoria(1, "Desempenho excepcional em todos os critérios")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _setup_avaliacao(db, admin):
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=1,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="UA AV",
        sigla="UAV",
        user=admin,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="A",
        data_publicacao=date(2024, 1, 1),
        referencia="R",
        user=admin,
    )
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=100,
        nome="UI AV",
        sigla="UIAV",
        ato_instituicao_ref="R2",
        data_instituicao=date(2024, 1, 10),
        tipos_atividades="T",
        modalidades_autorizadas=[1],
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    from src.models.institucional import UnidadeExecucao

    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=200,
        nome="UE AV",
        sigla="UEAV",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)

    p = await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape="1234567",
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome="Avaliado",
        email="av@t.com",
        modalidade_execucao=1,
        data_assinatura_tcr=date(2024, 3, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
        user=admin,
    )
    tcr = await pactu_tcr(
        db,
        participante_id=p.id,
        chefia_user_id=admin.id,
        modalidade_execucao=1,
        regime_execucao=RegimeExecucao.INTEGRAL,
        prazo_antecedencia_convocacao_dias=5,
        canais_comunicacao=["email"],
        responsabilidades="R",
        ciencia_instalacoes_ergonomia=True,
        ciencia_nao_direito_adquirido=True,
        ciencia_custeio_estrutura=True,
        user=admin,
    )
    await assinar_tcr_chefia(db, tcr_id=tcr.id, user=admin)

    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-AV",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_executora=ue.cod_unidade_executora,
        cod_unidade_lotacao_participante=ue.cod_unidade_executora,
        participante_id=p.id,
        cpf_participante=p.cpf,
        matricula_siape=p.matricula_siape,
        data_inicio=date(2024, 3, 1),
        data_termino=date(2024, 12, 31),
        carga_horaria_disponivel=160,
        criterios_avaliacao="C",
        user=admin,
    )
    pt = await iniciar_execucao_pt(db, plano_id=pt.id, user=admin)

    are = await registrar_execucao(
        db,
        id_periodo_avaliativo="P-AV",
        plano_trabalho_id=pt.id,
        data_inicio_periodo_avaliativo=date(2024, 3, 1),
        data_fim_periodo_avaliativo=date(2024, 3, 31),
        descricao_execucao="Executei tudo",
        user=admin,
    )
    return are


# ---------------------------------------------------------------------------
# Service — Avaliação
# ---------------------------------------------------------------------------


async def test_avaliar_registros_execucao_ok(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    are = await _setup_avaliacao(db, admin)

    result = await avaliar_registros_execucao(
        db,
        avaliacao_id=are.id,
        nota=3,
        data_avaliacao=date(2024, 4, 10),
        user=admin,
    )
    assert result.avaliacao_registros_execucao == 3
    assert result.data_avaliacao_registros_execucao == date(2024, 4, 10)
    assert result.status_recurso is None  # nota 3 não abre recurso


async def test_avaliar_nota_invalida(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    are = await _setup_avaliacao(db, admin)
    with pytest.raises(ValidationError, match="1 e 5"):
        await avaliar_registros_execucao(
            db,
            avaliacao_id=are.id,
            nota=6,
            data_avaliacao=date(2024, 4, 10),
            user=admin,
        )


async def test_avaliar_nota4_sem_justificativa(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    are = await _setup_avaliacao(db, admin)
    with pytest.raises(ValidationError, match="[Jj]ustificativa"):
        await avaliar_registros_execucao(
            db,
            avaliacao_id=are.id,
            nota=4,
            data_avaliacao=date(2024, 4, 10),
            justificativa=None,
            user=admin,
        )


async def test_avaliar_nota4_abre_recurso(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    are = await _setup_avaliacao(db, admin)
    result = await avaliar_registros_execucao(
        db,
        avaliacao_id=are.id,
        nota=4,
        data_avaliacao=date(2024, 4, 10),
        justificativa="Metas não atingidas",
        user=admin,
    )
    assert result.status_recurso == StatusRecurso.ABERTO


# ---------------------------------------------------------------------------
# Service — Recurso
# ---------------------------------------------------------------------------


async def test_abrir_recurso_ok(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    are = await _setup_avaliacao(db, admin)
    await avaliar_registros_execucao(
        db,
        avaliacao_id=are.id,
        nota=4,
        data_avaliacao=date(2024, 4, 10),
        justificativa="Inadequado",
        user=admin,
    )
    result = await abrir_recurso(
        db,
        avaliacao_id=are.id,
        texto="Discordo da avaliação pois realizei todas as entregas",
        user=admin,
    )
    assert result.recurso_texto is not None
    assert result.recurso_data is not None


async def test_abrir_recurso_sem_status_aberto(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    are = await _setup_avaliacao(db, admin)
    await avaliar_registros_execucao(
        db,
        avaliacao_id=are.id,
        nota=3,
        data_avaliacao=date(2024, 4, 10),
        user=admin,
    )
    with pytest.raises(ValidationError, match="recurso"):
        await abrir_recurso(
            db,
            avaliacao_id=are.id,
            texto="Quero recorrer",
            user=admin,
        )


async def test_decidir_recurso_nao_acatado(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    are = await _setup_avaliacao(db, admin)
    await avaliar_registros_execucao(
        db,
        avaliacao_id=are.id,
        nota=5,
        data_avaliacao=date(2024, 4, 10),
        justificativa="Não executou",
        user=admin,
    )
    await abrir_recurso(db, avaliacao_id=are.id, texto="Tinha problema pessoal", user=admin)

    result = await decidir_recurso(
        db,
        avaliacao_id=are.id,
        decisao=DecisaoRecurso.NAO_ACATADO,
        justificativa="Responsabilidade do participante",
        user=admin,
    )
    assert result.recurso_decisao == DecisaoRecurso.NAO_ACATADO
    assert result.status_recurso == StatusRecurso.ENCERRADO
    assert result.avaliacao_registros_execucao == 5  # nota mantida


async def test_decidir_recurso_acatado_muda_nota(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    are = await _setup_avaliacao(db, admin)
    await avaliar_registros_execucao(
        db,
        avaliacao_id=are.id,
        nota=4,
        data_avaliacao=date(2024, 4, 10),
        justificativa="Inadequado",
        user=admin,
    )
    await abrir_recurso(db, avaliacao_id=are.id, texto="Tenho evidências", user=admin)

    result = await decidir_recurso(
        db,
        avaliacao_id=are.id,
        decisao=DecisaoRecurso.ACATADO,
        nova_nota=3,
        justificativa=None,
        user=admin,
    )
    assert result.recurso_decisao == DecisaoRecurso.ACATADO
    assert result.avaliacao_registros_execucao == 3  # nota ajustada
    assert result.status_recurso == StatusRecurso.ENCERRADO


async def test_decidir_recurso_nao_acatado_sem_justificativa(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    are = await _setup_avaliacao(db, admin)
    await avaliar_registros_execucao(
        db,
        avaliacao_id=are.id,
        nota=4,
        data_avaliacao=date(2024, 4, 10),
        justificativa="Inadequado",
        user=admin,
    )
    await abrir_recurso(db, avaliacao_id=are.id, texto="Recurso", user=admin)

    with pytest.raises(ValidationError, match="[Jj]ustificativa"):
        await decidir_recurso(
            db,
            avaliacao_id=are.id,
            decisao=DecisaoRecurso.NAO_ACATADO,
            justificativa=None,
            user=admin,
        )
