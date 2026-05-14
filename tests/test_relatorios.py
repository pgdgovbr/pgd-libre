"""RF-028 — Relatórios de Conformidade (TC-M07-005 a TC-M07-009)."""

from datetime import UTC, date

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade, UnidadeExecucao
from src.models.participante import RegimeExecucao, TipoVinculo
from src.models.plano import (
    STATUS_PE_CONCLUIDO,
    AvaliacaoRegistrosExecucao,
    TipoMeta,
)
from src.models.user import UserRole
from src.services.institucional import (
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
from src.services.relatorios import (
    relatorio_avaliacoes_pendentes,
    relatorio_nao_enviados,
    relatorio_pe_avaliacao_pendente,
    relatorio_registros_atraso,
    relatorio_sem_plano_trabalho,
)

from .conftest import persist_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _setup_base(db: AsyncSession, admin, cod_ua: int = 90001):
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=cod_ua,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="UA Rel",
        sigla="UAR",
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
        cod_unidade_instituidora=90010,
        nome="UI Rel",
        sigla="UIR",
        ato_instituicao_ref="P1",
        data_instituicao=date(2024, 1, 1),
        tipos_atividades="T",
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=90020,
        nome="UE Rel",
        sigla="UER",
    )
    db.add(ue)
    await db.commit()
    await db.refresh(ue)
    return ua, ui, ue


async def _make_participante(db, admin, ue, ua, ui, matricula="9000001", cod_ua=90001):
    return await cadastrar_participante(
        db,
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=cod_ua,
        cod_unidade_lotacao=ue.cod_unidade_executora,
        matricula_siape=matricula,
        cod_unidade_instituidora=ui.cod_unidade_instituidora,
        cpf="11144477735",
        nome="Part Rel",
        email=f"{matricula}@t.com",
        modalidade_execucao=1,
        data_assinatura_tcr=date(2024, 3, 1),
        tipo_vinculo=TipoVinculo.EFETIVO,
        unidade_execucao_id=ue.id,
        user=admin,
    )


# ---------------------------------------------------------------------------
# TC-M07-005 — Participantes sem plano de trabalho ativo [I]
# ---------------------------------------------------------------------------


async def test_relatorio_sem_plano_trabalho(db: AsyncSession):
    """TC-M07-005."""
    admin = await persist_user(db, email="rel005@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup_base(db, admin)
    p = await _make_participante(db, admin, ue, ua, ui)

    resultado = await relatorio_sem_plano_trabalho(db)
    ids = [r.id for r in resultado]
    assert p.id in ids


async def test_relatorio_sem_plano_trabalho_exclui_com_plano_ativo(db: AsyncSession):
    """TC-M07-005 variante — participante com plano ativo não aparece."""
    admin = await persist_user(db, email="rel005b@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup_base(db, admin, cod_ua=90002)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="9000002", cod_ua=90002)

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

    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-R2",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=90002,
        cod_unidade_instituidora=90010,
        cod_unidade_executora=90020,
        unidade_execucao_id=ue.id,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        user=admin,
    )
    await criar_entrega(
        db,
        id_entrega="E-R2",
        plano_entregas_id=pe.id,
        nome_entrega="E",
        meta_entrega=1,
        tipo_meta=TipoMeta.UNIDADE,
        data_entrega=date(2026, 12, 31),
        nome_unidade_demandante="D",
        nome_unidade_destinataria="D",
        user=admin,
    )
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-R2",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=90002,
        cod_unidade_executora=90020,
        cod_unidade_lotacao_participante=90020,
        participante_id=p.id,
        cpf_participante=p.cpf,
        matricula_siape=p.matricula_siape,
        tcr_id=tcr.id,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        carga_horaria_disponivel=2000,
        criterios_avaliacao="CA",
        plano_entregas_id=pe.id,
        user=admin,
    )
    await adicionar_contribuicao(
        db,
        plano_trabalho_id=pt.id,
        id_contribuicao="C1",
        tipo_contribuicao=2,
        percentual_contribuicao=100,
        descricao="C",
        user=admin,
    )
    await iniciar_execucao_pt(db, plano_id=pt.id, user=admin)

    resultado = await relatorio_sem_plano_trabalho(db, cod_unidade_autorizadora=90002)
    ids = [r.id for r in resultado]
    assert p.id not in ids


# ---------------------------------------------------------------------------
# TC-M07-006 — Planos com registro de execução em atraso [I]
# ---------------------------------------------------------------------------


async def test_relatorio_registros_atraso(db: AsyncSession):
    """TC-M07-006."""
    admin = await persist_user(db, email="rel006@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup_base(db, admin, cod_ua=90003)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="9000003", cod_ua=90003)

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

    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-R3",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=90003,
        cod_unidade_instituidora=90010,
        cod_unidade_executora=90020,
        unidade_execucao_id=ue.id,
        data_inicio=date(2025, 1, 1),
        data_termino=date(2025, 12, 31),
        user=admin,
    )
    await criar_entrega(
        db,
        id_entrega="E-R3",
        plano_entregas_id=pe.id,
        nome_entrega="E",
        meta_entrega=1,
        tipo_meta=TipoMeta.UNIDADE,
        data_entrega=date(2025, 12, 31),
        nome_unidade_demandante="D",
        nome_unidade_destinataria="D",
        user=admin,
    )
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-R3",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=90003,
        cod_unidade_executora=90020,
        cod_unidade_lotacao_participante=90020,
        participante_id=p.id,
        cpf_participante=p.cpf,
        matricula_siape=p.matricula_siape,
        tcr_id=tcr.id,
        data_inicio=date(2025, 1, 1),
        data_termino=date(2025, 12, 31),
        carga_horaria_disponivel=2000,
        criterios_avaliacao="CA",
        plano_entregas_id=pe.id,
        user=admin,
    )
    await adicionar_contribuicao(
        db,
        plano_trabalho_id=pt.id,
        id_contribuicao="C1",
        tipo_contribuicao=2,
        percentual_contribuicao=100,
        descricao="C",
        user=admin,
    )
    await iniciar_execucao_pt(db, plano_id=pt.id, user=admin)

    # Período com data_fim no passado, sem registro
    avaliacao = AvaliacaoRegistrosExecucao(
        id_periodo_avaliativo="PA-R3",
        plano_trabalho_id=pt.id,
        data_inicio_periodo_avaliativo=date(2025, 1, 1),
        data_fim_periodo_avaliativo=date(2025, 1, 31),
        # data_registro_participante = None (em atraso)
    )
    db.add(avaliacao)
    await db.commit()

    # referência = hoje; prazo vencido = data_fim + 10 < referencia
    referencia = date(2026, 3, 1)
    resultado = await relatorio_registros_atraso(
        db, referencia=referencia, cod_unidade_autorizadora=90003
    )
    assert len(resultado) >= 1
    assert any(r.id == avaliacao.id for r in resultado)


# ---------------------------------------------------------------------------
# TC-M07-007 — Avaliações pendentes da chefia [I]
# ---------------------------------------------------------------------------


async def test_relatorio_avaliacoes_pendentes(db: AsyncSession):
    """TC-M07-007."""
    admin = await persist_user(db, email="rel007@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup_base(db, admin, cod_ua=90004)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="9000004", cod_ua=90004)

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

    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-R4",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=90004,
        cod_unidade_instituidora=90010,
        cod_unidade_executora=90020,
        unidade_execucao_id=ue.id,
        data_inicio=date(2025, 1, 1),
        data_termino=date(2025, 12, 31),
        user=admin,
    )
    await criar_entrega(
        db,
        id_entrega="E-R4",
        plano_entregas_id=pe.id,
        nome_entrega="E",
        meta_entrega=1,
        tipo_meta=TipoMeta.UNIDADE,
        data_entrega=date(2025, 12, 31),
        nome_unidade_demandante="D",
        nome_unidade_destinataria="D",
        user=admin,
    )
    pt = await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-R4",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=90004,
        cod_unidade_executora=90020,
        cod_unidade_lotacao_participante=90020,
        participante_id=p.id,
        cpf_participante=p.cpf,
        matricula_siape=p.matricula_siape,
        tcr_id=tcr.id,
        data_inicio=date(2025, 1, 1),
        data_termino=date(2025, 12, 31),
        carga_horaria_disponivel=2000,
        criterios_avaliacao="CA",
        plano_entregas_id=pe.id,
        user=admin,
    )
    await adicionar_contribuicao(
        db,
        plano_trabalho_id=pt.id,
        id_contribuicao="C1",
        tipo_contribuicao=2,
        percentual_contribuicao=100,
        descricao="C",
        user=admin,
    )
    await iniciar_execucao_pt(db, plano_id=pt.id, user=admin)

    from datetime import datetime

    avaliacao = AvaliacaoRegistrosExecucao(
        id_periodo_avaliativo="PA-R4",
        plano_trabalho_id=pt.id,
        data_inicio_periodo_avaliativo=date(2025, 1, 1),
        data_fim_periodo_avaliativo=date(2025, 1, 31),
        data_registro_participante=datetime(2025, 2, 5, tzinfo=UTC),
        # avaliacao_registros_execucao = None (pendente)
    )
    db.add(avaliacao)
    await db.commit()

    referencia = date(2026, 3, 1)
    resultado = await relatorio_avaliacoes_pendentes(
        db, referencia=referencia, cod_unidade_autorizadora=90004
    )
    assert len(resultado) >= 1
    assert any(r.id == avaliacao.id for r in resultado)


# ---------------------------------------------------------------------------
# TC-M07-008 — Registros não enviados à API PGD Central [I]
# ---------------------------------------------------------------------------


async def test_relatorio_nao_enviados(db: AsyncSession):
    """TC-M07-008 — participante com api_sincronizado_em=null aparece no relatório."""
    admin = await persist_user(db, email="rel008@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup_base(db, admin, cod_ua=90005)
    p = await _make_participante(db, admin, ue, ua, ui, matricula="9000005", cod_ua=90005)

    resultado = await relatorio_nao_enviados(db, cod_unidade_autorizadora=90005)
    ids = [r.id for r in resultado["participantes"]]
    assert p.id in ids


# ---------------------------------------------------------------------------
# TC-M07-009 — Planos de entregas com avaliação pendente [I]
# ---------------------------------------------------------------------------


async def test_relatorio_pe_avaliacao_pendente(db: AsyncSession):
    """TC-M07-009 — PE concluído há mais de 30 dias sem avaliação aparece no relatório."""
    admin = await persist_user(db, email="rel009@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup_base(db, admin, cod_ua=90006)

    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-R9",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=90006,
        cod_unidade_instituidora=90010,
        cod_unidade_executora=90020,
        unidade_execucao_id=ue.id,
        data_inicio=date(2025, 1, 1),
        data_termino=date(2025, 6, 30),
        user=admin,
    )
    await criar_entrega(
        db,
        id_entrega="E-R9",
        plano_entregas_id=pe.id,
        nome_entrega="E",
        meta_entrega=1,
        tipo_meta=TipoMeta.UNIDADE,
        data_entrega=date(2025, 6, 30),
        nome_unidade_demandante="D",
        nome_unidade_destinataria="D",
        user=admin,
    )
    # Forçar status CONCLUIDO diretamente (sem avaliação)
    pe.status = STATUS_PE_CONCLUIDO
    await db.commit()
    await db.refresh(pe)

    referencia = date(2026, 3, 1)
    resultado = await relatorio_pe_avaliacao_pendente(
        db, referencia=referencia, cod_unidade_autorizadora=90006
    )
    assert len(resultado) >= 1
    assert any(r.id == pe.id for r in resultado)


async def test_relatorio_pe_avaliacao_pendente_exclui_avaliado(db: AsyncSession):
    """TC-M07-009 variante — PE já avaliado não aparece."""
    admin = await persist_user(db, email="rel009b@t.com", role=UserRole.ADMIN)
    ua, ui, ue = await _setup_base(db, admin, cod_ua=90007)

    pe = await criar_plano_entregas(
        db,
        id_plano_entregas="PE-R9B",
        origem_unidade=OrigemUnidade.SIAPE,
        cod_unidade_autorizadora=90007,
        cod_unidade_instituidora=90010,
        cod_unidade_executora=90020,
        unidade_execucao_id=ue.id,
        data_inicio=date(2025, 1, 1),
        data_termino=date(2025, 6, 30),
        user=admin,
    )
    await criar_entrega(
        db,
        id_entrega="E-R9B",
        plano_entregas_id=pe.id,
        nome_entrega="E",
        meta_entrega=1,
        tipo_meta=TipoMeta.UNIDADE,
        data_entrega=date(2025, 6, 30),
        nome_unidade_demandante="D",
        nome_unidade_destinataria="D",
        user=admin,
    )
    pe.status = STATUS_PE_CONCLUIDO
    pe.avaliacao = 3
    await db.commit()

    referencia = date(2026, 3, 1)
    resultado = await relatorio_pe_avaliacao_pendente(
        db, referencia=referencia, cod_unidade_autorizadora=90007
    )
    ids = [r.id for r in resultado]
    assert pe.id not in ids
