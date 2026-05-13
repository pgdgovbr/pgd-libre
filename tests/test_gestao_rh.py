"""RF-031 a RF-036 — Gestão de Pessoas e RH (TC-M09-003..005, TC-M02-026..029, TC-M10-001..004, TC-M10-002, TC-M10-007)."""
import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade, UnidadeExecucao
from src.models.participante import RegimeExecucao, StatusTCR, TipoVinculo
from src.models.plano import TipoMeta
from src.models.user import UserRole
from src.services.avaliacao import mapear_avaliacao_customizada, validate_escala_customizada
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
    registrar_autorizacao_equipamentos,
    validate_acumulacao_cargos_declaracao,
)
from src.services.plano_entregas import criar_entrega, criar_plano_entregas
from src.services.plano_trabalho import (
    adicionar_contribuicao,
    criar_plano_trabalho,
    iniciar_execucao_pt,
    validate_adicional_ocupacional_periodicidade,
)
from src.services.relatorios import relatorio_frequencia

from .conftest import persist_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup(db: AsyncSession, admin, cod_ua: int = 110001):
    ua = await criar_unidade_autorizadora(
        db, cod_unidade_autorizadora=cod_ua, origem_unidade=OrigemUnidade.SIAPE,
        nome="UA RH", sigla="URH", user=admin,
    )
    await criar_ato_autorizacao(
        db, unidade_autorizadora_id=ua.id, autoridade="Min.",
        data_publicacao=date(2024, 1, 1), referencia="P1", user=admin,
    )
    await db.refresh(ua)
    ui = await criar_unidade_instituidora(
        db, unidade_autorizadora_id=ua.id, cod_unidade_instituidora=110010,
        nome="UI RH", sigla="UIH", ato_instituicao_ref="P1",
        data_instituicao=date(2024, 1, 1), tipos_atividades="T",
        conteudo_minimo_tcr="C", prazo_antecedencia_convocacao_dias=5, user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id, cod_unidade_executora=110020,
        nome="UE RH", sigla="UEH",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)
    return ua, ui, ue


async def _make_participante(db, admin, ue, ua, ui, matricula="1110001", cod_ua=110001, modalidade=1):
    return await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=cod_ua,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape=matricula,
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome="Part RH",
        email=f"{matricula}@t.com",
        modalidade_execucao=modalidade,
        data_assinatura_tcr=date(2024, 3, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
        cumpriu_estagio_probatorio=True if modalidade != 1 else None,
        user=admin,
    )


# ---------------------------------------------------------------------------
# RF-031 — Escalas Customizadas (TC-M09-003 a TC-M09-005) [U]
# ---------------------------------------------------------------------------


def test_mapear_avaliacao_customizada_ok():
    """TC-M09-003 — valor 'B' com escala A=1,B=2,C=3,D=4,E=5 → 2."""
    mapeamento = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}
    assert mapear_avaliacao_customizada("B", mapeamento) == 2


def test_mapear_avaliacao_customizada_valor_desconhecido():
    mapeamento = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}
    with pytest.raises(ValidationError, match="não encontrado"):
        mapear_avaliacao_customizada("F", mapeamento)


def test_envio_api_usa_valor_padrao():
    """TC-M09-004 — mapper retorna int, nunca a string customizada."""
    mapeamento = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}
    valor = mapear_avaliacao_customizada("B", mapeamento)
    assert isinstance(valor, int)
    assert valor == 2


def test_escala_customizada_mapeamento_incompleto_rejeitado():
    """TC-M09-005 — escala sem todos os 5 valores é rejeitada."""
    with pytest.raises(ValidationError, match="todos os valores de 1 a 5"):
        validate_escala_customizada({"A": 1, "B": 2, "C": 3})


def test_escala_customizada_mapeamento_completo_ok():
    """TC-M09-005 variante — escala completa é aceita."""
    validate_escala_customizada({"A": 1, "B": 2, "C": 3, "D": 4, "E": 5})  # sem exceção


# ---------------------------------------------------------------------------
# RF-032 — Retirada de Equipamentos (TC-M02-026 a TC-M02-027) [I]
# ---------------------------------------------------------------------------


async def test_equipamentos_vedado_para_tt_parcial(db: AsyncSession):
    """TC-M02-026 — teletrabalho parcial (modalidade 2) não pode retirar equipamentos."""
    admin = await persist_user(db, email="rh026@t.com", role=UserRole.ADMIN)

    with pytest.raises(ValidationError, match="[Tt]eletrabalho integral"):
        await registrar_autorizacao_equipamentos(
            db,
            participante_id=uuid.uuid4(),
            tcr_id=uuid.uuid4(),
            descricao_equipamentos="Notebook",
            data_autorizacao=date(2026, 1, 1),
            modalidade_execucao=2,
            user=admin,
        )


async def test_equipamentos_autorizado_para_tt_integral(db: AsyncSession):
    """TC-M02-027 — teletrabalho integral pode retirar equipamentos."""
    admin = await persist_user(db, email="rh027@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=110002)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1110002", cod_ua=110002, modalidade=3)

    tcr = await pactu_tcr(
        db, participante_id=p.id, chefia_user_id=admin.id,
        modalidade_execucao=3, regime_execucao=RegimeExecucao.INTEGRAL,
        prazo_antecedencia_convocacao_dias=5, canais_comunicacao=["email"],
        responsabilidades="R", ciencia_instalacoes_ergonomia=True,
        ciencia_nao_direito_adquirido=True, ciencia_custeio_estrutura=True,
        user=admin,
    )
    await assinar_tcr_chefia(db, tcr_id=tcr.id, user=admin)

    termo = await registrar_autorizacao_equipamentos(
        db,
        participante_id=p.id,
        tcr_id=tcr.id,
        descricao_equipamentos="Notebook e monitor",
        data_autorizacao=date(2026, 1, 15),
        modalidade_execucao=3,
        user=admin,
    )

    assert termo.tcr_id == tcr.id
    assert termo.participante_id == p.id


# ---------------------------------------------------------------------------
# RF-033 — Acumulação de Cargos (TC-M02-028 a TC-M02-029) [U/I]
# ---------------------------------------------------------------------------


def test_declaracao_ausencia_prejuizo_obrigatoria():
    """TC-M02-028 — acumulador sem declaração completa é rejeitado."""
    with pytest.raises(ValidationError, match="[Dd]eclaração de ausência"):
        validate_acumulacao_cargos_declaracao(
            acumula_cargos=True,
            declaracao_plano=True,
            declaracao_comparecer=True,
            declaracao_contato=False,  # falta este
            declaracao_sincrono=True,
        )


def test_declaracao_ausencia_prejuizo_completa_ok():
    """TC-M02-028 variante — todos confirmados é aceito."""
    validate_acumulacao_cargos_declaracao(
        acumula_cargos=True,
        declaracao_plano=True,
        declaracao_comparecer=True,
        declaracao_contato=True,
        declaracao_sincrono=True,
    )


def test_declaracao_nao_exigida_sem_acumulacao():
    """Sem acumulação, não é exigida declaração."""
    validate_acumulacao_cargos_declaracao(
        acumula_cargos=False,
        declaracao_plano=False,
        declaracao_comparecer=False,
        declaracao_contato=False,
        declaracao_sincrono=False,
    )


async def test_declaracao_acumulacao_persistida(db: AsyncSession):
    """TC-M02-029 — declaração é persistida no plano de trabalho."""
    from src.services.plano_entregas import criar_plano_entregas, criar_entrega

    admin = await persist_user(db, email="rh029@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=110003)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1110003", cod_ua=110003)

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
        db, id_plano_entregas="PE-RH29", origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=110003, cod_unidade_instituidora=110010,
        cod_unidade_executora=110020, unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1), data_termino=date(2026, 12, 31), user=admin,
    )
    await criar_entrega(
        db, id_entrega="E-RH29", plano_entregas_id=pe.id, nome_entrega="E",
        meta_entrega=1, tipo_meta=TipoMeta.UNIDADE, data_entrega=date(2026, 12, 31),
        nome_unidade_demandante="D", nome_unidade_destinataria="D", user=admin,
    )

    # Criar plano com declaração de ausência de prejuízo
    pt = await criar_plano_trabalho(
        db, id_plano_trabalho="PT-RH29", origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=110003, cod_unidade_executora=110020,
        cod_unidade_lotacao_participante=110020, participante_id=p.id,
        cpf_participante=p.cpf, matricula_siape=p.matricula_siape, tcr_id=tcr.id,
        data_inicio=date(2026, 1, 1), data_termino=date(2026, 12, 31),
        carga_horaria_disponivel=2000, criterios_avaliacao="CA",
        plano_entregas_id=pe.id,
        declaracao_ausencia_prejuizo_plano=True,
        declaracao_ausencia_prejuizo_comparecer=True,
        declaracao_ausencia_prejuizo_contato=True,
        declaracao_ausencia_prejuizo_sincrono=True,
        user=admin,
    )
    await adicionar_contribuicao(
        db, plano_trabalho_id=pt.id, id_contribuicao="C1",
        tipo_contribuicao=2, percentual_contribuicao=100, descricao="C", user=admin,
    )

    assert pt.declaracao_ausencia_prejuizo_plano is True
    assert pt.declaracao_ausencia_prejuizo_comparecer is True


# ---------------------------------------------------------------------------
# RF-034 — Ações de Desenvolvimento em Serviço (TC-M10-001) [I]
# ---------------------------------------------------------------------------


async def test_contribuicao_acao_desenvolvimento_persiste_rotulo(db: AsyncSession):
    """TC-M10-001 — contribuição tipo 2 com rótulo 'acao_desenvolvimento' é persistida."""
    from src.services.plano_entregas import criar_plano_entregas, criar_entrega

    admin = await persist_user(db, email="rh101@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=110004)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1110004", cod_ua=110004)

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
        db, id_plano_entregas="PE-RH101", origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=110004, cod_unidade_instituidora=110010,
        cod_unidade_executora=110020, unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1), data_termino=date(2026, 12, 31), user=admin,
    )
    await criar_entrega(
        db, id_entrega="E-RH101", plano_entregas_id=pe.id, nome_entrega="E",
        meta_entrega=1, tipo_meta=TipoMeta.UNIDADE, data_entrega=date(2026, 12, 31),
        nome_unidade_demandante="D", nome_unidade_destinataria="D", user=admin,
    )
    pt = await criar_plano_trabalho(
        db, id_plano_trabalho="PT-RH101", origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=110004, cod_unidade_executora=110020,
        cod_unidade_lotacao_participante=110020, participante_id=p.id,
        cpf_participante=p.cpf, matricula_siape=p.matricula_siape, tcr_id=tcr.id,
        data_inicio=date(2026, 1, 1), data_termino=date(2026, 12, 31),
        carga_horaria_disponivel=2000, criterios_avaliacao="CA",
        plano_entregas_id=pe.id, user=admin,
    )
    contrib = await adicionar_contribuicao(
        db, plano_trabalho_id=pt.id, id_contribuicao="C-DEV",
        tipo_contribuicao=2, percentual_contribuicao=100,
        descricao="Capacitação em gestão de projetos",
        rotulo="acao_desenvolvimento",
        user=admin,
    )

    assert contrib.rotulo == "acao_desenvolvimento"
    assert contrib.tipo_contribuicao == 2


# ---------------------------------------------------------------------------
# RF-035 — Adicionais Ocupacionais (TC-M10-003 a TC-M10-004) [U]
# ---------------------------------------------------------------------------


def test_adicional_ocupacional_plano_90_dias_rejeitado():
    """TC-M10-003 — plano de 90 dias para participante com adicional é rejeitado."""
    with pytest.raises(ValidationError, match="[Pp]eriodicidade mensal"):
        validate_adicional_ocupacional_periodicidade(
            sujeito_adicional_ocupacional=True,
            modalidade_execucao=2,
            data_inicio=date(2026, 1, 1),
            data_termino=date(2026, 3, 31),
        )


def test_adicional_ocupacional_plano_mensal_aceito():
    """TC-M10-003 variante — plano de 30 dias é aceito."""
    validate_adicional_ocupacional_periodicidade(
        sujeito_adicional_ocupacional=True,
        modalidade_execucao=2,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 1, 31),
    )


def test_adicional_ocupacional_tt_integral_nao_aplicavel():
    """TC-M10-004 — teletrabalho integral (mod 3) não aplica a regra de periodicidade."""
    validate_adicional_ocupacional_periodicidade(
        sujeito_adicional_ocupacional=True,
        modalidade_execucao=3,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 3, 31),
    )


def test_sem_adicional_ocupacional_plano_longo_aceito():
    """Sem adicional ocupacional, plano de qualquer duração é aceito."""
    validate_adicional_ocupacional_periodicidade(
        sujeito_adicional_ocupacional=False,
        modalidade_execucao=2,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
    )


# ---------------------------------------------------------------------------
# TC-M10-002 — Rótulo de ação de desenvolvimento aparece no payload da API [U]
# ---------------------------------------------------------------------------


def test_rotulo_no_payload_mapper():
    """TC-M10-002 — contribuição com rotulo é incluída no payload da API Central."""
    from unittest.mock import MagicMock
    from src.integration.mapper import _contribuicao

    c = MagicMock()
    c.id_contribuicao = "C-DEV"
    c.tipo_contribuicao = 2
    c.percentual_contribuicao = 30
    c.id_plano_entregas = None
    c.id_entrega = None
    c.rotulo = "acao_desenvolvimento"

    payload = _contribuicao(c)
    assert payload["rotulo"] == "acao_desenvolvimento"


def test_rotulo_nulo_omitido_no_payload():
    """Contribuição sem rótulo não inclui a chave no payload."""
    from unittest.mock import MagicMock
    from src.integration.mapper import _contribuicao

    c = MagicMock()
    c.id_contribuicao = "C-NORM"
    c.tipo_contribuicao = 2
    c.percentual_contribuicao = 100
    c.id_plano_entregas = None
    c.id_entrega = None
    c.rotulo = None

    payload = _contribuicao(c)
    assert "rotulo" not in payload


# ---------------------------------------------------------------------------
# TC-M10-007 — Relatório de frequência/códigos PGD [I]
# ---------------------------------------------------------------------------


async def test_relatorio_frequencia_retorna_participantes_no_periodo(db: AsyncSession):
    """TC-M10-007 — participantes com PT ativo no período aparecem no relatório."""
    admin = await persist_user(db, email="freq007@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=120001)

    # PE compartilhado por todos os participantes da unidade
    pe = await criar_plano_entregas(
        db, id_plano_entregas="PE-FREQ-1", origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=120001, cod_unidade_instituidora=110010,
        cod_unidade_executora=110020, unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1), data_termino=date(2026, 6, 30), user=admin,
    )
    await criar_entrega(
        db, id_entrega="E-FREQ-1", plano_entregas_id=pe.id, nome_entrega="E",
        meta_entrega=1, tipo_meta=TipoMeta.UNIDADE, data_entrega=date(2026, 6, 30),
        nome_unidade_demandante="D", nome_unidade_destinataria="D", user=admin,
    )

    # 3 participantes com PT em fevereiro/2026
    for i, mat in enumerate(["1200001", "1200002", "1200003"], start=1):
        p = await _make_participante(db, admin, ue, ua, ui, matricula=mat, cod_ua=120001)
        tcr = await pactu_tcr(
            db, participante_id=p.id, chefia_user_id=admin.id,
            modalidade_execucao=1, regime_execucao=RegimeExecucao.INTEGRAL,
            prazo_antecedencia_convocacao_dias=5, canais_comunicacao=["email"],
            responsabilidades="R", ciencia_instalacoes_ergonomia=True,
            ciencia_nao_direito_adquirido=True, ciencia_custeio_estrutura=True,
            user=admin,
        )
        await assinar_tcr_chefia(db, tcr_id=tcr.id, user=admin)
        pt = await criar_plano_trabalho(
            db, id_plano_trabalho=f"PT-FREQ-{i}", origem_unidade=OrigemUnidade.SIAPE,
            cod_unidade_autorizadora=120001, cod_unidade_executora=110020,
            cod_unidade_lotacao_participante=110020, participante_id=p.id,
            cpf_participante=p.cpf, matricula_siape=p.matricula_siape, tcr_id=tcr.id,
            data_inicio=date(2026, 1, 1), data_termino=date(2026, 6, 30),
            carga_horaria_disponivel=1040, criterios_avaliacao="CA",
            plano_entregas_id=pe.id, user=admin,
        )
        await adicionar_contribuicao(
            db, plano_trabalho_id=pt.id, id_contribuicao=f"C-FREQ-{i}",
            tipo_contribuicao=2, percentual_contribuicao=100, descricao="C", user=admin,
        )
        await iniciar_execucao_pt(db, plano_id=pt.id, user=admin)

    # Participante sem PT no período — não deve aparecer
    p_sem = await _make_participante(db, admin, ue, ua, ui, matricula="1200099", cod_ua=120001)

    resultado = await relatorio_frequencia(db, cod_unidade_autorizadora=120001, ano=2026, mes=2)
    ids = [r.id for r in resultado]

    assert len([x for x in ids if x != p_sem.id]) >= 3
    assert p_sem.id not in ids
