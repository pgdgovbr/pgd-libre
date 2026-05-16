#!/usr/bin/env python3
"""
Demo seed script for PGD Libre.

Creates realistic data covering all modules and user journeys.
Designed to reset daily for a live demo instance.

Usage:
    # With local venv:
    cd pgd-libre/pgd-libre && source .venv/bin/activate
    python scripts/seed_demo.py

    # Via Docker:
    docker exec pgd-libre-app-1 python scripts/seed_demo.py
"""
import asyncio
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AsyncSessionLocal
from src.models.institucional import (
    AtoAutorizacao,
    OrigemUnidade,
    StatusAto,
    StatusPgd,
    UnidadeAutorizadora,
    UnidadeExecucao,
    UnidadeInstituidora,
)
from src.models.notificacao import Notificacao, TipoEvento
from src.models.participante import (
    Afastamento,
    Convocacao,
    Participante,
    RegimeExecucao,
    StatusConvocacao,
    StatusTCR,
    TCR,
    TermoGuardaEquipamento,
    TipoAfastamento,
    TipoVinculo,
)
from src.models.plano import (
    STATUS_PE_APROVADO,
    STATUS_PE_EM_EXECUCAO,
    STATUS_PT_APROVADO,
    STATUS_PT_EM_EXECUCAO,
    AvaliacaoRegistrosExecucao,
    Contribuicao,
    Entrega,
    PlanoEntregas,
    PlanoTrabalho,
    StatusRecurso,
    TipoMeta,
)
from src.models.sync_log import RegistroEnvioAPI, TipoEntidadeSync
from src.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Org codes (fictitious but realistic for SIAPE/MGI)
# ---------------------------------------------------------------------------
COD_AUTORIZADORA = 20001  # MGI
COD_INSTITUIDORA = 20110  # SEGES
COD_CGPGD = 20111
COD_CGTI = 20112
ORIGEM = OrigemUnidade.SIAPE


# ---------------------------------------------------------------------------
# Delete all data in reverse FK order
# ---------------------------------------------------------------------------
async def _delete_all(session: AsyncSession) -> None:
    tables = [
        "notificacoes",
        "registros_envio_api",
        "afastamentos",
        "autorizacoes_adicional_noturno",
        "termos_guarda_equipamento",
        "processos_selecao",
        "delegacoes_competencia",
        "convocacoes",
        "avaliacoes_registros_execucao",
        "contribuicoes",
        "planos_trabalho",
        "entregas",
        "planos_entregas",
        "tcrs",
        "participantes",
        "unidades_execucao",
        "unidades_instituidoras",
        "atos_autorizacao",
        "unidades_autorizadoras",
        "users",
    ]
    for table in tables:
        await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
    await session.commit()


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------
async def seed(session: AsyncSession) -> None:  # noqa: PLR0915
    today = date.today()
    now = datetime.now(UTC)

    plan_start = today - timedelta(days=180)
    plan_end = today + timedelta(days=185)

    p2_start = today - timedelta(days=60)
    p2_end = today - timedelta(days=31)

    p1_start = today - timedelta(days=30)
    p1_end = today - timedelta(days=1)

    # ------------------------------------------------------------------
    # 1. Users
    # ------------------------------------------------------------------
    u_admin = User(email="admin@pgd-demo.gov.br", name="Roberto Admin", role=UserRole.ADMIN)
    u_gestor = User(
        email="gestor@pgd-demo.gov.br", name="Maria Fernanda",
        role=UserRole.GESTOR_UNIDADE, cod_unidade_autorizadora=COD_AUTORIZADORA,
    )
    u_chefe_cgpgd = User(
        email="chefe1@pgd-demo.gov.br", name="Carlos Souza",
        role=UserRole.CHEFE_IMEDIATO, cod_unidade_autorizadora=COD_AUTORIZADORA,
    )
    u_chefe_cgti = User(
        email="chefe2@pgd-demo.gov.br", name="Beatriz Lima",
        role=UserRole.CHEFE_IMEDIATO, cod_unidade_autorizadora=COD_AUTORIZADORA,
    )
    u_ana = User(
        email="servidor1@pgd-demo.gov.br", name="Ana Silva",
        role=UserRole.SERVIDOR, cod_unidade_autorizadora=COD_AUTORIZADORA,
    )
    u_joao = User(
        email="servidor2@pgd-demo.gov.br", name="João Santos",
        role=UserRole.SERVIDOR, cod_unidade_autorizadora=COD_AUTORIZADORA,
    )
    u_carla = User(
        email="servidor3@pgd-demo.gov.br", name="Carla Mendes",
        role=UserRole.SERVIDOR, cod_unidade_autorizadora=COD_AUTORIZADORA,
    )
    u_lucas = User(
        email="servidor4@pgd-demo.gov.br", name="Lucas Ramos",
        role=UserRole.SERVIDOR, cod_unidade_autorizadora=COD_AUTORIZADORA,
    )
    u_pedro = User(
        email="servidor5@pgd-demo.gov.br", name="Pedro Alves",
        role=UserRole.SERVIDOR, cod_unidade_autorizadora=COD_AUTORIZADORA,
    )

    session.add_all([
        u_admin, u_gestor, u_chefe_cgpgd, u_chefe_cgti,
        u_ana, u_joao, u_carla, u_lucas, u_pedro,
    ])
    await session.flush()

    # ------------------------------------------------------------------
    # 2. Institutional structure
    # ------------------------------------------------------------------
    unid_aut = UnidadeAutorizadora(
        origem_unidade=ORIGEM,
        cod_unidade_autorizadora=COD_AUTORIZADORA,
        nome="Ministério da Gestão e da Inovação em Serviços Públicos",
        sigla="MGI",
        pgd_autorizado=True,
    )
    session.add(unid_aut)
    await session.flush()

    ato = AtoAutorizacao(
        unidade_autorizadora_id=unid_aut.id,
        autoridade="Ministro da Gestão e da Inovação",
        data_publicacao=date(2023, 6, 1),
        referencia="Portaria MGI nº 001/2023",
        status=StatusAto.ATIVO,
    )
    session.add(ato)

    unid_inst = UnidadeInstituidora(
        unidade_autorizadora_id=unid_aut.id,
        cod_unidade_instituidora=COD_INSTITUIDORA,
        nome="Secretaria de Gestão e Inovação",
        sigla="SEGES",
        ato_instituicao_ref="Portaria SEGES nº 042/2023",
        data_instituicao=date(2023, 7, 1),
        tipos_atividades=(
            "Análise de políticas públicas, gestão de processos institucionais, "
            "elaboração de normativos, desenvolvimento de sistemas de informação, "
            "capacitação de servidores"
        ),
        modalidades_autorizadas=[1, 2, 3],
        vagas_percentual_presencial=20,
        vagas_percentual_tt_parcial=50,
        vagas_percentual_tt_integral=30,
        conteudo_minimo_tcr=(
            "Modalidade de execução, regime de trabalho, carga horária, "
            "critérios de avaliação, canais de comunicação, responsabilidades "
            "do servidor e da chefia, ciência sobre ergonomia e custeio de infraestrutura."
        ),
        prazo_antecedencia_convocacao_dias=5,
        nivel_produtividade_adicional_tt=(
            "Servidores em teletrabalho devem manter disponibilidade em horário "
            "comercial e participar de reuniões de alinhamento semanais."
        ),
        status=StatusPgd.EM_VIGOR,
    )
    session.add(unid_inst)
    await session.flush()

    unid_cgpgd = UnidadeExecucao(
        unidade_instituidora_id=unid_inst.id,
        cod_unidade_executora=COD_CGPGD,
        nome="Coordenação-Geral de Gestão do Programa de Gestão",
        sigla="CGPGD",
        chefia_user_id=u_chefe_cgpgd.id,
        nivel_superior_user_id=u_gestor.id,
    )
    unid_cgti = UnidadeExecucao(
        unidade_instituidora_id=unid_inst.id,
        cod_unidade_executora=COD_CGTI,
        nome="Coordenação-Geral de Tecnologia da Informação",
        sigla="CGTI",
        chefia_user_id=u_chefe_cgti.id,
        nivel_superior_user_id=u_gestor.id,
    )
    session.add_all([unid_cgpgd, unid_cgti])
    await session.flush()

    # ------------------------------------------------------------------
    # 3. Participantes
    # ------------------------------------------------------------------
    def _participante(
        nome: str, email: str, cpf: str, matricula: str,
        modalidade: int, unidade: UnidadeExecucao, user: User,
    ) -> Participante:
        return Participante(
            origem_unidade=ORIGEM,
            cod_unidade_autorizadora=COD_AUTORIZADORA,
            cod_unidade_lotacao=unidade.cod_unidade_executora,
            matricula_siape=matricula,
            cod_unidade_instituidora=COD_INSTITUIDORA,
            cpf=cpf,
            nome=nome,
            email=email,
            situacao=1,
            modalidade_execucao=modalidade,
            data_assinatura_tcr=plan_start,
            cumpriu_estagio_probatorio=True,
            data_fim_estagio_probatorio=plan_start - timedelta(days=365),
            tipo_vinculo=TipoVinculo.EFETIVO,
            data_ingresso_pgd=plan_start,
            user_id=user.id,
            unidade_execucao_id=unidade.id,
        )

    p_ana = _participante("Ana Silva", "servidor1@pgd-demo.gov.br", "12345678901", "1234567", 2, unid_cgpgd, u_ana)
    p_joao = _participante("João Santos", "servidor2@pgd-demo.gov.br", "23456789012", "2345678", 3, unid_cgpgd, u_joao)
    p_carla = _participante("Carla Mendes", "servidor3@pgd-demo.gov.br", "34567890123", "3456789", 1, unid_cgpgd, u_carla)
    p_lucas = _participante("Lucas Ramos", "servidor4@pgd-demo.gov.br", "45678901234", "4567890", 2, unid_cgpgd, u_lucas)
    p_pedro = _participante("Pedro Alves", "servidor5@pgd-demo.gov.br", "56789012345", "5678901", 2, unid_cgti, u_pedro)

    session.add_all([p_ana, p_joao, p_carla, p_lucas, p_pedro])
    await session.flush()

    # ------------------------------------------------------------------
    # 4. TCRs (all ATIVO)
    # ------------------------------------------------------------------
    _tcr_base = dict(
        prazo_antecedencia_convocacao_dias=5,
        canais_comunicacao=["email", "microsoft_teams"],
        responsabilidades=(
            "Manter disponibilidade no horário comercial; registrar execução mensalmente; "
            "participar de reuniões de equipe; cumprir prazos de entrega pactuados."
        ),
        ciencia_instalacoes_ergonomia=True,
        ciencia_nao_direito_adquirido=True,
        ciencia_custeio_estrutura=True,
        data_assinatura_participante=now - timedelta(days=180),
        data_assinatura_chefia=now - timedelta(days=179),
        status=StatusTCR.ATIVO,
    )

    tcr_ana = TCR(participante_id=p_ana.id, chefia_user_id=u_chefe_cgpgd.id, modalidade_execucao=2, regime_execucao=RegimeExecucao.PARCIAL, **_tcr_base)
    tcr_joao = TCR(participante_id=p_joao.id, chefia_user_id=u_chefe_cgpgd.id, modalidade_execucao=3, regime_execucao=RegimeExecucao.INTEGRAL, **_tcr_base)
    tcr_carla = TCR(participante_id=p_carla.id, chefia_user_id=u_chefe_cgpgd.id, modalidade_execucao=1, regime_execucao=RegimeExecucao.PARCIAL, **_tcr_base)
    tcr_lucas = TCR(participante_id=p_lucas.id, chefia_user_id=u_chefe_cgpgd.id, modalidade_execucao=2, regime_execucao=RegimeExecucao.PARCIAL, **_tcr_base)
    tcr_pedro = TCR(participante_id=p_pedro.id, chefia_user_id=u_chefe_cgti.id, modalidade_execucao=2, regime_execucao=RegimeExecucao.PARCIAL, **_tcr_base)

    session.add_all([tcr_ana, tcr_joao, tcr_carla, tcr_lucas, tcr_pedro])
    await session.flush()

    # Equipment custody for João (full telework)
    session.add(TermoGuardaEquipamento(
        participante_id=p_joao.id,
        tcr_id=tcr_joao.id,
        descricao_equipamentos=(
            "1x Notebook Dell Latitude 5420 (patrimônio 202300123); "
            "1x Monitor 24\" LG (patrimônio 202300124); "
            "1x Teclado e mouse sem fio (patrimônio 202300125)"
        ),
        data_autorizacao=plan_start + timedelta(days=3),
        autorizado_por_user_id=u_chefe_cgpgd.id,
    ))

    # ------------------------------------------------------------------
    # 5. PlanoEntregas
    # ------------------------------------------------------------------
    pe_cgpgd = PlanoEntregas(
        id_plano_entregas="PE-2025-CGPGD-001",
        origem_unidade=ORIGEM,
        cod_unidade_autorizadora=COD_AUTORIZADORA,
        cod_unidade_instituidora=COD_INSTITUIDORA,
        cod_unidade_executora=COD_CGPGD,
        unidade_execucao_id=unid_cgpgd.id,
        status=STATUS_PE_EM_EXECUCAO,
        data_inicio=plan_start,
        data_termino=plan_end,
        aprovado_por_user_id=u_gestor.id,
        data_aprovacao=plan_start + timedelta(days=2),
        api_sincronizado_em=now - timedelta(days=5),
    )
    # Waiting for gestor approval — enables the gestor journey
    pe_cgti = PlanoEntregas(
        id_plano_entregas="PE-2025-CGTI-001",
        origem_unidade=ORIGEM,
        cod_unidade_autorizadora=COD_AUTORIZADORA,
        cod_unidade_instituidora=COD_INSTITUIDORA,
        cod_unidade_executora=COD_CGTI,
        unidade_execucao_id=unid_cgti.id,
        status=STATUS_PE_APROVADO,
        data_inicio=today - timedelta(days=30),
        data_termino=today + timedelta(days=335),
    )

    session.add_all([pe_cgpgd, pe_cgti])
    await session.flush()

    session.add_all([
        Entrega(id_entrega="E-001", plano_entregas_id=pe_cgpgd.id, nome_entrega="Módulo de Registro de Execução do PGD", meta_entrega=1, tipo_meta=TipoMeta.UNIDADE, data_entrega=plan_end - timedelta(days=90), nome_unidade_demandante="SEGES", nome_unidade_destinataria="Órgãos do SIAPE"),
        Entrega(id_entrega="E-002", plano_entregas_id=pe_cgpgd.id, nome_entrega="Relatórios de Conformidade PGD", meta_entrega=4, tipo_meta=TipoMeta.UNIDADE, data_entrega=plan_end - timedelta(days=10), nome_unidade_demandante="SEGES", nome_unidade_destinataria="CPGD/MGI"),
        Entrega(id_entrega="E-003", plano_entregas_id=pe_cgpgd.id, nome_entrega="Capacitação de Gestores PGD", meta_entrega=80, tipo_meta=TipoMeta.PERCENTUAL, data_entrega=plan_end - timedelta(days=60), nome_unidade_demandante="SEGES", nome_unidade_destinataria="Gestores dos órgãos"),
        Entrega(id_entrega="E-001", plano_entregas_id=pe_cgti.id, nome_entrega="Sistema de Integração com API PGD Central", meta_entrega=1, tipo_meta=TipoMeta.UNIDADE, data_entrega=today + timedelta(days=200), nome_unidade_demandante="CGPGD", nome_unidade_destinataria="Órgãos do SIAPE"),
        Entrega(id_entrega="E-002", plano_entregas_id=pe_cgti.id, nome_entrega="Dashboard de Monitoramento PGD", meta_entrega=1, tipo_meta=TipoMeta.UNIDADE, data_entrega=today + timedelta(days=300), nome_unidade_demandante="SEGES", nome_unidade_destinataria="Gestores da SEGES"),
    ])

    # ------------------------------------------------------------------
    # 6. PlanoTrabalho
    # ------------------------------------------------------------------
    _criterios = (
        "Cumprimento dos prazos pactuados; qualidade das entregas; "
        "proatividade na comunicação de impedimentos; participação nas reuniões de equipe."
    )

    def _plano_trabalho(
        id_pt: str, participante: Participante, tcr: TCR,
        status: int, data_inicio: date, data_termino: date,
        carga: int, pe: PlanoEntregas | None = None,
    ) -> PlanoTrabalho:
        return PlanoTrabalho(
            id_plano_trabalho=id_pt,
            origem_unidade=ORIGEM,
            cod_unidade_autorizadora=COD_AUTORIZADORA,
            cod_unidade_executora=participante.cod_unidade_lotacao,
            cod_unidade_lotacao_participante=participante.cod_unidade_lotacao,
            participante_id=participante.id,
            cpf_participante=participante.cpf,
            matricula_siape=participante.matricula_siape,
            tcr_id=tcr.id,
            status=status,
            data_inicio=data_inicio,
            data_termino=data_termino,
            carga_horaria_disponivel=carga,
            criterios_avaliacao=_criterios,
            plano_entregas_id=pe.id if pe else None,
        )

    pt_ana = _plano_trabalho("PT-2025-ANA-001", p_ana, tcr_ana, STATUS_PT_EM_EXECUCAO, plan_start, plan_end, 960, pe_cgpgd)
    pt_joao = _plano_trabalho("PT-2025-JOAO-001", p_joao, tcr_joao, STATUS_PT_EM_EXECUCAO, plan_start, plan_end, 960, pe_cgpgd)
    pt_carla = _plano_trabalho("PT-2025-CARLA-001", p_carla, tcr_carla, STATUS_PT_EM_EXECUCAO, plan_start, plan_end, 960, pe_cgpgd)
    # Pedro: approved but not started — links to PE_CGTI (not in execution yet)
    pt_pedro = _plano_trabalho("PT-2025-PEDRO-001", p_pedro, tcr_pedro, STATUS_PT_APROVADO, today - timedelta(days=30), today + timedelta(days=335), 1760, pe_cgti)

    session.add_all([pt_ana, pt_joao, pt_carla, pt_pedro])
    await session.flush()

    # Contribuições
    session.add_all([
        # Ana: 70% deliverable + 30% support
        Contribuicao(id_contribuicao="C-ANA-001", plano_trabalho_id=pt_ana.id, tipo_contribuicao=1, percentual_contribuicao=70, id_plano_entregas="PE-2025-CGPGD-001", id_entrega="E-001", descricao="Desenvolvimento e testes do módulo de registro de execução", rotulo="Desenvolvimento"),
        Contribuicao(id_contribuicao="C-ANA-002", plano_trabalho_id=pt_ana.id, tipo_contribuicao=2, percentual_contribuicao=30, descricao="Reuniões de equipe, alinhamentos, planejamento interno e suporte", rotulo="Suporte"),
        # João: 60% deliverable + 20% support + 20% cross-unit (CGTI)
        Contribuicao(id_contribuicao="C-JOAO-001", plano_trabalho_id=pt_joao.id, tipo_contribuicao=1, percentual_contribuicao=60, id_plano_entregas="PE-2025-CGPGD-001", id_entrega="E-002", descricao="Elaboração e revisão dos relatórios trimestrais de conformidade PGD", rotulo="Relatórios"),
        Contribuicao(id_contribuicao="C-JOAO-002", plano_trabalho_id=pt_joao.id, tipo_contribuicao=2, percentual_contribuicao=20, descricao="Reuniões de equipe e suporte à gestão", rotulo="Gestão"),
        Contribuicao(id_contribuicao="C-JOAO-003", plano_trabalho_id=pt_joao.id, tipo_contribuicao=3, percentual_contribuicao=20, descricao="Apoio à CGTI no levantamento de requisitos do sistema de integração API", rotulo="Colaboração CGTI"),
        # Carla: 80% deliverable + 20% admin
        Contribuicao(id_contribuicao="C-CARLA-001", plano_trabalho_id=pt_carla.id, tipo_contribuicao=1, percentual_contribuicao=80, id_plano_entregas="PE-2025-CGPGD-001", id_entrega="E-003", descricao="Elaboração e aplicação do programa de capacitação de gestores", rotulo="Capacitação"),
        Contribuicao(id_contribuicao="C-CARLA-002", plano_trabalho_id=pt_carla.id, tipo_contribuicao=2, percentual_contribuicao=20, descricao="Reuniões de equipe e atividades administrativas", rotulo="Administrativo"),
        # Pedro: 80% deliverable + 20% docs
        Contribuicao(id_contribuicao="C-PEDRO-001", plano_trabalho_id=pt_pedro.id, tipo_contribuicao=1, percentual_contribuicao=80, id_plano_entregas="PE-2025-CGTI-001", id_entrega="E-001", descricao="Desenvolvimento da integração com a API PGD Central", rotulo="Desenvolvimento"),
        Contribuicao(id_contribuicao="C-PEDRO-002", plano_trabalho_id=pt_pedro.id, tipo_contribuicao=2, percentual_contribuicao=20, descricao="Reuniões técnicas e documentação", rotulo="Documentação"),
    ])

    # ------------------------------------------------------------------
    # 7. AvaliacaoRegistrosExecucao
    # ------------------------------------------------------------------
    # Ana — Period -2: nota 3 (adequado), closed
    are_ana_p2 = AvaliacaoRegistrosExecucao(
        id_periodo_avaliativo="ARE-ANA-001",
        plano_trabalho_id=pt_ana.id,
        data_inicio_periodo_avaliativo=p2_start,
        data_fim_periodo_avaliativo=p2_end,
        descricao_execucao=(
            "Implementei a funcionalidade de exportação de relatórios em PDF e contribuí "
            "na revisão das especificações técnicas do módulo de registro. Participei de "
            "4 reuniões de equipe e 2 alinhamentos com stakeholders externos."
        ),
        ocorrencias="Nenhuma ocorrência relevante no período.",
        data_registro_participante=now - timedelta(days=38),
        avaliacao_registros_execucao=3,
        data_avaliacao_registros_execucao=p2_end + timedelta(days=12),
    )

    # Ana — Period -1: nota 4 (inadequado), recurso ABERTO — chefe must respond
    are_ana_p1 = AvaliacaoRegistrosExecucao(
        id_periodo_avaliativo="ARE-ANA-002",
        plano_trabalho_id=pt_ana.id,
        data_inicio_periodo_avaliativo=p1_start,
        data_fim_periodo_avaliativo=p1_end,
        descricao_execucao=(
            "Trabalhei na implementação do módulo de notificações. Enfrentei dificuldades "
            "técnicas com a integração de uma API externa que causaram atrasos na entrega "
            "prevista. Comuniquei os impedimentos à chefia durante as reuniões semanais."
        ),
        ocorrencias=(
            "API de terceiros ficou indisponível por 3 dias úteis (dias 15, 16 e 17 do "
            "período), impactando o cronograma de desenvolvimento."
        ),
        data_registro_participante=now - timedelta(days=8),
        avaliacao_registros_execucao=4,
        data_avaliacao_registros_execucao=today - timedelta(days=5),
        avaliacao_justificativa=(
            "A entrega principal do período não foi concluída. Apesar da ocorrência relatada, "
            "o prazo disponível era suficiente para mitigar o impacto caso houvesse comunicação "
            "mais tempestiva."
        ),
        recurso_texto=(
            "Solicito revisão da avaliação, pois a indisponibilidade da API externa foi "
            "comunicada em tempo real nas reuniões semanais e está documentada nos registros "
            "de incidente. O atraso decorreu de fator externo alheio ao meu controle."
        ),
        recurso_data=now - timedelta(days=3),
        status_recurso=StatusRecurso.ABERTO,
    )

    # Ana — Current period: no registration yet — Ana can register now
    are_ana_atual = AvaliacaoRegistrosExecucao(
        id_periodo_avaliativo="ARE-ANA-003",
        plano_trabalho_id=pt_ana.id,
        data_inicio_periodo_avaliativo=today,
        data_fim_periodo_avaliativo=today + timedelta(days=30),
    )

    # João — Period -1: registered by server, awaiting chefe evaluation
    are_joao_p1 = AvaliacaoRegistrosExecucao(
        id_periodo_avaliativo="ARE-JOAO-001",
        plano_trabalho_id=pt_joao.id,
        data_inicio_periodo_avaliativo=p1_start,
        data_fim_periodo_avaliativo=p1_end,
        descricao_execucao=(
            "Finalizei o primeiro relatório trimestral de conformidade PGD com dados de "
            "12 órgãos. Também prestei apoio técnico à CGTI no levantamento de requisitos "
            "da API, participando de 3 reuniões técnicas. Todos os prazos foram cumpridos."
        ),
        data_registro_participante=now - timedelta(days=5),
    )

    # Carla — Period -1: nota 2 (alto desempenho), closed
    are_carla_p1 = AvaliacaoRegistrosExecucao(
        id_periodo_avaliativo="ARE-CARLA-001",
        plano_trabalho_id=pt_carla.id,
        data_inicio_periodo_avaliativo=p1_start,
        data_fim_periodo_avaliativo=p1_end,
        descricao_execucao=(
            "Concluí o primeiro módulo do programa de capacitação com 95% de satisfação "
            "dos participantes (acima da meta de 80%). Treinei 45 gestores de 8 órgãos "
            "distintos. Desenvolvi material didático adicional não previsto no escopo original."
        ),
        ocorrencias="Licença de férias de 7 dias úteis no período (dias 8 a 16). Atividades foram redistribuídas com antecedência.",
        data_registro_participante=now - timedelta(days=12),
        avaliacao_registros_execucao=2,
        data_avaliacao_registros_execucao=today - timedelta(days=8),
    )

    session.add_all([are_ana_p2, are_ana_p1, are_ana_atual, are_joao_p1, are_carla_p1])

    # ------------------------------------------------------------------
    # 8. Convocação (João — TT integral, summons in 5 days)
    # ------------------------------------------------------------------
    conv_joao = Convocacao(
        participante_id=p_joao.id,
        unidade_execucao_id=unid_cgpgd.id,
        chefia_user_id=u_chefe_cgpgd.id,
        canal_comunicacao="microsoft_teams",
        data_convocacao=today - timedelta(days=2),
        data_comparecimento_prevista=today + timedelta(days=5),
        horario_comparecimento="09:00",
        local_comparecimento="Esplanada dos Ministérios, Bloco C, Sala 412 — Brasília/DF",
        periodo_presencial_inicio=today + timedelta(days=5),
        periodo_presencial_fim=today + timedelta(days=5),
        motivo="Reunião presencial obrigatória de alinhamento do plano de entregas e revisão de metas do segundo semestre.",
        status=StatusConvocacao.PENDENTE,
    )
    session.add(conv_joao)

    # ------------------------------------------------------------------
    # 9. Afastamento (Carla — férias, already ended)
    # ------------------------------------------------------------------
    session.add(Afastamento(
        participante_id=p_carla.id,
        tipo_afastamento=TipoAfastamento.FERIAS,
        data_inicio=today - timedelta(days=20),
        data_fim=today - timedelta(days=8),
        observacao="Férias regulamentares — período aprovado em 2025-03-10.",
        registrado_por_user_id=u_chefe_cgpgd.id,
    ))

    # ------------------------------------------------------------------
    # 10. RegistroEnvioAPI (sync log — mixed success/error)
    # ------------------------------------------------------------------
    session.add_all([
        RegistroEnvioAPI(tipo_entidade=TipoEntidadeSync.PARTICIPANTE, entidade_id=p_ana.id, tentativa=1, sucesso=True, http_status=200),
        RegistroEnvioAPI(tipo_entidade=TipoEntidadeSync.PLANO_TRABALHO, entidade_id=pt_ana.id, tentativa=1, sucesso=True, http_status=200),
        RegistroEnvioAPI(tipo_entidade=TipoEntidadeSync.PARTICIPANTE, entidade_id=p_joao.id, tentativa=1, sucesso=True, http_status=200),
        RegistroEnvioAPI(tipo_entidade=TipoEntidadeSync.PARTICIPANTE, entidade_id=p_carla.id, tentativa=1, sucesso=True, http_status=200),
        RegistroEnvioAPI(tipo_entidade=TipoEntidadeSync.PLANO_ENTREGAS, entidade_id=pe_cgpgd.id, tentativa=1, sucesso=True, http_status=200),
        RegistroEnvioAPI(tipo_entidade=TipoEntidadeSync.PARTICIPANTE, entidade_id=p_pedro.id, tentativa=1, sucesso=False, http_status=500, erro_mensagem="Timeout connecting to API PGD Central: connection timed out after 30s"),
        RegistroEnvioAPI(tipo_entidade=TipoEntidadeSync.PARTICIPANTE, entidade_id=p_pedro.id, tentativa=2, sucesso=False, http_status=500, erro_mensagem="Timeout connecting to API PGD Central: connection timed out after 30s"),
        RegistroEnvioAPI(tipo_entidade=TipoEntidadeSync.PLANO_TRABALHO, entidade_id=pt_pedro.id, tentativa=1, sucesso=False, http_status=None, erro_mensagem="Participante não sincronizado — envio de PlanoTrabalho cancelado"),
    ])

    # ------------------------------------------------------------------
    # 11. Notificações
    # ------------------------------------------------------------------
    def _fmt(d: date) -> str:
        return d.strftime("%d/%m/%Y")

    session.add_all([
        Notificacao(
            tipo_evento=TipoEvento.AVALIACAO_REALIZADA,
            destinatario_user_id=u_ana.id,
            destinatario_email="servidor1@pgd-demo.gov.br",
            conteudo=f"Sua avaliação do período de {_fmt(p1_start)} a {_fmt(p1_end)} foi registrada com nota 4 (Inadequado). Você pode contestar a avaliação em até 10 dias.",
            contexto={"plano_trabalho_id": str(pt_ana.id), "periodo": "ARE-ANA-002", "nota": 4},
            enviada=True, enviada_em=now - timedelta(days=5),
        ),
        Notificacao(
            tipo_evento=TipoEvento.RECURSO_ABERTO,
            destinatario_user_id=u_chefe_cgpgd.id,
            destinatario_email="chefe1@pgd-demo.gov.br",
            conteudo=f"Ana Silva contestou a avaliação do período de {_fmt(p1_start)} a {_fmt(p1_end)}. Você tem até {_fmt(today + timedelta(days=7))} para responder.",
            contexto={"plano_trabalho_id": str(pt_ana.id), "periodo": "ARE-ANA-002", "participante": "Ana Silva"},
            enviada=True, enviada_em=now - timedelta(days=3),
        ),
        Notificacao(
            tipo_evento=TipoEvento.PRAZO_REGISTRO_IMINENTE,
            destinatario_user_id=u_joao.id,
            destinatario_email="servidor2@pgd-demo.gov.br",
            conteudo=f"Lembrete: o prazo para avaliação do seu registro do período de {_fmt(p1_start)} a {_fmt(p1_end)} vence em breve.",
            contexto={"plano_trabalho_id": str(pt_joao.id), "periodo": "ARE-JOAO-001"},
            enviada=True, enviada_em=now - timedelta(days=1),
        ),
        Notificacao(
            tipo_evento=TipoEvento.CONVOCACAO_EMITIDA,
            destinatario_user_id=u_joao.id,
            destinatario_email="servidor2@pgd-demo.gov.br",
            conteudo=f"Você foi convocado(a) para comparecimento presencial em {_fmt(today + timedelta(days=5))} às 09h00, Esplanada dos Ministérios, Bloco C, Sala 412.",
            contexto={"convocacao_id": str(conv_joao.id)},
            enviada=True, enviada_em=now - timedelta(days=2),
        ),
        Notificacao(
            tipo_evento=TipoEvento.PLANO_APROVADO,
            destinatario_user_id=u_carla.id,
            destinatario_email="servidor3@pgd-demo.gov.br",
            conteudo=f"Seu Plano de Trabalho foi aprovado e está em execução. Período: {_fmt(plan_start)} a {_fmt(plan_end)}.",
            contexto={"plano_trabalho_id": str(pt_carla.id)},
            enviada=True, enviada_em=now - timedelta(days=178),
        ),
    ])

    await session.commit()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main() -> None:
    print("🌱 PGD Libre — iniciando seed de dados demo...")
    async with AsyncSessionLocal() as session:
        print("🗑️  Limpando dados existentes...")
        await _delete_all(session)
    async with AsyncSessionLocal() as session:
        print("📦 Criando dados de demonstração...")
        await seed(session)
    print("✅ Seed concluído!")
    print("   Usuários: 9 | Participantes: 5 | PlanoTrabalho: 4 | ARE: 5")
    print("   PlanoEntregas: 2 | Contribuições: 9 | Notificações: 5 | Sync log: 8")


if __name__ == "__main__":
    asyncio.run(main())
