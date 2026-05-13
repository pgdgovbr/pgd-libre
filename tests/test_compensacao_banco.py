"""RF-019 + RF-020 — Compensação de Carga Horária e Banco de Horas (TC-M04-033 a 036)."""
from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade, UnidadeExecucao
from src.models.participante import RegimeExecucao, StatusTCR, TipoVinculo
from src.models.plano import AvaliacaoRegistrosExecucao, STATUS_PT_EM_EXECUCAO
from src.models.user import UserRole
from src.services.institucional import (
    ValidationError,
    criar_ato_autorizacao,
    criar_unidade_autorizadora,
    criar_unidade_instituidora,
)
from src.services.participante import (
    assinar_tcr_chefia,
    bloquear_adesao_banco_horas,
    cadastrar_participante,
    get_carga_compensacao_pendente,
    pactu_tcr,
)
from src.services.plano_trabalho import validate_soma_percentuais

from .conftest import persist_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_setup(db: AsyncSession, admin, cod_ua: int = 80001):
    ua = await criar_unidade_autorizadora(
        db, cod_unidade_autorizadora=cod_ua, origem_unidade=OrigemUnidade.SIAPE,
        nome="UA CB", sigla="UCB", user=admin,
    )
    await criar_ato_autorizacao(
        db, unidade_autorizadora_id=ua.id, autoridade="Min.",
        data_publicacao=date(2024, 1, 1), referencia="P1", user=admin,
    )
    await db.refresh(ua)
    ui = await criar_unidade_instituidora(
        db, unidade_autorizadora_id=ua.id, cod_unidade_instituidora=80010,
        nome="UI CB", sigla="UCB", ato_instituicao_ref="P1",
        data_instituicao=date(2024, 1, 1), tipos_atividades="T",
        conteudo_minimo_tcr="C", prazo_antecedencia_convocacao_dias=5, user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id, cod_unidade_executora=80020,
        nome="UE CB", sigla="UCB",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)
    return ua, ui, ue


async def _make_participante(db, admin, ue, ua, ui, matricula="1234569", cod_ua=80001):
    p = await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=cod_ua,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape=matricula,
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome="Participante CB",
        email=f"{matricula}@t.com",
        modalidade_execucao=1,
        data_assinatura_tcr=date(2024, 3, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
        user=admin,
    )
    return p


# ---------------------------------------------------------------------------
# TC-M04-033 — Próximo plano pré-preenchido com carga de compensação [I]
# ---------------------------------------------------------------------------


async def test_get_carga_compensacao_pendente(db: AsyncSession):
    """TC-M04-033 — get_carga_compensacao_pendente retorna horas da inexecução."""
    from src.services.plano_entregas import criar_plano_entregas, criar_entrega
    from src.services.plano_trabalho import (
        adicionar_contribuicao,
        criar_plano_trabalho,
        iniciar_execucao_pt,
        registrar_execucao,
    )
    from src.models.plano import TipoMeta

    admin = await persist_user(db, email="cb033@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _make_setup(db, admin)
    p = await _make_participante(db, admin, ue, ua, ui)

    tcr = await pactu_tcr(
        db, participante_id=p.id, chefia_user_id=admin.id,
        modalidade_execucao=1, regime_execucao=RegimeExecucao.INTEGRAL,
        prazo_antecedencia_convocacao_dias=5, canais_comunicacao=["email"],
        responsabilidades="R", ciencia_instalacoes_ergonomia=True,
        ciencia_nao_direito_adquirido=True, ciencia_custeio_estrutura=True,
        user=admin,
    )
    await assinar_tcr_chefia(db, tcr_id=tcr.id, user=admin)

    pe = await criar_plano_entregas(
        db, id_plano_entregas="PE-CB-001", origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=80001, cod_unidade_instituidora=80010,
        cod_unidade_executora=80020, unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1), data_termino=date(2026, 3, 31), user=admin,
    )
    await criar_entrega(
        db, id_entrega="E-001", plano_entregas_id=pe.id, nome_entrega="E",
        meta_entrega=10, tipo_meta=TipoMeta.UNIDADE,
        data_entrega=date(2026, 3, 31),
        nome_unidade_demandante="D", nome_unidade_destinataria="D", user=admin,
    )

    pt = await criar_plano_trabalho(
        db, id_plano_trabalho="PT-CB-001", origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=80001, cod_unidade_executora=80020,
        cod_unidade_lotacao_participante=80020, participante_id=p.id,
        cpf_participante=p.cpf, matricula_siape=p.matricula_siape, tcr_id=tcr.id,
        data_inicio=date(2026, 1, 1), data_termino=date(2026, 3, 31),
        carga_horaria_disponivel=504, criterios_avaliacao="CA",
        plano_entregas_id=pe.id, user=admin,
    )
    await adicionar_contribuicao(
        db, plano_trabalho_id=pt.id, id_contribuicao="C1",
        tipo_contribuicao=2, percentual_contribuicao=100,
        descricao="Contrib", user=admin,
    )
    await iniciar_execucao_pt(db, plano_id=pt.id, user=admin)

    # Registrar avaliação com inexecução de 20 horas
    avaliacao = AvaliacaoRegistrosExecucao(
        id_periodo_avaliativo="PA-001",
        plano_trabalho_id=pt.id,
        data_inicio_periodo_avaliativo=date(2026, 1, 1),
        data_fim_periodo_avaliativo=date(2026, 3, 31),
        avaliacao_registros_execucao=4,
        data_avaliacao_registros_execucao=date(2026, 4, 5),
        avaliacao_justificativa="Inexecução parcial",
        horas_inexecucao=20,
    )
    db.add(avaliacao)
    await db.commit()

    carga = await get_carga_compensacao_pendente(db, p.id)
    assert carga == 20


async def test_carga_compensacao_zero_sem_inexecucao(db: AsyncSession):
    """TC-M04-033 variante — sem avaliação de inexecução retorna 0."""
    admin = await persist_user(db, email="cb033b@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _make_setup(db, admin, cod_ua=80002)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1234560", cod_ua=80002)

    carga = await get_carga_compensacao_pendente(db, p.id)
    assert carga == 0


# ---------------------------------------------------------------------------
# TC-M04-033b — TCR com compensação exige prazo [U]
# ---------------------------------------------------------------------------


async def test_tcr_carga_compensacao_exige_prazo(db: AsyncSession):
    """TCR com carga_horaria_compensacao > 0 requer prazo_compensacao_inexecucao."""
    admin = await persist_user(db, email="cb033c@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _make_setup(db, admin, cod_ua=80003)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1234561", cod_ua=80003)

    with pytest.raises(ValidationError, match="[Pp]razo de compensação"):
        await pactu_tcr(
            db, participante_id=p.id, chefia_user_id=admin.id,
            modalidade_execucao=1, regime_execucao=RegimeExecucao.INTEGRAL,
            prazo_antecedencia_convocacao_dias=5, canais_comunicacao=["email"],
            responsabilidades="R", ciencia_instalacoes_ergonomia=True,
            ciencia_nao_direito_adquirido=True, ciencia_custeio_estrutura=True,
            carga_horaria_compensacao=20,
            prazo_compensacao_inexecucao=None,
            user=admin,
        )


async def test_tcr_carga_compensacao_com_prazo_ok(db: AsyncSession):
    """TCR com carga_horaria_compensacao > 0 e prazo é aceito."""
    admin = await persist_user(db, email="cb033d@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _make_setup(db, admin, cod_ua=80004)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1234562", cod_ua=80004)

    tcr = await pactu_tcr(
        db, participante_id=p.id, chefia_user_id=admin.id,
        modalidade_execucao=1, regime_execucao=RegimeExecucao.INTEGRAL,
        prazo_antecedencia_convocacao_dias=5, canais_comunicacao=["email"],
        responsabilidades="R", ciencia_instalacoes_ergonomia=True,
        ciencia_nao_direito_adquirido=True, ciencia_custeio_estrutura=True,
        carga_horaria_compensacao=20,
        prazo_compensacao_inexecucao=date(2026, 6, 30),
        user=admin,
    )
    assert tcr.carga_horaria_compensacao == 20
    assert tcr.prazo_compensacao_inexecucao == date(2026, 6, 30)


# ---------------------------------------------------------------------------
# TC-M04-034 — Soma > 100% com compensação é aceita [U]
# ---------------------------------------------------------------------------


def test_soma_percentuais_com_compensacao_aceita():
    """TC-M04-034."""
    validate_soma_percentuais([60, 60], carga_horaria_compensacao=20)  # sem exceção


# ---------------------------------------------------------------------------
# TC-M04-035 — Nova adesão ao banco de horas bloqueada para participantes do PGD [I]
# ---------------------------------------------------------------------------


def test_bloquear_adesao_banco_horas_participante_ativo():
    """TC-M04-035."""
    with pytest.raises(ValidationError, match="banco de horas"):
        bloquear_adesao_banco_horas(participante_situacao=1)


def test_bloquear_adesao_banco_horas_participante_inativo():
    """Participante inativo não é bloqueado."""
    bloquear_adesao_banco_horas(participante_situacao=0)  # sem exceção


# ---------------------------------------------------------------------------
# TC-M04-036 — Saldo de banco de horas registrado no TCR [I]
# ---------------------------------------------------------------------------


async def test_tcr_saldo_banco_horas_prazo_6_meses(db: AsyncSession):
    """TC-M04-036 — saldo_banco_horas registra prazo_compensacao_banco_horas."""
    admin = await persist_user(db, email="cb036@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _make_setup(db, admin, cod_ua=80005)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1234563", cod_ua=80005)

    tcr = await pactu_tcr(
        db, participante_id=p.id, chefia_user_id=admin.id,
        modalidade_execucao=1, regime_execucao=RegimeExecucao.INTEGRAL,
        prazo_antecedencia_convocacao_dias=5, canais_comunicacao=["email"],
        responsabilidades="R", ciencia_instalacoes_ergonomia=True,
        ciencia_nao_direito_adquirido=True, ciencia_custeio_estrutura=True,
        saldo_banco_horas=15,
        user=admin,
    )

    assert tcr.saldo_banco_horas == 15
    assert tcr.prazo_compensacao_banco_horas is not None
    from dateutil.relativedelta import relativedelta
    from datetime import date
    esperado = date.today() + relativedelta(months=6)
    assert tcr.prazo_compensacao_banco_horas == esperado
