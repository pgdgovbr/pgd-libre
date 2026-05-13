"""Sprint 2.7 — TC-M10-005/006: Adicional Noturno.

Servidores em teletrabalho que trabalham regularmente em horário noturno
(22h–05h) têm direito a adicional noturno, mas precisam de autorização
prévia da chefia.

TC-M10-005: criação da autorização com período e janela horária.
TC-M10-006: PT com `trabalho_noturno=True` sem autorização vigente é rejeitado.
"""
import uuid
from datetime import date, time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade, UnidadeExecucao
from src.models.participante import RegimeExecucao, TipoVinculo
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
)

from .conftest import persist_user, set_auth_cookie


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup(db: AsyncSession, admin, cod_ua: int = 140001):
    ua = await criar_unidade_autorizadora(
        db, cod_unidade_autorizadora=cod_ua, origem_unidade=OrigemUnidade.SIAPE,
        nome="UA NOT", sigla="UNO", user=admin,
    )
    await criar_ato_autorizacao(
        db, unidade_autorizadora_id=ua.id, autoridade="Min.",
        data_publicacao=date(2024, 1, 1), referencia="NOT", user=admin,
    )
    await db.refresh(ua)
    ui = await criar_unidade_instituidora(
        db, unidade_autorizadora_id=ua.id, cod_unidade_instituidora=140010,
        nome="UI NOT", sigla="UIN", ato_instituicao_ref="NOT",
        data_instituicao=date(2024, 1, 1), tipos_atividades="T",
        conteudo_minimo_tcr="C", prazo_antecedencia_convocacao_dias=5, user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id, cod_unidade_executora=140020,
        nome="UE NOT", sigla="UEN",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)
    return ua, ui, ue


async def _make_participante(db, admin, ue, ua, ui, matricula="1400001", cod_ua=140001, modalidade=3):
    return await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=cod_ua,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape=matricula,
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome=f"Part NOT {matricula}",
        email=f"{matricula}@t.com",
        modalidade_execucao=modalidade,
        data_assinatura_tcr=date(2024, 3, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
        cumpriu_estagio_probatorio=True if modalidade in (2, 3, 4, 5) else None,
        user=admin,
    )


async def _make_pe_pt_base(db, admin, ua, ui, ue, p, cod_ua, suffix, *, trabalho_noturno=False):
    """Cria PE + entrega + TCR ativo + retorna o tcr e o PE para uso no PT."""
    tcr = await pactu_tcr(
        db, participante_id=p.id, chefia_user_id=admin.id,
        modalidade_execucao=3, regime_execucao=RegimeExecucao.INTEGRAL,
        prazo_antecedencia_convocacao_dias=5, canais_comunicacao=["email"],
        responsabilidades="R", ciencia_instalacoes_ergonomia=True,
        ciencia_nao_direito_adquirido=True, ciencia_custeio_estrutura=True,
        user=admin,
    )
    await assinar_tcr_chefia(db, tcr_id=tcr.id, user=admin)
    pe = await criar_plano_entregas(
        db, id_plano_entregas=f"PE-NOT-{suffix}", origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=cod_ua, cod_unidade_instituidora=140010,
        cod_unidade_executora=140020, unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1), data_termino=date(2026, 12, 31), user=admin,
    )
    await criar_entrega(
        db, id_entrega=f"E-NOT-{suffix}", plano_entregas_id=pe.id, nome_entrega="E",
        meta_entrega=1, tipo_meta=TipoMeta.UNIDADE, data_entrega=date(2026, 12, 31),
        nome_unidade_demandante="D", nome_unidade_destinataria="D", user=admin,
    )
    return tcr, pe


# ---------------------------------------------------------------------------
# TC-M10-005 — autorizar_adicional_noturno service
# ---------------------------------------------------------------------------


async def test_autorizar_adicional_noturno_default_horario(db: AsyncSession):
    """TC-M10-005 — autorização criada com janela padrão 22h-05h."""
    from src.services.participante import autorizar_adicional_noturno

    admin = await persist_user(db, email="not1@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=140001)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1400001", cod_ua=140001)

    auth = await autorizar_adicional_noturno(
        db,
        participante_id=p.id,
        data_inicio_autorizacao=date(2026, 1, 1),
        data_fim_autorizacao=date(2026, 12, 31),
        justificativa="Plantão noturno do setor X",
        user=admin,
    )
    assert auth.participante_id == p.id
    assert auth.horario_inicio_noturno == time(22, 0)
    assert auth.horario_fim_noturno == time(5, 0)
    assert auth.autorizado_por_user_id == admin.id
    assert auth.justificativa == "Plantão noturno do setor X"


async def test_autorizar_adicional_noturno_horario_customizado(db: AsyncSession):
    """Janela horária pode ser customizada (ex.: turno 23h-06h)."""
    from src.services.participante import autorizar_adicional_noturno

    admin = await persist_user(db, email="not2@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=140002)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1400002", cod_ua=140002)

    auth = await autorizar_adicional_noturno(
        db,
        participante_id=p.id,
        data_inicio_autorizacao=date(2026, 1, 1),
        horario_inicio_noturno=time(23, 0),
        horario_fim_noturno=time(6, 0),
        user=admin,
    )
    assert auth.horario_inicio_noturno == time(23, 0)
    assert auth.horario_fim_noturno == time(6, 0)
    assert auth.data_fim_autorizacao is None


async def test_autorizar_adicional_noturno_data_fim_anterior_inicio_rejeitado(db: AsyncSession):
    """Data fim anterior à data início é rejeitada."""
    from src.services.participante import autorizar_adicional_noturno

    admin = await persist_user(db, email="not3@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=140003)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1400003", cod_ua=140003)

    with pytest.raises(ValidationError, match="[Dd]ata"):
        await autorizar_adicional_noturno(
            db,
            participante_id=p.id,
            data_inicio_autorizacao=date(2026, 5, 1),
            data_fim_autorizacao=date(2026, 4, 30),
            user=admin,
        )


# ---------------------------------------------------------------------------
# TC-M10-006 — validate_adicional_noturno_autorizado
# ---------------------------------------------------------------------------


async def test_validate_pt_diurno_nao_exige_autorizacao(db: AsyncSession):
    """PT sem flag noturna não requer autorização (nenhum erro)."""
    from src.services.participante import validate_adicional_noturno_autorizado

    admin = await persist_user(db, email="not4@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=140004)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1400004", cod_ua=140004)

    # Sem autorização cadastrada, mas trabalho_noturno=False → ok
    await validate_adicional_noturno_autorizado(
        db,
        participante_id=p.id,
        trabalho_noturno=False,
        data_inicio_pt=date(2026, 2, 1),
        data_termino_pt=date(2026, 7, 31),
    )


async def test_validate_pt_noturno_sem_autorizacao_rejeitado(db: AsyncSession):
    """TC-M10-006 — PT com trabalho_noturno=True sem autorização vigente é rejeitado."""
    from src.services.participante import validate_adicional_noturno_autorizado

    admin = await persist_user(db, email="not5@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=140005)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1400005", cod_ua=140005)

    with pytest.raises(ValidationError, match="[Aa]utorização"):
        await validate_adicional_noturno_autorizado(
            db,
            participante_id=p.id,
            trabalho_noturno=True,
            data_inicio_pt=date(2026, 2, 1),
            data_termino_pt=date(2026, 7, 31),
        )


async def test_validate_pt_noturno_com_autorizacao_vigente_ok(db: AsyncSession):
    """TC-M10-005 (variante) — PT noturno com autorização cobrindo o período é aceito."""
    from src.services.participante import (
        autorizar_adicional_noturno,
        validate_adicional_noturno_autorizado,
    )

    admin = await persist_user(db, email="not6@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=140006)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1400006", cod_ua=140006)

    await autorizar_adicional_noturno(
        db,
        participante_id=p.id,
        data_inicio_autorizacao=date(2026, 1, 1),
        data_fim_autorizacao=date(2026, 12, 31),
        user=admin,
    )

    # sem exceção
    await validate_adicional_noturno_autorizado(
        db,
        participante_id=p.id,
        trabalho_noturno=True,
        data_inicio_pt=date(2026, 2, 1),
        data_termino_pt=date(2026, 7, 31),
    )


async def test_validate_pt_noturno_autorizacao_fora_periodo_rejeitado(db: AsyncSession):
    """Autorização que termina antes do PT não cobre o plano."""
    from src.services.participante import (
        autorizar_adicional_noturno,
        validate_adicional_noturno_autorizado,
    )

    admin = await persist_user(db, email="not7@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=140007)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1400007", cod_ua=140007)

    # Autorização vence em jan/2026
    await autorizar_adicional_noturno(
        db,
        participante_id=p.id,
        data_inicio_autorizacao=date(2025, 6, 1),
        data_fim_autorizacao=date(2026, 1, 31),
        user=admin,
    )

    # PT começa em fev/2026 — fora da autorização
    with pytest.raises(ValidationError, match="[Aa]utorização"):
        await validate_adicional_noturno_autorizado(
            db,
            participante_id=p.id,
            trabalho_noturno=True,
            data_inicio_pt=date(2026, 2, 1),
            data_termino_pt=date(2026, 7, 31),
        )


async def test_validate_pt_noturno_autorizacao_indeterminada_ok(db: AsyncSession):
    """Autorização sem data_fim (vigente indeterminada) cobre qualquer PT futuro."""
    from src.services.participante import (
        autorizar_adicional_noturno,
        validate_adicional_noturno_autorizado,
    )

    admin = await persist_user(db, email="not8@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=140008)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1400008", cod_ua=140008)

    await autorizar_adicional_noturno(
        db,
        participante_id=p.id,
        data_inicio_autorizacao=date(2026, 1, 1),
        user=admin,  # sem data_fim
    )

    await validate_adicional_noturno_autorizado(
        db,
        participante_id=p.id,
        trabalho_noturno=True,
        data_inicio_pt=date(2027, 6, 1),
        data_termino_pt=date(2027, 12, 31),
    )


# ---------------------------------------------------------------------------
# Integration — criar_plano_trabalho com flag trabalho_noturno
# ---------------------------------------------------------------------------


async def test_criar_pt_noturno_sem_autorizacao_rejeitado(db: AsyncSession):
    """TC-M10-006 integração — criar_plano_trabalho com trabalho_noturno=True
    sem autorização vigente é rejeitado."""
    admin = await persist_user(db, email="not9@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=140009)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1400009", cod_ua=140009)
    tcr, pe = await _make_pe_pt_base(db, admin, ua, ui, ue, p, 140009, "9")

    with pytest.raises(ValidationError, match="[Aa]utorização"):
        await criar_plano_trabalho(
            db, id_plano_trabalho="PT-NOT-9", origem_unidade=OrigemUnidade.SIAPE,
            cod_unidade_autorizadora=140009, cod_unidade_executora=140020,
            cod_unidade_lotacao_participante=140020, participante_id=p.id,
            cpf_participante=p.cpf, matricula_siape=p.matricula_siape, tcr_id=tcr.id,
            data_inicio=date(2026, 1, 1), data_termino=date(2026, 6, 30),
            carga_horaria_disponivel=1040, criterios_avaliacao="CA",
            plano_entregas_id=pe.id,
            trabalho_noturno=True,
            user=admin,
        )


async def test_criar_pt_noturno_com_autorizacao_ok(db: AsyncSession):
    """TC-M10-005 integração — criar_plano_trabalho com autorização vigente é aceito."""
    from src.services.participante import autorizar_adicional_noturno

    admin = await persist_user(db, email="not10@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup(db, admin, cod_ua=140010)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1400010", cod_ua=140010)
    tcr, pe = await _make_pe_pt_base(db, admin, ua, ui, ue, p, 140010, "10")

    await autorizar_adicional_noturno(
        db,
        participante_id=p.id,
        data_inicio_autorizacao=date(2026, 1, 1),
        data_fim_autorizacao=date(2026, 12, 31),
        user=admin,
    )

    pt = await criar_plano_trabalho(
        db, id_plano_trabalho="PT-NOT-10", origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=140010, cod_unidade_executora=140020,
        cod_unidade_lotacao_participante=140020, participante_id=p.id,
        cpf_participante=p.cpf, matricula_siape=p.matricula_siape, tcr_id=tcr.id,
        data_inicio=date(2026, 1, 1), data_termino=date(2026, 6, 30),
        carga_horaria_disponivel=1040, criterios_avaliacao="CA",
        plano_entregas_id=pe.id,
        trabalho_noturno=True,
        user=admin,
    )
    assert pt.trabalho_noturno is True


# ---------------------------------------------------------------------------
# GraphQL — autorizarAdicionalNoturno mutation
# ---------------------------------------------------------------------------


async def test_gql_autorizar_adicional_noturno(db: AsyncSession, client: AsyncClient):
    """Mutation autorizarAdicionalNoturno cria autorização via GraphQL."""
    admin = await persist_user(db, email="not_gql@t.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)
    ua, ui, ue = await _setup(db, admin, cod_ua=140020)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="1400100", cod_ua=140020)

    mutation = """
    mutation($input: AutorizarAdicionalNoturnoInput!) {
      autorizarAdicionalNoturno(input: $input) {
        id
        participanteId
        dataInicioAutorizacao
        dataFimAutorizacao
        horarioInicioNoturno
        horarioFimNoturno
        justificativa
      }
    }
    """
    variables = {
        "input": {
            "participanteId": str(p.id),
            "dataInicioAutorizacao": "2026-01-01",
            "dataFimAutorizacao": "2026-12-31",
            "horarioInicioNoturno": "22:00:00",
            "horarioFimNoturno": "05:00:00",
            "justificativa": "Plantão",
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
    auth = data["data"]["autorizarAdicionalNoturno"]
    assert auth["participanteId"] == str(p.id)
    assert auth["dataInicioAutorizacao"] == "2026-01-01"
    assert auth["dataFimAutorizacao"] == "2026-12-31"
    assert auth["justificativa"] == "Plantão"
