"""TDD — Workflow de pactuação bilateral do Plano de Trabalho.

Cobre:
- Criação pelo servidor (RASCUNHO_PARTICIPANTE) e pela chefia (RASCUNHO_CHEFIA)
- Servidor edita seu rascunho livremente
- Servidor envia → AGUARDANDO_ASSINATURA_CHEFIA, registra assinatura participante
- Chefia ajusta → assinaturas zeram, volta a RASCUNHO_CHEFIA
- Chefia envia → AGUARDANDO_ASSINATURA_PARTICIPANTE
- Servidor assina → ambas datas preenchidas → EM_EXECUCAO
- Clonar PT antigo cria novo em rascunho com mesmos campos
- Permissões: chefia de outra equipe não consegue editar
"""

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade, UnidadeExecucao
from src.models.participante import RegimeExecucao, TipoVinculo
from src.models.plano import (
    STATUS_PT_AGUARDANDO_ASSINATURA_CHEFIA,
    STATUS_PT_AGUARDANDO_ASSINATURA_PARTICIPANTE,
    STATUS_PT_EM_EXECUCAO,
    STATUS_PT_RASCUNHO_CHEFIA,
    STATUS_PT_RASCUNHO_PARTICIPANTE,
    CriadoPorRole,
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
    pactu_tcr,
)
from src.services.plano_trabalho import (
    adicionar_contribuicao,
    assinar_pt,
    clonar_plano_trabalho,
    criar_plano_trabalho,
    editar_plano_trabalho,
    enviar_pt_para_outro_lado,
)
from tests.conftest import persist_user


async def _add_contrib(db: AsyncSession, pt_id, user, idx="C1"):
    """Helper para adicionar uma contribuição tipo 2 ao PT (sem dependência de PE)."""
    return await adicionar_contribuicao(
        db,
        id_contribuicao=idx,
        plano_trabalho_id=pt_id,
        tipo_contribuicao=2,
        percentual_contribuicao=100,
        descricao="Contribuição padrão",
        user=user,
    )


async def _setup_servidor_e_chefia(db: AsyncSession):
    """Cria infraestrutura mínima + user servidor (linkado a Participante) + user chefia."""
    admin = await persist_user(db, email="adm-pact@t.com", role=UserRole.ADMIN)
    chefe = await persist_user(db, email="chefe-pact@t.com", role=UserRole.CHEFE_IMEDIATO)
    serv_user = await persist_user(db, email="srv-pact@t.com", role=UserRole.SERVIDOR)

    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=1,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="UA Pact",
        sigla="UAP",
        user=admin,
    )
    await criar_ato_autorizacao(
        db,
        unidade_autorizadora_id=ua.id,
        autoridade="Min",
        data_publicacao=date(2024, 1, 1),
        referencia="REF-PACT",
        user=admin,
    )
    await db.refresh(ua)
    ui = await criar_unidade_instituidora(
        db,
        unidade_autorizadora_id=ua.id,
        cod_unidade_instituidora=10,
        nome="UI Pact",
        sigla="UIP",
        ato_instituicao_ref="REF-PACT",
        data_instituicao=date(2024, 1, 10),
        tipos_atividades="T",
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=11,
        nome="UE Pact",
        sigla="UEP",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)

    p = await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ua.cod_unidade_autorizadora,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape="7654321",
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="52998224725",
        nome="Servidor Pact",
        email="srv-pact@t.com",
        modalidade_execucao=1,
        data_assinatura_tcr=date(2024, 3, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
        user=admin,
    )
    tcr = await pactu_tcr(
        db,
        participante_id=p.id,
        chefia_user_id=chefe.id,
        modalidade_execucao=1,
        regime_execucao=RegimeExecucao.INTEGRAL,
        prazo_antecedencia_convocacao_dias=5,
        canais_comunicacao=["email"],
        responsabilidades="R",
        ciencia_instalacoes_ergonomia=True,
        ciencia_nao_direito_adquirido=True,
        ciencia_custeio_estrutura=True,
        user=chefe,
    )
    await assinar_tcr_chefia(db, tcr_id=tcr.id, user=chefe)

    return {
        "admin": admin,
        "chefe": chefe,
        "serv_user": serv_user,
        "ua": ua,
        "ue": ue,
        "p": p,
        "tcr": tcr,
    }


# ---------------------------------------------------------------------------
# Criação
# ---------------------------------------------------------------------------


async def test_servidor_cria_pt_em_rascunho_participante(db: AsyncSession):
    """Servidor cria PT → status RASCUNHO_PARTICIPANTE, criado_por_role=participante."""
    ctx = await _setup_servidor_e_chefia(db)
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-001",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ctx["ua"].cod_unidade_autorizadora,
        cod_unidade_executora=ctx["ue"].cod_unidade_executora,
        cod_unidade_lotacao_participante=ctx["ue"].cod_unidade_executora,
        participante_id=ctx["p"].id,
        cpf_participante=ctx["p"].cpf,
        matricula_siape=ctx["p"].matricula_siape,
        data_inicio=date(2024, 3, 1),
        data_termino=date(2024, 12, 31),
        carga_horaria_disponivel=160,
        criterios_avaliacao="C",
        user=ctx["serv_user"],
    )
    assert pt.status == STATUS_PT_RASCUNHO_PARTICIPANTE
    assert pt.criado_por_role == CriadoPorRole.PARTICIPANTE
    assert pt.data_assinatura_participante is None
    assert pt.data_assinatura_chefia is None


async def test_chefia_cria_pt_em_rascunho_chefia(db: AsyncSession):
    """Chefia cria PT → status RASCUNHO_CHEFIA, criado_por_role=chefia."""
    ctx = await _setup_servidor_e_chefia(db)
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-002",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ctx["ua"].cod_unidade_autorizadora,
        cod_unidade_executora=ctx["ue"].cod_unidade_executora,
        cod_unidade_lotacao_participante=ctx["ue"].cod_unidade_executora,
        participante_id=ctx["p"].id,
        cpf_participante=ctx["p"].cpf,
        matricula_siape=ctx["p"].matricula_siape,
        data_inicio=date(2024, 3, 1),
        data_termino=date(2024, 12, 31),
        carga_horaria_disponivel=160,
        criterios_avaliacao="C",
        user=ctx["chefe"],
    )
    assert pt.status == STATUS_PT_RASCUNHO_CHEFIA
    assert pt.criado_por_role == CriadoPorRole.CHEFIA


# ---------------------------------------------------------------------------
# Edição em rascunho
# ---------------------------------------------------------------------------


async def test_servidor_edita_seu_rascunho(db: AsyncSession):
    """Em RASCUNHO_PARTICIPANTE, servidor edita campos."""
    ctx = await _setup_servidor_e_chefia(db)
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-EDIT",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ctx["ua"].cod_unidade_autorizadora,
        cod_unidade_executora=ctx["ue"].cod_unidade_executora,
        cod_unidade_lotacao_participante=ctx["ue"].cod_unidade_executora,
        participante_id=ctx["p"].id,
        cpf_participante=ctx["p"].cpf,
        matricula_siape=ctx["p"].matricula_siape,
        data_inicio=date(2024, 3, 1),
        data_termino=date(2024, 12, 31),
        carga_horaria_disponivel=160,
        criterios_avaliacao="Original",
        user=ctx["serv_user"],
    )
    pt = await editar_plano_trabalho(
        db,
        plano_id=pt.id,
        user=ctx["serv_user"],
        criterios_avaliacao="Atualizado",
        carga_horaria_disponivel=120,
    )
    assert pt.criterios_avaliacao == "Atualizado"
    assert pt.carga_horaria_disponivel == 120
    assert pt.status == STATUS_PT_RASCUNHO_PARTICIPANTE  # ainda em rascunho


async def test_chefia_nao_pode_editar_rascunho_participante(db: AsyncSession):
    """Chefia tenta editar PT do servidor enquanto está em rascunho do servidor → falha."""
    ctx = await _setup_servidor_e_chefia(db)
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-LOCK",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ctx["ua"].cod_unidade_autorizadora,
        cod_unidade_executora=ctx["ue"].cod_unidade_executora,
        cod_unidade_lotacao_participante=ctx["ue"].cod_unidade_executora,
        participante_id=ctx["p"].id,
        cpf_participante=ctx["p"].cpf,
        matricula_siape=ctx["p"].matricula_siape,
        data_inicio=date(2024, 3, 1),
        data_termino=date(2024, 12, 31),
        carga_horaria_disponivel=160,
        criterios_avaliacao="C",
        user=ctx["serv_user"],
    )
    with pytest.raises(ValidationError, match="(?i)não pode editar|bola"):
        await editar_plano_trabalho(
            db,
            plano_id=pt.id,
            user=ctx["chefe"],
            criterios_avaliacao="Tentativa",
        )


# ---------------------------------------------------------------------------
# Envio para o outro lado
# ---------------------------------------------------------------------------


async def test_servidor_envia_pt_para_chefia(db: AsyncSession):
    """Servidor envia → AGUARDANDO_ASSINATURA_CHEFIA + assinatura participante registrada."""
    ctx = await _setup_servidor_e_chefia(db)
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-ENV",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ctx["ua"].cod_unidade_autorizadora,
        cod_unidade_executora=ctx["ue"].cod_unidade_executora,
        cod_unidade_lotacao_participante=ctx["ue"].cod_unidade_executora,
        participante_id=ctx["p"].id,
        cpf_participante=ctx["p"].cpf,
        matricula_siape=ctx["p"].matricula_siape,
        data_inicio=date(2024, 3, 1),
        data_termino=date(2024, 12, 31),
        carga_horaria_disponivel=160,
        criterios_avaliacao="C",
        user=ctx["serv_user"],
    )
    await _add_contrib(db, pt.id, ctx["serv_user"])
    pt = await enviar_pt_para_outro_lado(db, plano_id=pt.id, user=ctx["serv_user"])
    assert pt.status == STATUS_PT_AGUARDANDO_ASSINATURA_CHEFIA
    assert pt.data_assinatura_participante is not None
    assert pt.data_assinatura_chefia is None


# ---------------------------------------------------------------------------
# Ajuste após envio: zera assinaturas
# ---------------------------------------------------------------------------


async def test_chefia_ajusta_pt_recebido_zera_assinatura_participante(db: AsyncSession):
    """Chefia edita PT em AGUARDANDO_ASSINATURA_CHEFIA → assinatura participante cai, vira RASCUNHO_CHEFIA."""
    ctx = await _setup_servidor_e_chefia(db)
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-ADJ",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ctx["ua"].cod_unidade_autorizadora,
        cod_unidade_executora=ctx["ue"].cod_unidade_executora,
        cod_unidade_lotacao_participante=ctx["ue"].cod_unidade_executora,
        participante_id=ctx["p"].id,
        cpf_participante=ctx["p"].cpf,
        matricula_siape=ctx["p"].matricula_siape,
        data_inicio=date(2024, 3, 1),
        data_termino=date(2024, 12, 31),
        carga_horaria_disponivel=160,
        criterios_avaliacao="C",
        user=ctx["serv_user"],
    )
    await _add_contrib(db, pt.id, ctx["serv_user"])
    pt = await enviar_pt_para_outro_lado(db, plano_id=pt.id, user=ctx["serv_user"])
    assert pt.data_assinatura_participante is not None

    pt = await editar_plano_trabalho(
        db,
        plano_id=pt.id,
        user=ctx["chefe"],
        criterios_avaliacao="Chefia ajustou",
    )
    assert pt.status == STATUS_PT_RASCUNHO_CHEFIA
    assert pt.data_assinatura_participante is None  # zerou
    assert pt.criterios_avaliacao == "Chefia ajustou"


# ---------------------------------------------------------------------------
# Pactuação completa: ambas as assinaturas → EM_EXECUCAO
# ---------------------------------------------------------------------------


async def test_dupla_assinatura_vira_em_execucao(db: AsyncSession):
    """Servidor envia → chefia assina → status EM_EXECUCAO, ambas datas preenchidas."""
    ctx = await _setup_servidor_e_chefia(db)
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-EXEC",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ctx["ua"].cod_unidade_autorizadora,
        cod_unidade_executora=ctx["ue"].cod_unidade_executora,
        cod_unidade_lotacao_participante=ctx["ue"].cod_unidade_executora,
        participante_id=ctx["p"].id,
        cpf_participante=ctx["p"].cpf,
        matricula_siape=ctx["p"].matricula_siape,
        data_inicio=date(2024, 3, 1),
        data_termino=date(2024, 12, 31),
        carga_horaria_disponivel=160,
        criterios_avaliacao="C",
        user=ctx["serv_user"],
    )
    await _add_contrib(db, pt.id, ctx["serv_user"])
    await enviar_pt_para_outro_lado(db, plano_id=pt.id, user=ctx["serv_user"])
    pt = await assinar_pt(db, plano_id=pt.id, user=ctx["chefe"])
    assert pt.status == STATUS_PT_EM_EXECUCAO
    assert pt.data_assinatura_participante is not None
    assert pt.data_assinatura_chefia is not None


async def test_chefia_cria_envia_servidor_assina_vira_em_execucao(db: AsyncSession):
    """Caso exceção: chefia inicia → envia → servidor assina → EM_EXECUCAO."""
    ctx = await _setup_servidor_e_chefia(db)
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-CHEF",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ctx["ua"].cod_unidade_autorizadora,
        cod_unidade_executora=ctx["ue"].cod_unidade_executora,
        cod_unidade_lotacao_participante=ctx["ue"].cod_unidade_executora,
        participante_id=ctx["p"].id,
        cpf_participante=ctx["p"].cpf,
        matricula_siape=ctx["p"].matricula_siape,
        data_inicio=date(2024, 3, 1),
        data_termino=date(2024, 12, 31),
        carga_horaria_disponivel=160,
        criterios_avaliacao="C",
        user=ctx["chefe"],
    )
    assert pt.status == STATUS_PT_RASCUNHO_CHEFIA
    await _add_contrib(db, pt.id, ctx["chefe"])
    pt = await enviar_pt_para_outro_lado(db, plano_id=pt.id, user=ctx["chefe"])
    assert pt.status == STATUS_PT_AGUARDANDO_ASSINATURA_PARTICIPANTE
    assert pt.data_assinatura_chefia is not None
    pt = await assinar_pt(db, plano_id=pt.id, user=ctx["serv_user"])
    assert pt.status == STATUS_PT_EM_EXECUCAO


# ---------------------------------------------------------------------------
# Não pode editar PT em EM_EXECUCAO
# ---------------------------------------------------------------------------


async def test_nao_pode_editar_pt_em_execucao(db: AsyncSession):
    ctx = await _setup_servidor_e_chefia(db)
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-RO",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ctx["ua"].cod_unidade_autorizadora,
        cod_unidade_executora=ctx["ue"].cod_unidade_executora,
        cod_unidade_lotacao_participante=ctx["ue"].cod_unidade_executora,
        participante_id=ctx["p"].id,
        cpf_participante=ctx["p"].cpf,
        matricula_siape=ctx["p"].matricula_siape,
        data_inicio=date(2024, 3, 1),
        data_termino=date(2024, 12, 31),
        carga_horaria_disponivel=160,
        criterios_avaliacao="C",
        user=ctx["serv_user"],
    )
    await _add_contrib(db, pt.id, ctx["serv_user"])
    await enviar_pt_para_outro_lado(db, plano_id=pt.id, user=ctx["serv_user"])
    await assinar_pt(db, plano_id=pt.id, user=ctx["chefe"])
    with pytest.raises(ValidationError, match="(?i)em execução|não pode"):
        await editar_plano_trabalho(
            db,
            plano_id=pt.id,
            user=ctx["serv_user"],
            criterios_avaliacao="X",
        )


# ---------------------------------------------------------------------------
# Clonagem
# ---------------------------------------------------------------------------


async def test_clonar_pt_copia_campos_e_cria_rascunho(db: AsyncSession):
    """Clonar PT antigo → novo PT em RASCUNHO_X com mesmos critérios/contribuições."""
    ctx = await _setup_servidor_e_chefia(db)
    pt_origem = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-ORIG",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=ctx["ua"].cod_unidade_autorizadora,
        cod_unidade_executora=ctx["ue"].cod_unidade_executora,
        cod_unidade_lotacao_participante=ctx["ue"].cod_unidade_executora,
        participante_id=ctx["p"].id,
        cpf_participante=ctx["p"].cpf,
        matricula_siape=ctx["p"].matricula_siape,
        data_inicio=date(2024, 3, 1),
        data_termino=date(2024, 8, 31),
        carga_horaria_disponivel=160,
        criterios_avaliacao="Critérios A B C",
        user=ctx["serv_user"],
    )
    pt_novo = await clonar_plano_trabalho(
        db,
        pt_origem_id=pt_origem.id,
        id_plano_trabalho_novo="PT-CLONE",
        nova_data_inicio=date(2024, 9, 1),
        nova_data_termino=date(2025, 2, 28),
        user=ctx["serv_user"],
    )
    assert pt_novo.id != pt_origem.id
    assert pt_novo.clonado_de_id == pt_origem.id
    assert pt_novo.criterios_avaliacao == "Critérios A B C"
    assert pt_novo.status == STATUS_PT_RASCUNHO_PARTICIPANTE
    assert pt_novo.data_assinatura_participante is None
    assert pt_novo.data_assinatura_chefia is None
