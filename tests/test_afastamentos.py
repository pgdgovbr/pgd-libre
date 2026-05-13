"""Sprint 2.6 — TC-M10-008: Afastamentos legais com código PGD diferenciado.

O relatório de frequência (`relatorio_frequencia`) lista participantes com PT ativo,
mas afastamentos legais (licença médica, maternidade, etc.) precisam ser destacados
porque têm código PGD diferente no SIAPE Frequência. Esta sprint adiciona o modelo
`Afastamento`, o serviço `registrar_afastamento()`, o relatório
`relatorio_afastamentos()` e a camada GraphQL correspondente.
"""
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade, UnidadeExecucao
from src.models.participante import (
    RegimeExecucao,
    TipoVinculo,
)
from src.models.plano import TipoMeta
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
    pactu_tcr,
)
from src.services.plano_entregas import criar_entrega, criar_plano_entregas
from src.services.plano_trabalho import (
    adicionar_contribuicao,
    criar_plano_trabalho,
    iniciar_execucao_pt,
)

from .conftest import persist_user, set_auth_cookie


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup(db: AsyncSession, admin, cod_ua: int = 130001):
    ua = await criar_unidade_autorizadora(
        db, cod_unidade_autorizadora=cod_ua, origem_unidade=OrigemUnidade.SIAPE,
        nome="UA AFA", sigla="UAF", user=admin,
    )
    await criar_ato_autorizacao(
        db, unidade_autorizadora_id=ua.id, autoridade="Min.",
        data_publicacao=date(2024, 1, 1), referencia="AFA", user=admin,
    )
    await db.refresh(ua)
    ui = await criar_unidade_instituidora(
        db, unidade_autorizadora_id=ua.id, cod_unidade_instituidora=130010,
        nome="UI AFA", sigla="UIF", ato_instituicao_ref="AFA",
        data_instituicao=date(2024, 1, 1), tipos_atividades="T",
        conteudo_minimo_tcr="C", prazo_antecedencia_convocacao_dias=5, user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id, cod_unidade_executora=130020,
        nome="UE AFA", sigla="UEF",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)
    return ua, ui, ue


async def _make_participante(db, admin, ue, ua, ui, matricula="1300001", cod_ua=130001, modalidade=1):
    return await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=cod_ua,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape=matricula,
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome=f"Part AFA {matricula}",
        email=f"{matricula}@t.com",
        modalidade_execucao=modalidade,
        data_assinatura_tcr=date(2024, 3, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
        cumpriu_estagio_probatorio=True if modalidade != 1 else None,
        user=admin,
    )


# ---------------------------------------------------------------------------
# Unit / Integration — service registrar_afastamento
# ---------------------------------------------------------------------------


async def test_registrar_afastamento_licenca_medica_ok(db: AsyncSession):
    """Afastamento por licença médica é criado e persistido."""
    from src.models.participante import TipoAfastamento
    from src.services.participante import registrar_afastamento

    admin = await persist_user(db, email="afa1@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=130001)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1300001", cod_ua=130001)

    afa = await registrar_afastamento(
        db,
        participante_id=p.id,
        tipo_afastamento=TipoAfastamento.LICENCA_MEDICA,
        data_inicio=date(2026, 2, 10),
        data_fim=date(2026, 2, 20),
        observacao="Atestado de 10 dias",
        user=admin,
    )

    assert afa.participante_id == p.id
    assert afa.tipo_afastamento == TipoAfastamento.LICENCA_MEDICA
    assert afa.data_inicio == date(2026, 2, 10)
    assert afa.data_fim == date(2026, 2, 20)
    assert afa.observacao == "Atestado de 10 dias"


async def test_registrar_afastamento_em_curso_sem_data_fim(db: AsyncSession):
    """Afastamento em curso (licença maternidade) pode ser registrado sem data_fim."""
    from src.models.participante import TipoAfastamento
    from src.services.participante import registrar_afastamento

    admin = await persist_user(db, email="afa2@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=130002)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1300002", cod_ua=130002)

    afa = await registrar_afastamento(
        db,
        participante_id=p.id,
        tipo_afastamento=TipoAfastamento.LICENCA_MATERNIDADE,
        data_inicio=date(2026, 2, 1),
        user=admin,
    )

    assert afa.data_fim is None
    assert afa.tipo_afastamento == TipoAfastamento.LICENCA_MATERNIDADE


async def test_registrar_afastamento_data_fim_anterior_inicio_rejeitado(db: AsyncSession):
    """Data fim anterior à data início é rejeitada."""
    from src.models.participante import TipoAfastamento
    from src.services.participante import registrar_afastamento

    admin = await persist_user(db, email="afa3@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=130003)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1300003", cod_ua=130003)

    with pytest.raises(ValidationError, match="[Dd]ata"):
        await registrar_afastamento(
            db,
            participante_id=p.id,
            tipo_afastamento=TipoAfastamento.FERIAS,
            data_inicio=date(2026, 3, 10),
            data_fim=date(2026, 3, 5),
            user=admin,
        )


# ---------------------------------------------------------------------------
# Integration — TC-M10-008: relatorio_afastamentos no período
# ---------------------------------------------------------------------------


async def test_relatorio_afastamentos_destaca_afastados_no_periodo(db: AsyncSession):
    """TC-M10-008 — afastamentos no período aparecem no relatório separado.

    Setup: 3 participantes com PT ativo em fevereiro/2026; um deles está em
    licença médica de 10/02 a 20/02. O relatório de afastamentos deve listar
    somente esse afastamento (não os demais participantes).
    """
    from src.models.participante import TipoAfastamento
    from src.services.participante import registrar_afastamento
    from src.services.relatorios import relatorio_afastamentos, relatorio_frequencia

    admin = await persist_user(db, email="afa10@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=130010)

    pe = await criar_plano_entregas(
        db, id_plano_entregas="PE-AFA-1", origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=130010, cod_unidade_instituidora=130010,
        cod_unidade_executora=130020, unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1), data_termino=date(2026, 6, 30), user=admin,
    )
    await criar_entrega(
        db, id_entrega="E-AFA-1", plano_entregas_id=pe.id, nome_entrega="E",
        meta_entrega=1, tipo_meta=TipoMeta.UNIDADE, data_entrega=date(2026, 6, 30),
        nome_unidade_demandante="D", nome_unidade_destinataria="D", user=admin,
    )

    participantes = []
    for i, mat in enumerate(["1300010", "1300011", "1300012"], start=1):
        p = await _make_participante(db, admin, ue, ua, ui, matricula=mat, cod_ua=130010)
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
            db, id_plano_trabalho=f"PT-AFA-{i}", origem_unidade=OrigemUnidade.SIAPE,
            cod_unidade_autorizadora=130010, cod_unidade_executora=130020,
            cod_unidade_lotacao_participante=130020, participante_id=p.id,
            cpf_participante=p.cpf, matricula_siape=p.matricula_siape, tcr_id=tcr.id,
            data_inicio=date(2026, 1, 1), data_termino=date(2026, 6, 30),
            carga_horaria_disponivel=1040, criterios_avaliacao="CA",
            plano_entregas_id=pe.id, user=admin,
        )
        await adicionar_contribuicao(
            db, plano_trabalho_id=pt.id, id_contribuicao=f"C-AFA-{i}",
            tipo_contribuicao=2, percentual_contribuicao=100, descricao="C", user=admin,
        )
        await iniciar_execucao_pt(db, plano_id=pt.id, user=admin)
        participantes.append(p)

    # Apenas o primeiro participante está afastado em fevereiro
    await registrar_afastamento(
        db,
        participante_id=participantes[0].id,
        tipo_afastamento=TipoAfastamento.LICENCA_MEDICA,
        data_inicio=date(2026, 2, 10),
        data_fim=date(2026, 2, 20),
        observacao="Atestado",
        user=admin,
    )

    # relatorio_frequencia continua retornando todos os participantes
    freq = await relatorio_frequencia(db, cod_unidade_autorizadora=130010, ano=2026, mes=2)
    assert len(freq) == 3

    # relatorio_afastamentos retorna SÓ o que está afastado em fev/2026
    afastados = await relatorio_afastamentos(
        db, cod_unidade_autorizadora=130010, ano=2026, mes=2
    )
    assert len(afastados) == 1
    assert afastados[0].participante_id == participantes[0].id
    assert afastados[0].tipo_afastamento == TipoAfastamento.LICENCA_MEDICA


async def test_relatorio_afastamentos_fora_periodo_excluido(db: AsyncSession):
    """Afastamento que termina antes do mês de referência não aparece."""
    from src.models.participante import TipoAfastamento
    from src.services.participante import registrar_afastamento
    from src.services.relatorios import relatorio_afastamentos

    admin = await persist_user(db, email="afa11@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=130011)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1300020", cod_ua=130011)

    # Afastamento em janeiro/2026
    await registrar_afastamento(
        db,
        participante_id=p.id,
        tipo_afastamento=TipoAfastamento.FERIAS,
        data_inicio=date(2026, 1, 5),
        data_fim=date(2026, 1, 25),
        user=admin,
    )

    # Consultando março/2026 não deve retornar nada
    afastados = await relatorio_afastamentos(
        db, cod_unidade_autorizadora=130011, ano=2026, mes=3
    )
    assert afastados == []


async def test_relatorio_afastamentos_em_curso_aparece(db: AsyncSession):
    """Afastamento sem data_fim (em curso) aparece em qualquer mês após o início."""
    from src.models.participante import TipoAfastamento
    from src.services.participante import registrar_afastamento
    from src.services.relatorios import relatorio_afastamentos

    admin = await persist_user(db, email="afa12@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=130012)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1300030", cod_ua=130012)

    await registrar_afastamento(
        db,
        participante_id=p.id,
        tipo_afastamento=TipoAfastamento.LICENCA_MATERNIDADE,
        data_inicio=date(2026, 1, 15),
        user=admin,  # sem data_fim
    )

    afastados_jan = await relatorio_afastamentos(db, cod_unidade_autorizadora=130012, ano=2026, mes=1)
    afastados_mar = await relatorio_afastamentos(db, cod_unidade_autorizadora=130012, ano=2026, mes=3)
    assert len(afastados_jan) == 1
    assert len(afastados_mar) == 1


# ---------------------------------------------------------------------------
# GraphQL — registrarAfastamento mutation + relatorioAfastamentos query
# ---------------------------------------------------------------------------


async def test_gql_registrar_afastamento(db: AsyncSession, client: AsyncClient):
    """Mutation registrarAfastamento cria o afastamento via GraphQL."""
    admin = await persist_user(db, email="afa_gql@t.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ui, ue = await _setup(db, admin, cod_ua=130020)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1300100", cod_ua=130020)

    mutation = """
    mutation($input: RegistrarAfastamentoInput!) {
      registrarAfastamento(input: $input) {
        id
        participanteId
        tipoAfastamento
        dataInicio
        dataFim
        observacao
      }
    }
    """
    variables = {
        "input": {
            "participanteId": str(p.id),
            "tipoAfastamento": "LICENCA_MEDICA",
            "dataInicio": "2026-04-01",
            "dataFim": "2026-04-15",
            "observacao": "Atestado 15 dias",
        }
    }
    resp = await client.post(
        "/graphql",
        json={"query": mutation, "variables": variables},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    afa = data["data"]["registrarAfastamento"]
    assert afa["participanteId"] == str(p.id)
    assert afa["tipoAfastamento"] == "LICENCA_MEDICA"
    assert afa["dataInicio"] == "2026-04-01"
    assert afa["dataFim"] == "2026-04-15"
    assert afa["observacao"] == "Atestado 15 dias"


async def test_gql_relatorio_afastamentos(db: AsyncSession, client: AsyncClient):
    """Query relatorioAfastamentos retorna afastamentos no período."""
    from src.models.participante import TipoAfastamento
    from src.services.participante import registrar_afastamento

    admin = await persist_user(
        db, email="afa_gql_rel@t.com", role=UserRole.GESTOR_UNIDADE,
        cod_unidade_autorizadora=130030,
    )
    set_auth_cookie(client, admin)
    ua, ui, ue = await _setup(db, admin, cod_ua=130030)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1300200", cod_ua=130030)

    await registrar_afastamento(
        db,
        participante_id=p.id,
        tipo_afastamento=TipoAfastamento.LICENCA_CAPACITACAO,
        data_inicio=date(2026, 5, 1),
        data_fim=date(2026, 5, 20),
        user=admin,
    )

    query = """
    query($ua: Int!, $ano: Int!, $mes: Int!) {
      relatorioAfastamentos(codUnidadeAutorizadora: $ua, ano: $ano, mes: $mes) {
        id
        participanteId
        tipoAfastamento
        dataInicio
        dataFim
      }
    }
    """
    resp = await client.post(
        "/graphql",
        json={"query": query, "variables": {"ua": 130030, "ano": 2026, "mes": 5}},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    rows = data["data"]["relatorioAfastamentos"]
    assert len(rows) == 1
    assert rows[0]["participanteId"] == str(p.id)
    assert rows[0]["tipoAfastamento"] == "LICENCA_CAPACITACAO"
