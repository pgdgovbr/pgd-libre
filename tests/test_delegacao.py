"""Sprint 2.8 — RF-037: Delegação de Competência.

A UnidadeAutorizadora pode delegar competências (ex.: aprovar planos de entregas,
realizar seleção, avaliar registros) para uma chefia específica. A delegação
pode ser restrita a uma UnidadeExecucao e tem janela de vigência.

JU-08 (em tests/test_jornadas.py): jornada E2E onde admin delega
APROVAR_PLANO_ENTREGAS para chefia, que então aprova um PE.
"""
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade, UnidadeExecucao
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
)
from src.models.plano import TipoMeta

from .conftest import persist_user, set_auth_cookie


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup(db: AsyncSession, admin, cod_ua: int = 150001):
    ua = await criar_unidade_autorizadora(
        db, cod_unidade_autorizadora=cod_ua, origem_unidade=OrigemUnidade.SIAPE,
        nome="UA DEL", sigla="UDL", user=admin,
    )
    await criar_ato_autorizacao(
        db, unidade_autorizadora_id=ua.id, autoridade="Min.",
        data_publicacao=date(2024, 1, 1), referencia="DEL", user=admin,
    )
    await db.refresh(ua)
    ui = await criar_unidade_instituidora(
        db, unidade_autorizadora_id=ua.id, cod_unidade_instituidora=150010,
        nome="UI DEL", sigla="UIL", ato_instituicao_ref="DEL",
        data_instituicao=date(2024, 1, 1), tipos_atividades="T",
        conteudo_minimo_tcr="C", prazo_antecedencia_convocacao_dias=5, user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id, cod_unidade_executora=150020,
        nome="UE DEL", sigla="UEL",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)
    return ua, ui, ue


async def _make_pe(db, admin, ua, ui, ue, cod_ua, suffix):
    pe = await criar_plano_entregas(
        db, id_plano_entregas=f"PE-DEL-{suffix}", origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=cod_ua, cod_unidade_instituidora=150010,
        cod_unidade_executora=150020, unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1), data_termino=date(2026, 12, 31), user=admin,
    )
    await criar_entrega(
        db, id_entrega=f"E-DEL-{suffix}", plano_entregas_id=pe.id, nome_entrega="E",
        meta_entrega=1, tipo_meta=TipoMeta.UNIDADE, data_entrega=date(2026, 12, 31),
        nome_unidade_demandante="D", nome_unidade_destinataria="D", user=admin,
    )
    return pe


# ---------------------------------------------------------------------------
# Service — delegar_competencia
# ---------------------------------------------------------------------------


async def test_delegar_competencia_aprovar_pe_ok(db: AsyncSession):
    """RF-037 — admin delega APROVAR_PLANO_ENTREGAS para chefia."""
    from src.models.institucional import Competencia
    from src.services.institucional import delegar_competencia

    admin = await persist_user(db, email="del1_a@t.com", role=UserRole.ADMIN)
    chefia = await persist_user(db, email="del1_c@t.com", role=UserRole.CHEFE_IMEDIATO)
    ua, ui, ue = await _setup(db, admin, cod_ua=150001)

    d = await delegar_competencia(
        db,
        delegante_user_id=admin.id,
        delegatario_user_id=chefia.id,
        competencia=Competencia.APROVAR_PLANO_ENTREGAS,
        unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1),
        data_fim=date(2026, 12, 31),
        motivo="Substituição do gestor durante férias",
        user=admin,
    )
    assert d.delegante_user_id == admin.id
    assert d.delegatario_user_id == chefia.id
    assert d.competencia == Competencia.APROVAR_PLANO_ENTREGAS
    assert d.unidade_execucao_id == ue.id
    assert d.ativo is True


async def test_delegar_competencia_escopo_global_ok(db: AsyncSession):
    """Delegação sem unidade_execucao_id é global (vale para qualquer UE)."""
    from src.models.institucional import Competencia
    from src.services.institucional import delegar_competencia

    admin = await persist_user(db, email="del2_a@t.com", role=UserRole.ADMIN)
    chefia = await persist_user(db, email="del2_c@t.com", role=UserRole.CHEFE_IMEDIATO)
    ua, ui, ue = await _setup(db, admin, cod_ua=150002)

    d = await delegar_competencia(
        db,
        delegante_user_id=admin.id,
        delegatario_user_id=chefia.id,
        competencia=Competencia.REALIZAR_SELECAO,
        data_inicio=date(2026, 1, 1),
        user=admin,
    )
    assert d.unidade_execucao_id is None
    assert d.data_fim is None


async def test_delegar_competencia_data_fim_anterior_inicio_rejeitada(db: AsyncSession):
    from src.models.institucional import Competencia
    from src.services.institucional import delegar_competencia

    admin = await persist_user(db, email="del3_a@t.com", role=UserRole.ADMIN)
    chefia = await persist_user(db, email="del3_c@t.com", role=UserRole.CHEFE_IMEDIATO)

    with pytest.raises(ValidationError, match="[Dd]ata"):
        await delegar_competencia(
            db,
            delegante_user_id=admin.id,
            delegatario_user_id=chefia.id,
            competencia=Competencia.APROVAR_PLANO_ENTREGAS,
            data_inicio=date(2026, 6, 1),
            data_fim=date(2026, 5, 1),
            user=admin,
        )


async def test_revogar_delegacao_marca_inativo(db: AsyncSession):
    from src.models.institucional import Competencia
    from src.services.institucional import delegar_competencia, revogar_delegacao

    admin = await persist_user(db, email="del4_a@t.com", role=UserRole.ADMIN)
    chefia = await persist_user(db, email="del4_c@t.com", role=UserRole.CHEFE_IMEDIATO)

    d = await delegar_competencia(
        db,
        delegante_user_id=admin.id,
        delegatario_user_id=chefia.id,
        competencia=Competencia.AVALIAR_REGISTROS,
        data_inicio=date(2026, 1, 1),
        user=admin,
    )
    d2 = await revogar_delegacao(db, delegacao_id=d.id, user=admin)
    assert d2.ativo is False


# ---------------------------------------------------------------------------
# has_delegated_permission helper
# ---------------------------------------------------------------------------


async def test_has_delegated_permission_sem_registro_retorna_false(db: AsyncSession):
    from src.models.institucional import Competencia
    from src.services.institucional import has_delegated_permission

    admin = await persist_user(db, email="del5_a@t.com", role=UserRole.ADMIN)
    chefia = await persist_user(db, email="del5_c@t.com", role=UserRole.CHEFE_IMEDIATO)
    ua, ui, ue = await _setup(db, admin, cod_ua=150005)

    ok = await has_delegated_permission(
        db,
        user_id=chefia.id,
        competencia=Competencia.APROVAR_PLANO_ENTREGAS,
        unidade_execucao_id=ue.id,
        referencia=date(2026, 3, 1),
    )
    assert ok is False


async def test_has_delegated_permission_com_delegacao_ativa(db: AsyncSession):
    from src.models.institucional import Competencia
    from src.services.institucional import delegar_competencia, has_delegated_permission

    admin = await persist_user(db, email="del6_a@t.com", role=UserRole.ADMIN)
    chefia = await persist_user(db, email="del6_c@t.com", role=UserRole.CHEFE_IMEDIATO)
    ua, ui, ue = await _setup(db, admin, cod_ua=150006)

    await delegar_competencia(
        db,
        delegante_user_id=admin.id,
        delegatario_user_id=chefia.id,
        competencia=Competencia.APROVAR_PLANO_ENTREGAS,
        unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1),
        data_fim=date(2026, 12, 31),
        user=admin,
    )
    ok = await has_delegated_permission(
        db,
        user_id=chefia.id,
        competencia=Competencia.APROVAR_PLANO_ENTREGAS,
        unidade_execucao_id=ue.id,
        referencia=date(2026, 3, 1),
    )
    assert ok is True


async def test_has_delegated_permission_revogada_retorna_false(db: AsyncSession):
    from src.models.institucional import Competencia
    from src.services.institucional import (
        delegar_competencia,
        has_delegated_permission,
        revogar_delegacao,
    )

    admin = await persist_user(db, email="del7_a@t.com", role=UserRole.ADMIN)
    chefia = await persist_user(db, email="del7_c@t.com", role=UserRole.CHEFE_IMEDIATO)
    ua, ui, ue = await _setup(db, admin, cod_ua=150007)

    d = await delegar_competencia(
        db,
        delegante_user_id=admin.id,
        delegatario_user_id=chefia.id,
        competencia=Competencia.APROVAR_PLANO_ENTREGAS,
        unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1),
        user=admin,
    )
    await revogar_delegacao(db, delegacao_id=d.id, user=admin)
    ok = await has_delegated_permission(
        db,
        user_id=chefia.id,
        competencia=Competencia.APROVAR_PLANO_ENTREGAS,
        unidade_execucao_id=ue.id,
        referencia=date(2026, 3, 1),
    )
    assert ok is False


async def test_has_delegated_permission_fora_periodo_retorna_false(db: AsyncSession):
    from src.models.institucional import Competencia
    from src.services.institucional import delegar_competencia, has_delegated_permission

    admin = await persist_user(db, email="del8_a@t.com", role=UserRole.ADMIN)
    chefia = await persist_user(db, email="del8_c@t.com", role=UserRole.CHEFE_IMEDIATO)
    ua, ui, ue = await _setup(db, admin, cod_ua=150008)

    await delegar_competencia(
        db,
        delegante_user_id=admin.id,
        delegatario_user_id=chefia.id,
        competencia=Competencia.APROVAR_PLANO_ENTREGAS,
        unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1),
        data_fim=date(2026, 1, 31),
        user=admin,
    )
    ok = await has_delegated_permission(
        db,
        user_id=chefia.id,
        competencia=Competencia.APROVAR_PLANO_ENTREGAS,
        unidade_execucao_id=ue.id,
        referencia=date(2026, 3, 1),
    )
    assert ok is False


async def test_has_delegated_permission_escopo_global_vale_para_qualquer_ue(db: AsyncSession):
    """Delegação sem unidade_execucao_id (global) vale para qualquer UE consultada."""
    from src.models.institucional import Competencia
    from src.services.institucional import delegar_competencia, has_delegated_permission

    admin = await persist_user(db, email="del9_a@t.com", role=UserRole.ADMIN)
    chefia = await persist_user(db, email="del9_c@t.com", role=UserRole.CHEFE_IMEDIATO)
    ua, ui, ue = await _setup(db, admin, cod_ua=150009)

    await delegar_competencia(
        db,
        delegante_user_id=admin.id,
        delegatario_user_id=chefia.id,
        competencia=Competencia.APROVAR_PLANO_ENTREGAS,
        data_inicio=date(2026, 1, 1),
        user=admin,  # delegação global, sem unidade_execucao_id
    )
    ok = await has_delegated_permission(
        db,
        user_id=chefia.id,
        competencia=Competencia.APROVAR_PLANO_ENTREGAS,
        unidade_execucao_id=ue.id,
        referencia=date(2026, 3, 1),
    )
    assert ok is True


async def test_has_delegated_permission_escopo_ue_nao_vale_em_outra(db: AsyncSession):
    """Delegação restrita à UE-A não autoriza ações em UE-B."""
    from src.models.institucional import Competencia
    from src.services.institucional import delegar_competencia, has_delegated_permission

    admin = await persist_user(db, email="del10_a@t.com", role=UserRole.ADMIN)
    chefia = await persist_user(db, email="del10_c@t.com", role=UserRole.CHEFE_IMEDIATO)
    ua, ui, ue = await _setup(db, admin, cod_ua=150010)

    # outra UE no mesmo UI
    ue_outra = UnidadeExecucao(
        unidade_instituidora_id=ui.id, cod_unidade_executora=150021,
        nome="UE OUTRA", sigla="UEO",
    )
    db.add(ue_outra)
    await db.commit()
    await db.refresh(ue_outra)

    await delegar_competencia(
        db,
        delegante_user_id=admin.id,
        delegatario_user_id=chefia.id,
        competencia=Competencia.APROVAR_PLANO_ENTREGAS,
        unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1),
        user=admin,
    )
    # Tentar usar na outra UE → não autorizado
    ok = await has_delegated_permission(
        db,
        user_id=chefia.id,
        competencia=Competencia.APROVAR_PLANO_ENTREGAS,
        unidade_execucao_id=ue_outra.id,
        referencia=date(2026, 3, 1),
    )
    assert ok is False


# ---------------------------------------------------------------------------
# Integration — aprovar_plano_entregas com authz por delegação
# ---------------------------------------------------------------------------


async def test_aprovar_pe_chefia_sem_delegacao_rejeitado(db: AsyncSession):
    """Chefe imediato sem delegação ativa não pode aprovar PE."""
    admin = await persist_user(db, email="del11_a@t.com", role=UserRole.ADMIN)
    chefia = await persist_user(db, email="del11_c@t.com", role=UserRole.CHEFE_IMEDIATO)
    ua, ui, ue = await _setup(db, admin, cod_ua=150011)
    pe = await _make_pe(db, admin, ua, ui, ue, 150011, "11")

    with pytest.raises(ValidationError, match="[Dd]elegação|[Pp]ermissão"):
        await aprovar_plano_entregas(
            db,
            plano_id=pe.id,
            aprovador_user_id=chefia.id,
            user=chefia,
        )


async def test_aprovar_pe_chefia_com_delegacao_ok(db: AsyncSession):
    """JU-08 service-level — chefia com delegação ativa aprova PE com sucesso."""
    from src.models.institucional import Competencia
    from src.services.institucional import delegar_competencia

    admin = await persist_user(db, email="del12_a@t.com", role=UserRole.ADMIN)
    chefia = await persist_user(db, email="del12_c@t.com", role=UserRole.CHEFE_IMEDIATO)
    ua, ui, ue = await _setup(db, admin, cod_ua=150012)
    pe = await _make_pe(db, admin, ua, ui, ue, 150012, "12")

    await delegar_competencia(
        db,
        delegante_user_id=admin.id,
        delegatario_user_id=chefia.id,
        competencia=Competencia.APROVAR_PLANO_ENTREGAS,
        unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1),
        data_fim=date(2026, 12, 31),
        user=admin,
    )
    pe2 = await aprovar_plano_entregas(
        db, plano_id=pe.id, aprovador_user_id=chefia.id, user=chefia,
    )
    assert pe2.aprovado_por_user_id == chefia.id
    assert pe2.data_aprovacao is not None


async def test_aprovar_pe_gestor_sem_delegacao_ok(db: AsyncSession):
    """Gestor mantém autorização default (regressão — RBAC não regrediu)."""
    admin = await persist_user(db, email="del13_a@t.com", role=UserRole.ADMIN)
    gestor = await persist_user(db, email="del13_g@t.com", role=UserRole.GESTOR_UNIDADE)
    ua, ui, ue = await _setup(db, admin, cod_ua=150013)
    pe = await _make_pe(db, admin, ua, ui, ue, 150013, "13")

    pe2 = await aprovar_plano_entregas(
        db, plano_id=pe.id, aprovador_user_id=gestor.id, user=gestor,
    )
    assert pe2.aprovado_por_user_id == gestor.id


# ---------------------------------------------------------------------------
# GraphQL — delegarCompetencia mutation
# ---------------------------------------------------------------------------


async def test_gql_delegar_competencia(db: AsyncSession, client: AsyncClient):
    admin = await persist_user(db, email="del_gql_a@t.com", role=UserRole.ADMIN)
    chefia = await persist_user(db, email="del_gql_c@t.com", role=UserRole.CHEFE_IMEDIATO)
    set_auth_cookie(client, admin)
    ua, ui, ue = await _setup(db, admin, cod_ua=150020)

    mutation = """
    mutation($input: DelegarCompetenciaInput!) {
      delegarCompetencia(input: $input) {
        id
        delegatarioUserId
        competencia
        unidadeExecucaoId
        dataInicio
        dataFim
        ativo
      }
    }
    """
    variables = {
        "input": {
            "delegatarioUserId": chefia.id,
            "competencia": "APROVAR_PLANO_ENTREGAS",
            "unidadeExecucaoId": str(ue.id),
            "dataInicio": "2026-01-01",
            "dataFim": "2026-12-31",
            "motivo": "Férias do gestor",
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
    d = data["data"]["delegarCompetencia"]
    assert d["delegatarioUserId"] == chefia.id
    assert d["competencia"] == "APROVAR_PLANO_ENTREGAS"
    assert d["ativo"] is True


async def test_gql_revogar_delegacao(db: AsyncSession, client: AsyncClient):
    from src.models.institucional import Competencia
    from src.services.institucional import delegar_competencia

    admin = await persist_user(db, email="del_rev_a@t.com", role=UserRole.ADMIN)
    chefia = await persist_user(db, email="del_rev_c@t.com", role=UserRole.CHEFE_IMEDIATO)
    set_auth_cookie(client, admin)

    d = await delegar_competencia(
        db,
        delegante_user_id=admin.id,
        delegatario_user_id=chefia.id,
        competencia=Competencia.AVALIAR_REGISTROS,
        data_inicio=date(2026, 1, 1),
        user=admin,
    )

    mutation = f"""
    mutation {{
      revogarDelegacao(delegacaoId: "{d.id}") {{
        id
        ativo
      }}
    }}
    """
    resp = await client.post(
        "/graphql",
        json={"query": mutation},
        headers={"user-agent": "pytest"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("errors") is None, data.get("errors")
    assert data["data"]["revogarDelegacao"]["ativo"] is False
