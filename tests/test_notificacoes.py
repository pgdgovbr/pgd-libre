"""Sprint 1.6 — Notificações: testes de criação e envio (TC-M08)."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.institucional import OrigemUnidade
from src.models.notificacao import Notificacao, TipoEvento
from src.models.participante import RegimeExecucao, TipoVinculo
from src.models.user import UserRole
from src.services.notificacao import criar_notificacao, enviar_notificacoes_pendentes

from .conftest import persist_user, set_auth_cookie


async def test_criar_notificacao_avaliacao_realizada(db: AsyncSession):
    admin = await persist_user(db, email="a@t.com", role=UserRole.ADMIN)
    n = await criar_notificacao(
        db,
        tipo_evento=TipoEvento.AVALIACAO_REALIZADA,
        conteudo="Sua avaliação do período foi registrada: Adequado (3).",
        destinatario_user_id=admin.id,
        contexto={"nota": 3, "periodo": "2024-03"},
    )
    await db.commit()
    assert n.id is not None
    assert n.enviada is False


async def test_criar_notificacao_todos_tipos_eventos():
    """Verify all 8 mandatory event types are defined (RF-029)."""
    tipos = {e.value for e in TipoEvento}
    obrigatorios = {
        "avaliacao_realizada",
        "recurso_aberto",
        "recurso_decidido",
        "prazo_registro_iminente",
        "convocacao_emitida",
        "desligamento_registrado",
        "pgd_suspenso_revogado",
        "plano_aprovado",
    }
    assert obrigatorios.issubset(tipos)


async def test_criar_notificacao_sem_usuario(db: AsyncSession):
    n = await criar_notificacao(
        db,
        tipo_evento=TipoEvento.PGD_SUSPENSO_REVOGADO,
        conteudo="O PGD foi suspenso.",
        destinatario_email="servidor@orgao.gov.br",
    )
    await db.commit()
    assert n.destinatario_user_id is None
    assert n.destinatario_email == "servidor@orgao.gov.br"


async def test_criar_notificacao_com_contexto(db: AsyncSession):
    n = await criar_notificacao(
        db,
        tipo_evento=TipoEvento.CONVOCACAO_EMITIDA,
        conteudo="Você foi convocado para comparecer presencialmente.",
        contexto={
            "data_comparecimento": "2024-04-15",
            "local": "Sala 301",
        },
    )
    await db.commit()
    assert n.contexto["local"] == "Sala 301"


async def test_notificacoes_persistidas_no_db(db: AsyncSession):
    for i, tipo in enumerate(list(TipoEvento)[:3]):
        await criar_notificacao(
            db,
            tipo_evento=tipo,
            conteudo=f"Notificação {i}",
        )
    await db.commit()

    result = await db.execute(select(Notificacao))
    todas = result.scalars().all()
    assert len(todas) == 3


# ---------------------------------------------------------------------------
# Email sending (mocked SMTP)
# ---------------------------------------------------------------------------


async def test_enviar_notificacoes_pendentes_sem_registros(db: AsyncSession):
    count = await enviar_notificacoes_pendentes(db)
    assert count == 0


async def test_enviar_notificacoes_pendentes_com_email(db: AsyncSession):
    await criar_notificacao(
        db,
        tipo_evento=TipoEvento.PLANO_APROVADO,
        conteudo="Plano aprovado",
        destinatario_email="servidor@orgao.gov.br",
    )
    await db.commit()

    mock_mail = MagicMock()
    mock_mail.send_message = AsyncMock()

    count = await enviar_notificacoes_pendentes(db, mail=mock_mail)
    assert count == 1
    mock_mail.send_message.assert_called_once()

    result = await db.execute(select(Notificacao).where(Notificacao.enviada == True))  # noqa: E712
    enviadas = result.scalars().all()
    assert len(enviadas) == 1
    assert enviadas[0].enviada_em is not None


async def test_enviar_notificacoes_sem_destinatario_e_skipped(db: AsyncSession):
    await criar_notificacao(
        db,
        tipo_evento=TipoEvento.PGD_SUSPENSO_REVOGADO,
        conteudo="PGD suspenso",
    )
    await db.commit()

    mock_mail = MagicMock()
    mock_mail.send_message = AsyncMock()

    count = await enviar_notificacoes_pendentes(db, mail=mock_mail)
    assert count == 0
    mock_mail.send_message.assert_not_called()


async def test_enviar_notificacoes_por_user_id(db: AsyncSession):
    admin = await persist_user(db, email="admin@t.com", role=UserRole.ADMIN)
    await criar_notificacao(
        db,
        tipo_evento=TipoEvento.AVALIACAO_REALIZADA,
        conteudo="Avaliação registrada",
        destinatario_user_id=admin.id,
    )
    await db.commit()

    mock_mail = MagicMock()
    mock_mail.send_message = AsyncMock()

    count = await enviar_notificacoes_pendentes(db, mail=mock_mail)
    assert count == 1
    call_args = mock_mail.send_message.call_args[0][0]
    assert any("admin@t.com" in str(r) for r in call_args.recipients)


# ---------------------------------------------------------------------------
# Integration: notification fired by service events
# ---------------------------------------------------------------------------


async def _setup_for_notif(db):
    """Creates full hierarchy up to AvaliacaoRegistrosExecucao."""
    from src.models.institucional import UnidadeExecucao
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
    from src.services.plano_trabalho import (
        criar_plano_trabalho,
        iniciar_execucao_pt,
        registrar_execucao,
    )

    admin = await persist_user(db, email="admin@notif.com", role=UserRole.ADMIN)
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=1,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="UA N",
        sigla="UAN",
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
        nome="UI N",
        sigla="UIN",
        ato_instituicao_ref="R2",
        data_instituicao=date(2024, 1, 10),
        tipos_atividades="T",
        modalidades_autorizadas=[1],
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=200,
        nome="UE N",
        sigla="UEN",
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
        nome="Notif Test",
        email="notif@t.com",
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
        id_plano_trabalho="PT-N",
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
        id_periodo_avaliativo="P-N",
        plano_trabalho_id=pt.id,
        data_inicio_periodo_avaliativo=date(2024, 3, 1),
        data_fim_periodo_avaliativo=date(2024, 3, 31),
        descricao_execucao="Exec",
        user=admin,
    )
    return are, admin


async def test_avaliacao_realizada_cria_notificacao(db: AsyncSession):
    from src.services.avaliacao import avaliar_registros_execucao

    are, admin = await _setup_for_notif(db)
    await avaliar_registros_execucao(
        db,
        avaliacao_id=are.id,
        nota=3,
        data_avaliacao=date(2024, 4, 10),
        user=admin,
    )

    result = await db.execute(
        select(Notificacao).where(Notificacao.tipo_evento == TipoEvento.AVALIACAO_REALIZADA)
    )
    notifs = result.scalars().all()
    assert len(notifs) == 1
    assert notifs[0].destinatario_email == "notif@t.com"


async def test_plano_aprovado_cria_notificacao(db: AsyncSession):
    from src.models.institucional import UnidadeExecucao
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
    from src.services.plano_trabalho import criar_plano_trabalho

    admin = await persist_user(db, email="admin2@notif.com", role=UserRole.ADMIN)
    ua = await criar_unidade_autorizadora(
        db,
        cod_unidade_autorizadora=2,
        origem_unidade=OrigemUnidade.SIAPE,
        nome="UA N2",
        sigla="UN2",
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
        cod_unidade_instituidora=200,
        nome="UI N2",
        sigla="UN2",
        ato_instituicao_ref="R2",
        data_instituicao=date(2024, 1, 10),
        tipos_atividades="T",
        modalidades_autorizadas=[1],
        conteudo_minimo_tcr="C",
        prazo_antecedencia_convocacao_dias=5,
        user=admin,
    )
    ue = UnidadeExecucao(
        unidade_instituidora_id=ui.id,
        cod_unidade_executora=300,
        nome="UE N2",
        sigla="UN2",
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
        nome="Notif2",
        email="notif2@t.com",
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

    await criar_plano_trabalho(
        db,
        id_plano_trabalho="PT-NOTIF2",
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

    result = await db.execute(
        select(Notificacao).where(Notificacao.tipo_evento == TipoEvento.PLANO_APROVADO)
    )
    notifs = result.scalars().all()
    assert len(notifs) == 1
    assert notifs[0].destinatario_email == "notif2@t.com"


# ---------------------------------------------------------------------------
# GraphQL query
# ---------------------------------------------------------------------------


async def test_gql_minhas_notificacoes(client: AsyncClient, db: AsyncSession):
    admin = await persist_user(db, email="admin@t.com", role=UserRole.ADMIN)
    set_auth_cookie(client, admin)

    await criar_notificacao(
        db,
        tipo_evento=TipoEvento.PLANO_APROVADO,
        conteudo="Plano aprovado",
        destinatario_user_id=admin.id,
    )
    await db.commit()

    query = """
    query {
      minhasNotificacoes {
        id
        tipoEvento
        conteudo
        enviada
      }
    }
    """
    resp = await client.post("/graphql", json={"query": query})
    assert resp.status_code == 200
    data = resp.json()
    assert "errors" not in data
    notifs = data["data"]["minhasNotificacoes"]
    assert len(notifs) == 1
    assert notifs[0]["tipoEvento"] == "PLANO_APROVADO"
    assert notifs[0]["enviada"] is False
