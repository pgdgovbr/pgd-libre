"""Sprint 1.2 — Participantes e TCR: service + GraphQL tests (TC-M02)."""
import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade, StatusPgd
from src.models.participante import (
    MotivoDesligamento,
    RegimeExecucao,
    StatusConvocacao,
    StatusTCR,
    TipoVinculo,
)
from src.models.user import UserRole
from src.services.institucional import (
    ValidationError,
    criar_ato_autorizacao,
    criar_unidade_autorizadora,
    criar_unidade_instituidora,
)
from src.services.participante import (
    assinar_tcr_chefia,
    cadastrar_participante,
    criar_convocacao,
    desligar_participante,
    get_tcr_ativo,
    pactu_tcr,
    validate_cpf,
    validate_estagio_probatorio,
    validate_matricula_siape,
)

from .conftest import persist_user, set_auth_cookie

# ---------------------------------------------------------------------------
# Pure validators — CPF
# ---------------------------------------------------------------------------


def test_cpf_valid():
    validate_cpf("11144477735")  # no exception


def test_cpf_invalid_digits():
    with pytest.raises(ValidationError, match="CPF inválido"):
        validate_cpf("11144477736")  # wrong check digit


def test_cpf_all_equal():
    with pytest.raises(ValidationError, match="CPF inválido"):
        validate_cpf("11111111111")


def test_cpf_wrong_length():
    with pytest.raises(ValidationError, match="CPF inválido"):
        validate_cpf("1234567890")


def test_cpf_non_digits():
    with pytest.raises(ValidationError, match="CPF inválido"):
        validate_cpf("123.456.789-09")


# ---------------------------------------------------------------------------
# Pure validators — Matrícula SIAPE
# ---------------------------------------------------------------------------


def test_matricula_siape_valid():
    validate_matricula_siape("1234567")  # no exception


def test_matricula_siape_short():
    with pytest.raises(ValidationError, match="7 dígitos"):
        validate_matricula_siape("123456")


def test_matricula_siape_all_equal():
    with pytest.raises(ValidationError, match="inválida"):
        validate_matricula_siape("1111111")


def test_matricula_siape_non_digits():
    with pytest.raises(ValidationError, match="7 dígitos"):
        validate_matricula_siape("ABCDEFG")


# ---------------------------------------------------------------------------
# Pure validators — Estágio probatório
# ---------------------------------------------------------------------------


def test_estagio_probatorio_presencial_dispensado():
    validate_estagio_probatorio(1, False)  # presencial, no exception


def test_estagio_probatorio_teletrabalho_sem_cumprimento():
    with pytest.raises(ValidationError, match="estágio probatório"):
        validate_estagio_probatorio(2, False)


def test_estagio_probatorio_teletrabalho_none():
    with pytest.raises(ValidationError, match="estágio probatório"):
        validate_estagio_probatorio(3, None)


def test_estagio_probatorio_teletrabalho_cumprido():
    validate_estagio_probatorio(4, True)  # no exception


# ---------------------------------------------------------------------------
# Service — Participante cadastro
# ---------------------------------------------------------------------------


async def _make_unidade_com_participante_setup(db, admin):
    """Creates UA + ato + UI + UE for participant tests."""
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=1,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="Min. Teste",
        sigla="MT",
        user=admin,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Min.",
        data_publicacao=date(2024, 1, 1),
        referencia="Port. 001/2024",
        user=admin,
    )
    await db.refresh(ua)
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=100,
        nome="Secretaria Teste",
        sigla="ST",
        ato_instituicao_ref="Port. 002/2024",
        data_instituicao=date(2024, 2, 1),
        tipos_atividades="Análise",
        modalidades_autorizadas=[1, 2],
        conteudo_minimo_tcr="Mínimo",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    from src.models.institucional import UnidadeExecucao

    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=200,
        nome="Unidade Execução Teste",
        sigla="UE",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)
    return ua, ui, ue


async def test_cadastrar_participante_ok(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _make_unidade_com_participante_setup(db, admin)

    p = await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape="1234567",
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome="João Silva",
        email="joao@orgao.gov.br",
        modalidade_execucao=1,
        data_assinatura_tcr=date(2024, 3, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
        user=admin,
    )
    assert p.id is not None
    assert p.situacao == 1
    assert p.cpf == "11144477735"


async def test_cadastrar_participante_cpf_invalido(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _make_unidade_com_participante_setup(db, admin)
    with pytest.raises(ValidationError, match="CPF inválido"):
        await cadastrar_participante(
            db,
            origem_unidade=OrigemUnidade.SIAPE,
            cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
            cod_unidade_lotacao=ue.cod_unidade_executora,
            matricula_siape="1234567",
            cod_unidade_instituidora=ui.cod_unidade_instituidora,
            cpf="11111111111",
            nome="Inválido",
            email="inv@t.com",
            modalidade_execucao=1,
            data_assinatura_tcr=date(2024, 3, 1),
            tipo_vinculo=TipoVinculo.EFETIVO,
            unidade_execucao_id=ue.id,
            user=admin,
        )


async def test_cadastrar_participante_data_tcr_anterior_minima(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _make_unidade_com_participante_setup(db, admin)
    with pytest.raises(ValidationError, match="Decreto 11.072"):
        await cadastrar_participante(
            db,
            origem_unidade=OrigemUnidade.SIAPE,
            cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
            cod_unidade_lotacao=ue.cod_unidade_executora,
            matricula_siape="1234567",
            cod_unidade_instituidora=ui.cod_unidade_instituidora,
            cpf="11144477735",
            nome="Antigo",
            email="old@t.com",
            modalidade_execucao=1,
            data_assinatura_tcr=date(2020, 1, 1),
            tipo_vinculo=TipoVinculo.EFETIVO,
            unidade_execucao_id=ue.id,
            user=admin,
        )


# ---------------------------------------------------------------------------
# Service — Desligamento
# ---------------------------------------------------------------------------


async def test_desligar_participante_ok(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _make_unidade_com_participante_setup(db, admin)
    p = await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape="1234567",
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome="João",
        email="j@t.com",
        modalidade_execucao=1,
        data_assinatura_tcr=date(2024, 3, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
        user=admin,
    )
    result = await desligar_participante(
        db,
        participante_id=p.id,
        motivo=MotivoDesligamento.A_PEDIDO,
        user=admin,
    )
    assert result.situacao == 0
    assert result.motivo_desligamento == MotivoDesligamento.A_PEDIDO
    assert result.data_desligamento is not None


async def test_desligar_participante_sem_motivo(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    with pytest.raises(ValidationError, match="desligamento"):
        await desligar_participante(
            db,
            participante_id=uuid.uuid4(),
            motivo=None,  # type: ignore[arg-type]
            user=admin,
        )


# ---------------------------------------------------------------------------
# Service — TCR
# ---------------------------------------------------------------------------


async def test_pactu_tcr_e_assinar_chefia(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _make_unidade_com_participante_setup(db, admin)
    p = await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape="1234567",
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome="TCR Test",
        email="tcr@t.com",
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
        canais_comunicacao=["email", "teams"],
        responsabilidades="Manter agenda atualizada",
        ciencia_instalacoes_ergonomia=True,
        ciencia_nao_direito_adquirido=True,
        ciencia_custeio_estrutura=True,
        user=admin,
    )
    assert tcr.status == StatusTCR.PENDENTE

    # Before chefia signs, no active TCR
    ativo = await get_tcr_ativo(db, p.id)
    assert ativo is None

    tcr_assinado = await assinar_tcr_chefia(db, tcr_id=tcr.id, user=admin)
    assert tcr_assinado.status == StatusTCR.ATIVO

    ativo = await get_tcr_ativo(db, p.id)
    assert ativo is not None
    assert ativo.id == tcr.id


async def test_tcr_banco_horas_calcula_prazo(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _make_unidade_com_participante_setup(db, admin)
    p = await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape="1234568",
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome="Banco Horas",
        email="bh@t.com",
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
        saldo_banco_horas=10,
        user=admin,
    )
    assert tcr.prazo_compensacao_banco_horas is not None


# ---------------------------------------------------------------------------
# Service — Convocacao
# ---------------------------------------------------------------------------


async def _setup_participante_com_tcr_ativo(db, admin):
    ua, ui, ue = await _make_unidade_com_participante_setup(db, admin)
    p = await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape="1234567",
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome="Conv Test",
        email="conv@t.com",
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
    return p, ue


async def test_criar_convocacao_ok(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    p, ue = await _setup_participante_com_tcr_ativo(db, admin)

    today = date.today()
    c = await criar_convocacao(
        db,
        participante_id=p.id,
        unidade_execucao_id=ue.id,
        canal_comunicacao="email",
        data_convocacao=today,
        data_comparecimento_prevista=today + timedelta(days=7),
        horario_comparecimento="09:00",
        local_comparecimento="Sala 1",
        periodo_presencial_inicio=today + timedelta(days=7),
        periodo_presencial_fim=today + timedelta(days=9),
        motivo="Reunião importante",
        user=admin,
    )
    assert c.id is not None
    assert c.status == StatusConvocacao.PENDENTE


async def test_criar_convocacao_sem_antecedencia(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    p, ue = await _setup_participante_com_tcr_ativo(db, admin)

    today = date.today()
    with pytest.raises(ValidationError, match="antecedência mínima"):
        await criar_convocacao(
            db,
            participante_id=p.id,
            unidade_execucao_id=ue.id,
            canal_comunicacao="email",
            data_convocacao=today,
            data_comparecimento_prevista=today + timedelta(days=2),  # < 5 dias
            horario_comparecimento="09:00",
            local_comparecimento="Sala 1",
            periodo_presencial_inicio=today + timedelta(days=2),
            periodo_presencial_fim=today + timedelta(days=3),
            motivo="Urgente",
            user=admin,
        )
